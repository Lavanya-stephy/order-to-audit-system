from datetime import datetime, time
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.exceptions import ObjectDoesNotExist

from accounts.models import Role
from accounts.permissions import role_required
from masters.models import RawMaterial, PackagingItem, Product, Unit
from .models import StockMovement, MovementType
from .services import (
    get_stock_summary,
    get_item_ledger,
    get_all_inventory_items,
    record_movement,
    get_item_current_stock,
)
from .forms import StockAdjustmentForm

INVENTORY_VIEWERS = [Role.ADMIN, Role.PRODUCTION, Role.OWNER, Role.ACCOUNTANT]
INVENTORY_MANAGERS = [Role.ADMIN, Role.PRODUCTION, Role.OWNER]


def parse_date_filters(request):
    """Extracts start_date and end_date from GET parameters as aware datetimes."""
    start_str = request.GET.get('start_date', '').strip()
    end_str = request.GET.get('end_date', '').strip()

    start_dt = None
    end_dt = None

    if start_str:
        d = parse_date(start_str)
        if d:
            start_dt = timezone.make_aware(datetime.combine(d, time.min))
    if end_str:
        d = parse_date(end_str)
        if d:
            end_dt = timezone.make_aware(datetime.combine(d, time.max))

    return start_dt, end_dt, start_str, end_str


def resolve_inventory_item(item_key: str):
    """Resolves an item key like 'rm_1', 'pm_2', or 'prod_3' to its model instance."""
    if not item_key or '_' not in item_key:
        return None
    prefix, pk_str = item_key.split('_', 1)
    try:
        pk = int(pk_str)
        if prefix == 'rm':
            return RawMaterial.objects.select_related('unit').get(pk=pk)
        elif prefix == 'pm':
            return PackagingItem.objects.select_related('unit').get(pk=pk)
        elif prefix == 'prod':
            return Product.objects.select_related('unit').get(pk=pk)
    except (ValueError, ObjectDoesNotExist):
        return None
    return None


@login_required
@role_required(INVENTORY_VIEWERS)
def stock_summary_view(request):
    """
    Displays the real-time stock summary table across all inventory items.
    Balances are strictly derived from movements: Opening + Receipts - Issues = Closing.
    Filterable by category (All, Raw Material, Packaging, Finished Product) and date range.
    """
    category_filter = request.GET.get('category', 'all')
    start_dt, end_dt, start_str, end_str = parse_date_filters(request)

    summary_rows = get_stock_summary(
        item_type_filter=category_filter,
        start_date=start_dt,
        end_date=end_dt
    )

    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'csv':
        from reports.exporters import export_stock_summary_csv
        return export_stock_summary_csv(summary_rows)
    elif export_fmt == 'pdf':
        from reports.pdf import build_stock_summary_pdf
        period_label = f"{start_str} to {end_str}" if start_str and end_str else "All Time"
        buf = build_stock_summary_pdf(summary_rows, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="stock_summary.pdf"'
        return response

    total_valuation = sum((row['valuation'] for row in summary_rows), Decimal('0.00'))
    low_stock_count = sum((1 for row in summary_rows if row['is_low_stock']))
    can_adjust = request.user.role in INVENTORY_MANAGERS or request.user.is_superuser

    context = {
        'summary_rows': summary_rows,
        'selected_category': category_filter,
        'start_date': start_str,
        'end_date': end_str,
        'total_items_count': len(summary_rows),
        'total_valuation': total_valuation,
        'low_stock_count': low_stock_count,
        'can_adjust': can_adjust,
    }
    return render(request, 'inventory/stock_summary.html', context)


@login_required
@role_required(INVENTORY_VIEWERS)
def stock_ledger_view(request):
    """
    Displays the chronological stock ledger audit trail for a selected item,
    showing each movement, inward/outward quantity, running balance, and source document reference.
    Filterable by specific item and date range.
    """
    all_items = get_all_inventory_items()
    selected_item_key = request.GET.get('item', '').strip()
    start_dt, end_dt, start_str, end_str = parse_date_filters(request)

    # Default to first item if none selected and items exist
    if not selected_item_key and all_items:
        selected_item_key = all_items[0]['id_str']

    item_obj = resolve_inventory_item(selected_item_key)
    ledger_data = None

    if item_obj:
        ledger_data = get_item_ledger(item_obj, start_date=start_dt, end_date=end_dt)

    export_fmt = request.GET.get('export', '').lower()
    if export_fmt == 'csv' and item_obj and ledger_data:
        from reports.exporters import export_stock_ledger_csv
        return export_stock_ledger_csv(ledger_data, item_obj.name)

    context = {
        'all_items': all_items,
        'selected_item_key': selected_item_key,
        'item_obj': item_obj,
        'ledger_data': ledger_data,
        'start_date': start_str,
        'end_date': end_str,
        'can_adjust': request.user.role in INVENTORY_MANAGERS or request.user.is_superuser,
    }
    return render(request, 'inventory/stock_ledger.html', context)


@login_required
@role_required(INVENTORY_MANAGERS)
def stock_adjustment_view(request):
    """
    Allows authorized floor staff / factory admin to record physical audit stock
    adjustments or opening balances with mandatory source document references.
    """
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            item_type = form.cleaned_data['item_type']
            if item_type == 'raw_material':
                item = form.cleaned_data['raw_material']
            elif item_type == 'packaging':
                item = form.cleaned_data['packaging_item']
            else:
                item = form.cleaned_data['product']

            qty = form.cleaned_data['quantity']
            m_type = form.cleaned_data['movement_type']
            unit = form.cleaned_data['unit'] or item.unit
            source_doc = form.cleaned_data['source_document']
            batch_num = form.cleaned_data['batch_number']
            notes = form.cleaned_data['notes']

            movement = record_movement(
                item=item,
                quantity=qty,
                movement_type=m_type,
                source_document=source_doc,
                user=request.user,
                unit=unit,
                batch_number=batch_num,
                notes=notes,
            )
            messages.success(
                request,
                f"Recorded {movement.get_movement_type_display()} of {movement.quantity} {movement.unit.symbol} for {item.name}."
            )
            return redirect('inventory:stock_summary')
    else:
        initial_item = request.GET.get('item', '')
        form = StockAdjustmentForm()

    return render(request, 'inventory/stock_adjust.html', {
        'form': form,
        'title': 'Record Stock Movement / Audit Adjustment',
        'back_url': reverse('inventory:stock_summary'),
    })

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from accounts.models import Role
from accounts.permissions import role_required
from inventory.services import get_weighted_average_unit_cost
from masters.models import Product
from .models import ProductionRun, ProductionRunItem, ProductionRunLog, DEFAULT_VARIANCE_TOLERANCE_PCT
from .forms import (
    ProductionRunCreateForm,
    ProductionRunEditForm,
    ProductionIssueItemForm,
    ProductionOutputForm,
)
from .services import (
    create_production_run,
    issue_materials_for_run,
    record_production_output,
    log_run_action,
)

PRODUCTION_MANAGERS = [Role.ADMIN, Role.PRODUCTION]
PRODUCTION_VIEWERS = [Role.ADMIN, Role.PRODUCTION, Role.ACCOUNTANT, Role.OWNER]


@login_required
@role_required(PRODUCTION_VIEWERS)
def production_run_list_view(request):
    runs = ProductionRun.objects.select_related('product', 'bom', 'created_by').order_by('-created_at')
    return render(request, 'production/production_run_list.html', {
        'production_runs': runs,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_create_view(request):
    if request.method == 'POST':
        form = ProductionRunCreateForm(request.POST)
        if form.is_valid():
            product = form.cleaned_data['product']
            bom = form.cleaned_data['bom']
            multiplier = form.cleaned_data['batch_multiplier']
            tolerance = form.cleaned_data.get('variance_tolerance_pct') or DEFAULT_VARIANCE_TOLERANCE_PCT
            start_date = form.cleaned_data['start_date']
            notes = form.cleaned_data['notes']

            run = create_production_run(
                product=product,
                bom=bom,
                batch_multiplier=multiplier,
                variance_tolerance_pct=tolerance,
                start_date=start_date,
                notes=notes,
                user=request.user,
            )
            messages.success(request, f"Production Run {run.run_number} created as Planned.")
            return redirect('production:production_run_detail', pk=run.pk)
    else:
        form = ProductionRunCreateForm()

    return render(request, 'production/production_run_form.html', {
        'form': form,
        'title': 'Start New Production Run',
    })


@login_required
@role_required(PRODUCTION_VIEWERS)
def production_run_detail_view(request, pk):
    run = get_object_or_404(
        ProductionRun.objects.select_related('product', 'bom', 'created_by', 'updated_by').prefetch_related('items__unit', 'items__raw_material', 'items__packaging_item', 'audit_logs__user'),
        pk=pk
    )
    raw_material_items = run.items.filter(raw_material__isnull=False)
    packaging_items = run.items.filter(packaging_item__isnull=False)
    audit_logs = run.audit_logs.select_related('user').order_by('-timestamp', '-id')

    can_manage = request.user.role in PRODUCTION_MANAGERS or request.user.is_superuser

    return render(request, 'production/production_run_detail.html', {
        'run': run,
        'raw_material_items': raw_material_items,
        'packaging_items': packaging_items,
        'audit_logs': audit_logs,
        'can_manage': can_manage,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_edit_view(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if request.method == 'POST':
        form = ProductionRunEditForm(request.POST, instance=run)
        if form.is_valid():
            reason = form.cleaned_data['edit_reason']
            updated_run = form.save(commit=False)
            updated_run.updated_by = request.user
            updated_run.save()
            log_run_action(
                run=updated_run,
                action='Edited',
                user=request.user,
                details=f"Reason: {reason}",
            )
            messages.success(request, f"Production Run {run.run_number} updated successfully. Edit logged.")
            return redirect('production:production_run_detail', pk=run.pk)
    else:
        form = ProductionRunEditForm(instance=run)

    return render(request, 'production/production_run_edit.html', {
        'run': run,
        'form': form,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_issue_view(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if run.status != ProductionRun.Status.DRAFT:
        messages.error(request, f"Cannot issue materials for run {run.run_number}: status is {run.get_status_display()}.")
        return redirect('production:production_run_detail', pk=run.pk)

    raw_items = run.items.filter(raw_material__isnull=False).select_related('raw_material', 'unit')

    if request.method == 'POST':
        issues_data = []
        has_errors = False
        for item in raw_items:
            qty_field = f"qty_{item.id}"
            cost_field = f"cost_{item.id}"
            val = request.POST.get(qty_field)
            cost_val = request.POST.get(cost_field)
            if val is not None and str(val).strip() != '':
                raw_cost = cost_val if (cost_val and str(cost_val).strip() != '') else item.unit_cost
                form = ProductionIssueItemForm({
                    'item_id': item.id,
                    'actual_quantity': str(val).strip(),
                    'unit_cost': str(raw_cost).strip() if raw_cost is not None else None,
                })
                if form.is_valid():
                    issues_data.append({
                        'item_id': item.id,
                        'actual_quantity': form.cleaned_data['actual_quantity'],
                        'unit_cost': form.cleaned_data['unit_cost'] if form.cleaned_data.get('unit_cost') is not None else item.unit_cost,
                    })
                else:
                    has_errors = True
                    messages.error(request, f"Invalid value for {item.raw_material.name}: {form.errors}")

        if not has_errors:
            try:
                movements = issue_materials_for_run(run, issues_data=issues_data, user=request.user)
                messages.success(request, f"Successfully issued materials for {run.run_number}. {len(movements)} stock ledger movements recorded.")
                return redirect('production:production_run_detail', pk=run.pk)
            except Exception as e:
                messages.error(request, f"Error issuing materials: {str(e)}")
    else:
        # Pre-fill unit_cost with weighted average if currently unset or matching standard
        for item in raw_items:
            if item.unit_cost <= Decimal('0') or item.unit_cost == getattr(item.raw_material, 'standard_cost', Decimal('0')):
                avg_cost = get_weighted_average_unit_cost(item.raw_material)
                if avg_cost > Decimal('0'):
                    item.unit_cost = avg_cost

    return render(request, 'production/production_run_issue.html', {
        'run': run,
        'raw_items': raw_items,
    })


@login_required
@role_required(PRODUCTION_MANAGERS)
def production_run_output_view(request, pk):
    run = get_object_or_404(ProductionRun, pk=pk)
    if run.status != ProductionRun.Status.IN_PROGRESS:
        messages.error(request, f"Cannot record output for run {run.run_number}: status is {run.get_status_display()}.")
        return redirect('production:production_run_detail', pk=run.pk)

    if request.method == 'POST':
        form = ProductionOutputForm(request.POST)
        if form.is_valid():
            actual_yield = form.cleaned_data['actual_yield']
            damaged = form.cleaned_data['damaged_pouches']
            cartons = form.cleaned_data['cartons_used']
            labour = form.cleaned_data['labour_cost'] or Decimal('0.00')
            overhead = form.cleaned_data['overhead_cost'] or Decimal('0.00')
            comp_date = form.cleaned_data['completion_date']

            try:
                movements = record_production_output(
                    run=run,
                    actual_yield=actual_yield,
                    damaged_pouches=damaged,
                    cartons_used=cartons,
                    labour_cost=labour,
                    overhead_cost=overhead,
                    completion_date=comp_date,
                    user=request.user,
                )
                messages.success(request, f"Production Run {run.run_number} completed! {actual_yield} good packets produced. {len(movements)} stock movements recorded.")
                return redirect('production:production_run_detail', pk=run.pk)
            except Exception as e:
                messages.error(request, f"Error completing production run: {e}")
    else:
        carton_pack = run.product.carton_pack_qty or 20
        init_cartons = (run.expected_yield + carton_pack - 1) // carton_pack
        form = ProductionOutputForm(initial={
            'actual_yield': run.expected_yield,
            'damaged_pouches': 0,
            'cartons_used': init_cartons,
            'labour_cost': Decimal('0.00'),
            'overhead_cost': Decimal('0.00'),
        })

    return render(request, 'production/production_run_output.html', {
        'run': run,
        'form': form,
    })


@login_required
@role_required(PRODUCTION_VIEWERS)
def product_costing_view(request):
    """
    Product Costing page: lists the latest run-level cost per packet,
    selling price, and margin for each finished product.
    """
    products = Product.objects.filter(is_active=True).select_related('unit').order_by('name')
    costing_data = []

    for prod in products:
        latest_run = (
            prod.production_runs
            .filter(status=ProductionRun.Status.COMPLETED)
            .order_by('-completion_date', '-id')
            .first()
        )
        costing_data.append({
            'product': prod,
            'latest_run': latest_run,
            'cost_per_packet': latest_run.actual_cost_per_packet if latest_run else None,
            'selling_price': prod.selling_price,
            'margin_per_packet': latest_run.margin_per_packet if latest_run else None,
            'margin_pct': latest_run.margin_pct if latest_run else None,
            'raw_material_cost': latest_run.total_raw_material_cost if latest_run else None,
            'packaging_cost': latest_run.total_packaging_cost if latest_run else None,
            'labour_cost': latest_run.labour_cost if latest_run else None,
            'overhead_cost': latest_run.overhead_cost if latest_run else None,
            'total_production_cost': latest_run.total_production_cost if latest_run else None,
        })

    return render(request, 'production/product_costing.html', {
        'costing_data': costing_data,
    })


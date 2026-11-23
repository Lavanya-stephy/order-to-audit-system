from datetime import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import role_required
from masters.models import Customer, Supplier, Product
from invoices.models import Payment, InvoiceStatus
from invoices.services import get_ageing_report
from inventory.services import get_stock_summary

from .services import (
    parse_report_dates,
    get_sales_register_data,
    get_gst_summary_data,
    get_purchase_register_data,
    get_production_variance_report_data,
)
from .exporters import (
    export_sales_register_csv,
    export_customer_sales_csv,
    export_product_sales_csv,
    export_gst_summary_csv,
    export_purchase_register_csv,
    export_stock_summary_csv,
    export_production_variance_csv,
    export_ageing_report_csv,
    export_payments_csv,
)
from .pdf import (
    build_sales_register_pdf,
    build_gst_summary_pdf,
    build_purchase_register_pdf,
    build_stock_summary_pdf,
    build_production_variance_pdf,
    build_ageing_report_pdf,
)

REPORT_AUDIT_VIEWERS = [Role.ADMIN, Role.ACCOUNTANT, Role.OWNER]
REPORT_ALL_VIEWERS = [Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.PRODUCTION]


def _format_period(start_date, end_date) -> str:
    if start_date and end_date:
        return f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}"
    elif start_date:
        return f"From {start_date.strftime('%d %b %Y')}"
    elif end_date:
        return f"Up to {end_date.strftime('%d %b %Y')}"
    return "All Time"


# ---------------------------------------------------------------------------
# Reports Hub (Auditor & Accounts Dashboard)
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_ALL_VIEWERS)
def reports_hub_view(request):
    """
    Central hub for Section 4.6 Reports for accounts and audit.
    Shows summary cards, date selectors, and quick-download actions.
    """
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)

    # Quick overview metrics
    sales_data = get_sales_register_data(start_date=start_date, end_date=end_date)
    gst_data = get_gst_summary_data(start_date=start_date, end_date=end_date)
    purchases_data = get_purchase_register_data(start_date=start_date, end_date=end_date)
    production_data = get_production_variance_report_data(start_date=start_date, end_date=end_date)
    ageing_data = get_ageing_report(as_of_date=end_date or timezone.localdate())

    context = {
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': _format_period(start_date, end_date),
        'sales_totals': sales_data['totals'],
        'gst_3_1': gst_data['gstr3b_3_1'],
        'purchases_totals': purchases_data['totals'],
        'production_totals': production_data['totals'],
        'ageing_summary': ageing_data['summary'],
        'is_accountant': request.user.role == Role.ACCOUNTANT,
    }
    return render(request, 'reports/hub.html', context)


# ---------------------------------------------------------------------------
# 1. Sales Register, Customer-wise & Product-wise
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_AUDIT_VIEWERS)
def sales_register_view(request):
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)
    customer_id = request.GET.get('customer')
    status_filter = request.GET.get('status', 'all')
    tab = request.GET.get('tab', 'invoices')  # 'invoices', 'customer', 'product'
    export_fmt = request.GET.get('export', '').lower()

    cid = int(customer_id) if customer_id and customer_id.isdigit() else None
    data = get_sales_register_data(
        start_date=start_date,
        end_date=end_date,
        customer_id=cid,
        status_filter=status_filter,
    )

    period_label = _format_period(start_date, end_date)

    if export_fmt == 'csv':
        if tab == 'customer':
            return export_customer_sales_csv(data)
        elif tab == 'product':
            return export_product_sales_csv(data)
        return export_sales_register_csv(data)
    elif export_fmt == 'pdf':
        buf = build_sales_register_pdf(data, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="sales_register.pdf"'
        return response

    context = {
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': period_label,
        'selected_customer': cid,
        'selected_status': status_filter,
        'tab': tab,
        'data': data,
        'customers': Customer.objects.order_by('name'),
        'statuses': [('all', 'All Statuses')] + list(InvoiceStatus.choices),
    }
    return render(request, 'reports/sales_register.html', context)


# ---------------------------------------------------------------------------
# 2. GST Summary (GSTR-1 & GSTR-3B)
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_AUDIT_VIEWERS)
def gst_summary_view(request):
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)
    export_fmt = request.GET.get('export', '').lower()

    data = get_gst_summary_data(start_date=start_date, end_date=end_date)
    period_label = _format_period(start_date, end_date)

    if export_fmt == 'csv':
        return export_gst_summary_csv(data)
    elif export_fmt == 'pdf':
        buf = build_gst_summary_pdf(data, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="gst_outward_supplies_summary.pdf"'
        return response

    context = {
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': period_label,
        'data': data,
    }
    return render(request, 'reports/gst_summary.html', context)


# ---------------------------------------------------------------------------
# 3. Purchase Register
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_ALL_VIEWERS)
def purchase_register_view(request):
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)
    supplier_id = request.GET.get('supplier')
    status_filter = request.GET.get('status', 'all')
    export_fmt = request.GET.get('export', '').lower()

    sid = int(supplier_id) if supplier_id and supplier_id.isdigit() else None
    data = get_purchase_register_data(
        start_date=start_date,
        end_date=end_date,
        supplier_id=sid,
        status_filter=status_filter,
    )
    period_label = _format_period(start_date, end_date)

    if export_fmt == 'csv':
        return export_purchase_register_csv(data)
    elif export_fmt == 'pdf':
        buf = build_purchase_register_pdf(data, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="purchase_register.pdf"'
        return response

    context = {
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': period_label,
        'selected_supplier': sid,
        'selected_status': status_filter,
        'data': data,
        'suppliers': Supplier.objects.order_by('name'),
    }
    return render(request, 'reports/purchase_register.html', context)


# ---------------------------------------------------------------------------
# 4. Stock Summary & Stock Ledger Report
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_ALL_VIEWERS)
def stock_report_view(request):
    category_filter = request.GET.get('category', 'all')
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)
    export_fmt = request.GET.get('export', '').lower()

    # Pass aware datetimes to inventory get_stock_summary
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time())) if start_date else None
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time())) if end_date else None

    summary_rows = get_stock_summary(
        item_type_filter=category_filter,
        start_date=start_dt,
        end_date=end_dt
    )
    period_label = _format_period(start_date, end_date)

    if export_fmt == 'csv':
        return export_stock_summary_csv(summary_rows)
    elif export_fmt == 'pdf':
        buf = build_stock_summary_pdf(summary_rows, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="stock_summary_report.pdf"'
        return response

    total_valuation = sum((r['valuation'] for r in summary_rows), Decimal('0.00'))
    low_stock_count = sum((1 for r in summary_rows if r['is_low_stock']))

    context = {
        'summary_rows': summary_rows,
        'selected_category': category_filter,
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': period_label,
        'total_items_count': len(summary_rows),
        'total_valuation': total_valuation,
        'low_stock_count': low_stock_count,
    }
    return render(request, 'reports/stock_report.html', context)


# ---------------------------------------------------------------------------
# 5. Production Variance & Wastage Report
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_ALL_VIEWERS)
def production_variance_report_view(request):
    start_date, end_date, start_str, end_str, preset = parse_report_dates(request)
    product_id = request.GET.get('product')
    status_filter = request.GET.get('status', 'all')
    export_fmt = request.GET.get('export', '').lower()

    pid = int(product_id) if product_id and product_id.isdigit() else None
    data = get_production_variance_report_data(
        start_date=start_date,
        end_date=end_date,
        product_id=pid,
        status_filter=status_filter,
    )
    period_label = _format_period(start_date, end_date)

    if export_fmt == 'csv':
        return export_production_variance_csv(data)
    elif export_fmt == 'pdf':
        buf = build_production_variance_pdf(data, period_str=period_label)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="production_variance_report.pdf"'
        return response

    context = {
        'start_date': start_str,
        'end_date': end_str,
        'preset': preset,
        'period_label': period_label,
        'selected_product': pid,
        'selected_status': status_filter,
        'data': data,
        'products': Product.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'reports/production_variance.html', context)


# ---------------------------------------------------------------------------
# 6. Receivables, Ageing & Payments
# ---------------------------------------------------------------------------

@login_required
@role_required(REPORT_AUDIT_VIEWERS)
def receivables_ageing_view(request):
    as_of_str = request.GET.get('as_of_date', '').strip()
    export_fmt = request.GET.get('export', '').lower()
    tab = request.GET.get('tab', 'ageing')  # 'ageing' or 'payments'

    as_of_date = None
    if as_of_str:
        try:
            as_of_date = datetime.strptime(as_of_str, '%Y-%m-%d').date()
        except ValueError:
            as_of_date = timezone.localdate()
    else:
        as_of_date = timezone.localdate()

    report_data = get_ageing_report(as_of_date=as_of_date)

    payments = (
        Payment.objects
        .select_related('invoice', 'customer', 'recorded_by')
        .order_by('-payment_date', '-created_at')
    )
    total_received = sum((p.amount for p in payments), Decimal('0.00'))

    if export_fmt == 'csv':
        if tab == 'payments':
            return export_payments_csv(list(payments))
        return export_ageing_report_csv(report_data, as_of_date)
    elif export_fmt == 'pdf':
        buf = build_ageing_report_pdf(report_data, as_of_date)
        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="accounts_receivable_ageing_{as_of_date}.pdf"'
        return response

    context = {
        'as_of_date': as_of_date,
        'tab': tab,
        'summary': report_data['summary'],
        'customers': report_data['customers'],
        'invoices': report_data['invoices'],
        'payments': payments,
        'total_received': total_received,
    }
    return render(request, 'reports/receivables_ageing.html', context)

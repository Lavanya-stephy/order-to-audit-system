from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role
from accounts.permissions import role_required
from orders.models import SalesOrder, OrderStatus
from masters.models import Customer
from .models import Invoice, InvoiceStatus, Payment, PaymentMode
from .services import (
    generate_invoice,
    dispatch_invoice,
    cancel_invoice,
    record_payment,
    get_ageing_report,
    get_customer_outstanding_balance,
)
from .pdf import build_invoice_pdf
from .forms import PaymentForm

INVOICE_VIEWERS  = [Role.ADMIN, Role.ACCOUNTANT, Role.OWNER]
INVOICE_MANAGERS = [Role.ADMIN]
PAYMENT_MANAGERS = [Role.ADMIN, Role.ACCOUNTANT]


# ---------------------------------------------------------------------------
# Invoice List
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def invoice_list_view(request):
    invoices = (
        Invoice.objects
        .select_related('customer', 'order', 'created_by')
        .order_by('-invoice_date', '-invoice_number')
    )
    status_filter = request.GET.get('status', 'all')
    if status_filter and status_filter != 'all':
        invoices = invoices.filter(status=status_filter)

    return render(request, 'invoices/invoice_list.html', {
        'invoices': invoices,
        'current_status': status_filter,
        'can_manage': request.user.role == Role.ADMIN or request.user.is_superuser,
    })


# ---------------------------------------------------------------------------
# Invoice Detail
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def invoice_detail_view(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'order', 'created_by', 'cancelled_by')
        .prefetch_related('lines', 'lines__product', 'lines__unit', 'payments', 'payments__recorded_by'),
        pk=pk,
    )
    can_manage = request.user.role == Role.ADMIN or request.user.is_superuser
    can_record_payment = (
        (request.user.role in PAYMENT_MANAGERS or request.user.is_superuser)
        and invoice.status == InvoiceStatus.POSTED
        and invoice.outstanding_balance > 0
    )
    payment_form = PaymentForm(invoice=invoice) if can_record_payment else None

    return render(request, 'invoices/invoice_detail.html', {
        'invoice': invoice,
        'payments': invoice.payments.select_related('recorded_by').order_by('-payment_date', '-created_at'),
        'payment_form': payment_form,
        'can_record_payment': can_record_payment,
        'can_dispatch': can_manage and invoice.status == InvoiceStatus.POSTED and not invoice.is_dispatched,
        'can_cancel': can_manage and invoice.status == InvoiceStatus.POSTED,
        'can_manage': can_manage,
    })


# ---------------------------------------------------------------------------
# Generate Invoice from an Approved Order
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_MANAGERS)
@require_POST
def invoice_generate_view(request, order_pk):
    order = get_object_or_404(SalesOrder, pk=order_pk)
    try:
        invoice = generate_invoice(order, user=request.user)
        messages.success(request, f"Invoice {invoice.invoice_number} generated successfully.")
        return redirect('invoices:invoice_detail', pk=invoice.pk)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('orders:order_detail', pk=order_pk)


# ---------------------------------------------------------------------------
# Dispatch Invoice
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_MANAGERS)
@require_POST
def invoice_dispatch_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    try:
        dispatch_invoice(invoice, user=request.user)
        messages.success(
            request,
            f"Invoice {invoice.invoice_number} dispatched. Finished-goods stock updated in ledger."
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('invoices:invoice_detail', pk=pk)


# ---------------------------------------------------------------------------
# Cancel Invoice (Credit Note)
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_MANAGERS)
@require_POST
def invoice_cancel_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    reason = request.POST.get('cancellation_reason', '').strip()
    if not reason:
        messages.error(request, "A cancellation reason is required.")
        return redirect('invoices:invoice_detail', pk=pk)
    try:
        cancel_invoice(invoice, reason=reason, user=request.user)
        messages.success(
            request,
            f"Invoice {invoice.invoice_number} cancelled. Credit Note {invoice.credit_note_number} issued."
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('invoices:invoice_detail', pk=pk)


# ---------------------------------------------------------------------------
# PDF Download
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'order')
        .prefetch_related('lines', 'lines__product', 'lines__unit'),
        pk=pk,
    )
    buf = build_invoice_pdf(invoice)
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="{invoice.invoice_number}.pdf"'
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


# ---------------------------------------------------------------------------
# Record Payment View
# ---------------------------------------------------------------------------

@login_required
@role_required(PAYMENT_MANAGERS)
@require_POST
def invoice_record_payment_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    form = PaymentForm(request.POST, invoice=invoice)
    if form.is_valid():
        try:
            payment = record_payment(
                invoice=invoice,
                amount=form.cleaned_data['amount'],
                payment_date=form.cleaned_data['payment_date'],
                payment_mode=form.cleaned_data['payment_mode'],
                reference_number=form.cleaned_data['reference_number'],
                notes=form.cleaned_data['notes'],
                user=request.user,
            )
            messages.success(
                request,
                f"Payment receipt {payment.payment_number} for ₹{payment.amount} recorded successfully. "
                f"Remaining outstanding balance: ₹{invoice.outstanding_balance}"
            )
        except ValueError as e:
            messages.error(request, str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.capitalize()}: {error}")

    return redirect('invoices:invoice_detail', pk=pk)


# ---------------------------------------------------------------------------
# Payments List View
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def payment_list_view(request):
    payments = (
        Payment.objects
        .select_related('invoice', 'customer', 'recorded_by')
        .order_by('-payment_date', '-created_at')
    )
    customer_id = request.GET.get('customer')
    if customer_id:
        payments = payments.filter(customer_id=customer_id)

    total_received = sum(p.amount for p in payments)

    return render(request, 'invoices/payment_list.html', {
        'payments': payments,
        'total_received': total_received,
        'selected_customer': customer_id,
        'customers': Customer.objects.order_by('name'),
    })


# ---------------------------------------------------------------------------
# Customer Outstanding Balances View
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def customer_balances_view(request):
    """
    Shows outstanding accounts receivable balance per customer.
    """
    customers = Customer.objects.all().order_by('name')
    customer_balances = []
    total_receivables = 0
    total_invoiced_all = 0
    total_paid_all = 0

    for cust in customers:
        inv_total = cust.total_invoiced
        paid_total = cust.total_paid
        bal = cust.outstanding_balance
        total_invoiced_all += inv_total
        total_paid_all += paid_total
        total_receivables += bal

        customer_balances.append({
            'customer': cust,
            'total_invoiced': inv_total,
            'total_paid': paid_total,
            'outstanding_balance': bal,
            'has_outstanding': bal > 0,
        })

    return render(request, 'invoices/customer_balances.html', {
        'customer_balances': customer_balances,
        'total_receivables': total_receivables,
        'total_invoiced_all': total_invoiced_all,
        'total_paid_all': total_paid_all,
    })


# ---------------------------------------------------------------------------
# Accounts Receivable Ageing Report View
# ---------------------------------------------------------------------------

@login_required
@role_required(INVOICE_VIEWERS)
def ageing_report_view(request):
    """
    Accounts Receivable (AR) Ageing Report:
    Groups unpaid invoice balances into 0-30, 31-60, 61-90, 90+ day buckets.
    """
    as_of_str = request.GET.get('as_of_date')
    as_of_date = None
    if as_of_str:
        try:
            as_of_date = datetime.strptime(as_of_str, '%Y-%m-%d').date()
        except ValueError:
            as_of_date = timezone.localdate()
    else:
        as_of_date = timezone.localdate()

    report_data = get_ageing_report(as_of_date=as_of_date)

    return render(request, 'invoices/ageing_report.html', {
        'as_of_date': as_of_date,
        'summary': report_data['summary'],
        'customers': report_data['customers'],
        'invoices': report_data['invoices'],
    })


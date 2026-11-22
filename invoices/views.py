from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from accounts.models import Role
from accounts.permissions import role_required
from orders.models import SalesOrder, OrderStatus
from .models import Invoice, InvoiceStatus
from .services import generate_invoice, dispatch_invoice, cancel_invoice
from .pdf import build_invoice_pdf

INVOICE_VIEWERS  = [Role.ADMIN, Role.ACCOUNTANT, Role.OWNER]
INVOICE_MANAGERS = [Role.ADMIN]


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
        .prefetch_related('lines', 'lines__product', 'lines__unit'),
        pk=pk,
    )
    can_manage = request.user.role == Role.ADMIN or request.user.is_superuser
    return render(request, 'invoices/invoice_detail.html', {
        'invoice': invoice,
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

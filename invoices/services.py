"""
invoices/services.py

Business logic for GST Tax Invoice lifecycle:
  generate_invoice()   – create posted invoice from an approved SalesOrder
  dispatch_invoice()   – reduce finished-goods stock, mark order dispatched
  cancel_invoice()     – credit-note cancellation (never deletes the invoice)

Invoice numbering: INV-YYYY-YY-NNNN  (Indian FY April–March)
Credit notes:      CN-YYYY-YY-NNNN
"""
from decimal import Decimal
from datetime import date

from django.db import transaction
from django.utils import timezone

from orders.models import SalesOrder, SalesOrderLog, OrderStatus
from inventory.models import MovementType
from inventory.services import record_movement
from .models import Invoice, InvoiceLine, InvoiceStatus, FACTORY_STATE_CODE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _financial_year(d: date) -> str:
    """Returns 'YYYY-YY' string for the Indian financial year containing date d."""
    if d.month >= 4:
        return f"{d.year}-{str(d.year + 1)[2:]}"
    return f"{d.year - 1}-{str(d.year)[2:]}"


def _next_invoice_sequence(prefix: str) -> str:
    """
    Finds the next sequential number for invoices with the given prefix
    (e.g. 'INV-2026-27-') and returns the full invoice number string.
    Uses SELECT FOR UPDATE within the caller's transaction to avoid races.
    """
    qs = (
        Invoice.objects
        .filter(invoice_number__startswith=prefix)
        .order_by('-invoice_number')
        .select_for_update()
    )
    last = qs.first()
    if last is None:
        seq = 1
    else:
        # e.g. 'INV-2026-27-0042' → 42
        try:
            seq = int(last.invoice_number.rsplit('-', 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:04d}"


def _next_cn_sequence(prefix: str) -> str:
    """Same but for credit notes (uses credit_note_number field)."""
    qs = (
        Invoice.objects
        .filter(credit_note_number__startswith=prefix)
        .order_by('-credit_note_number')
        .select_for_update()
    )
    last = qs.first()
    if last is None:
        seq = 1
    else:
        try:
            seq = int(last.credit_note_number.rsplit('-', 1)[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:04d}"


# ---------------------------------------------------------------------------
# generate_invoice
# ---------------------------------------------------------------------------

@transaction.atomic
def generate_invoice(order: SalesOrder, user=None) -> Invoice:
    """
    Creates and saves a GST Tax Invoice from an *approved* SalesOrder.

    - Determines CGST+SGST vs IGST from customer state.
    - Stores all computed totals for auditability.
    - Transitions order status → invoiced.
    - Logs the action on the order audit trail.

    Raises ValueError if order is not in APPROVED status or already has an invoice.
    """
    if order.status != OrderStatus.APPROVED:
        raise ValueError(
            f"Order {order.order_number} must be APPROVED to generate an invoice "
            f"(current status: {order.get_status_display()})."
        )
    if hasattr(order, 'invoice') and order.invoice is not None:
        raise ValueError(
            f"Order {order.order_number} already has invoice {order.invoice.invoice_number}."
        )

    customer = order.customer
    today = timezone.localdate()
    fy = _financial_year(today)
    inv_prefix = f"INV-{fy}-"
    invoice_number = _next_invoice_sequence(inv_prefix)

    is_interstate = customer.is_interstate(FACTORY_STATE_CODE)

    invoice = Invoice(
        invoice_number=invoice_number,
        order=order,
        customer=customer,
        invoice_date=today,
        status=InvoiceStatus.POSTED,
        is_interstate=is_interstate,
        customer_gstin=customer.gstin or '',
        created_by=user,
    )
    invoice.save()

    taxable_total = Decimal('0.00')
    cgst_total    = Decimal('0.00')
    sgst_total    = Decimal('0.00')
    igst_total    = Decimal('0.00')

    for order_line in order.lines.select_related('product', 'unit').all():
        product = order_line.product
        taxable = (order_line.quantity * order_line.unit_price).quantize(Decimal('0.01'))

        gst_rate = product.gst_rate  # e.g. Decimal('5.00')
        half     = (gst_rate / Decimal('2')).quantize(Decimal('0.01'))

        if is_interstate:
            cgst_r = Decimal('0.00')
            sgst_r = Decimal('0.00')
            igst_r = gst_rate
            cgst_a = Decimal('0.00')
            sgst_a = Decimal('0.00')
            igst_a = (taxable * gst_rate / Decimal('100')).quantize(Decimal('0.01'))
        else:
            cgst_r = half
            sgst_r = half
            igst_r = Decimal('0.00')
            cgst_a = (taxable * half / Decimal('100')).quantize(Decimal('0.01'))
            sgst_a = (taxable * half / Decimal('100')).quantize(Decimal('0.01'))
            igst_a = Decimal('0.00')

        line_total = taxable + cgst_a + sgst_a + igst_a

        InvoiceLine.objects.create(
            invoice=invoice,
            product=product,
            hsn_code=product.hsn_code,
            quantity=order_line.quantity,
            unit=order_line.unit,
            unit_price=order_line.unit_price,
            taxable_value=taxable,
            gst_rate=gst_rate,
            cgst_rate=cgst_r,
            sgst_rate=sgst_r,
            igst_rate=igst_r,
            cgst_amount=cgst_a,
            sgst_amount=sgst_a,
            igst_amount=igst_a,
            line_total=line_total,
        )

        taxable_total += taxable
        cgst_total    += cgst_a
        sgst_total    += sgst_a
        igst_total    += igst_a

    grand_total = taxable_total + cgst_total + sgst_total + igst_total

    invoice.taxable_value = taxable_total
    invoice.cgst_amount   = cgst_total
    invoice.sgst_amount   = sgst_total
    invoice.igst_amount   = igst_total
    invoice.grand_total   = grand_total
    invoice.save()

    # Transition order to invoiced
    order.status = OrderStatus.INVOICED
    order.save(update_fields=['status'])

    SalesOrderLog.objects.create(
        order=order,
        user=user,
        action='Invoiced',
        details=(
            f"Invoice {invoice_number} generated. "
            f"Taxable: ₹{taxable_total} | "
            f"{'IGST' if is_interstate else 'CGST+SGST'}: ₹{grand_total - taxable_total} | "
            f"Grand Total: ₹{grand_total}"
        ),
    )
    return invoice


# ---------------------------------------------------------------------------
# dispatch_invoice
# ---------------------------------------------------------------------------

@transaction.atomic
def dispatch_invoice(invoice: Invoice, user=None) -> Invoice:
    """
    Dispatches an invoiced order:
      1. Reduces finished-goods stock in the ledger (negative DISPATCH movements).
      2. Marks invoice as dispatched.
      3. Transitions order status → dispatched.
      4. Logs the action.

    Raises ValueError if invoice is not in POSTED status or already dispatched.
    """
    if invoice.status != InvoiceStatus.POSTED:
        raise ValueError(f"Invoice {invoice.invoice_number} is not in POSTED status.")
    if invoice.is_dispatched:
        raise ValueError(f"Invoice {invoice.invoice_number} has already been dispatched.")

    order = invoice.order

    for inv_line in invoice.lines.select_related('product', 'unit').all():
        record_movement(
            item=inv_line.product,
            quantity=-inv_line.quantity,
            movement_type=MovementType.DISPATCH,
            source_document=invoice.invoice_number,
            user=user,
            unit_cost=inv_line.unit_price,
            notes=f"Dispatch for invoice {invoice.invoice_number}",
        )

    now = timezone.now()
    invoice.dispatched_at = now
    invoice.dispatch_ledger_note = f"Dispatched on {now.strftime('%Y-%m-%d %H:%M')} by {getattr(user, 'username', 'system')}"
    invoice.save(update_fields=['dispatched_at', 'dispatch_ledger_note'])

    order.status = OrderStatus.DISPATCHED
    order.save(update_fields=['status'])

    SalesOrderLog.objects.create(
        order=order,
        user=user,
        action='Dispatched',
        details=f"Invoice {invoice.invoice_number} dispatched. Finished-goods ledger updated.",
    )
    return invoice


# ---------------------------------------------------------------------------
# cancel_invoice  (credit-note cancellation — never deletes)
# ---------------------------------------------------------------------------

@transaction.atomic
def cancel_invoice(invoice: Invoice, reason: str, user=None) -> Invoice:
    """
    Cancels a posted invoice by issuing a credit note.
    - If already dispatched, reverses the stock movements (adds back to FG).
    - Sets invoice status to CANCELLED; stamps credit_note_number.
    - Transitions order back to APPROVED so it can be re-invoiced if needed.
    - The original Invoice record is never deleted.

    Raises ValueError if invoice is already cancelled.
    """
    if invoice.status == InvoiceStatus.CANCELLED:
        raise ValueError(f"Invoice {invoice.invoice_number} is already cancelled.")

    today = timezone.localdate()
    fy = _financial_year(today)
    cn_prefix = f"CN-{fy}-"
    credit_note_number = _next_cn_sequence(cn_prefix)

    # If dispatched: reverse the ledger movements (add stock back)
    if invoice.is_dispatched:
        for inv_line in invoice.lines.select_related('product', 'unit').all():
            record_movement(
                item=inv_line.product,
                quantity=+inv_line.quantity,
                movement_type=MovementType.RETURN,
                source_document=credit_note_number,
                user=user,
                unit_cost=inv_line.unit_price,
                notes=f"Stock reversal for cancelled invoice {invoice.invoice_number}",
            )

    invoice.status = InvoiceStatus.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.cancellation_reason = reason
    invoice.credit_note_number = credit_note_number
    invoice.cancelled_by = user
    invoice.save(update_fields=[
        'status', 'cancelled_at', 'cancellation_reason',
        'credit_note_number', 'cancelled_by',
    ])

    order = invoice.order
    # Roll order back to approved so it can be re-invoiced
    order.status = OrderStatus.APPROVED
    order.save(update_fields=['status'])

    SalesOrderLog.objects.create(
        order=order,
        user=user,
        action='Invoice Cancelled',
        details=f"Invoice {invoice.invoice_number} cancelled. Credit Note: {credit_note_number}. Reason: {reason}",
    )
    return invoice

from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from masters.models import Customer, Product, Unit
from orders.models import SalesOrder


FACTORY_NAME = getattr(settings, 'FACTORY_NAME', 'Demo Snacks Pvt Ltd')
FACTORY_ADDRESS = getattr(settings, 'FACTORY_ADDRESS', '12 Industrial Estate, Tiruchirappalli - 620001, Tamil Nadu')
FACTORY_STATE_CODE = getattr(settings, 'FACTORY_STATE_CODE', '33')          # Tamil Nadu
FACTORY_STATE_NAME = getattr(settings, 'FACTORY_STATE_NAME', 'Tamil Nadu')
FACTORY_GSTIN = getattr(settings, 'FACTORY_GSTIN', '33AAAAA0000A1Z5')
FACTORY_EVALUATION_NOTE = getattr(settings, 'FACTORY_EVALUATION_NOTE', 'All data in this system is dummy data for evaluation.')


class InvoiceStatus(models.TextChoices):
    POSTED   = 'posted',    'Posted'
    CANCELLED = 'cancelled', 'Cancelled'


class Invoice(models.Model):
    """
    GST Tax Invoice generated from an approved SalesOrder.

    Rules:
      - Intra-state (customer state_code == 33): CGST + SGST (each half of GST rate).
      - Inter-state (all other states)         : IGST (full GST rate).
      - Posted invoices are NEVER deleted; use credit-note cancellation instead.
      - Dispatch reduces finished-goods stock via the inventory ledger.
    """
    invoice_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        help_text='Auto-generated per financial year, e.g. INV-2026-27-0001',
    )
    order = models.OneToOneField(
        SalesOrder,
        on_delete=models.PROTECT,
        related_name='invoice',
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='invoices',
    )
    invoice_date = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=15,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.POSTED,
    )

    # Tax classification (denormalised from customer at invoice time)
    is_interstate = models.BooleanField(
        default=False,
        help_text='True → IGST; False → CGST+SGST',
    )
    customer_gstin = models.CharField(max_length=15, blank=True)

    # Totals (computed and stored for auditability)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cgst_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    sgst_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    igst_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    grand_total   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    # Dispatch tracking
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatch_ledger_note = models.CharField(max_length=200, blank=True)

    # Cancellation / Credit Note
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    credit_note_number = models.CharField(max_length=30, blank=True, editable=False)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='cancelled_invoices',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='created_invoices',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-invoice_number']
        verbose_name = 'GST Tax Invoice'
        verbose_name_plural = 'GST Tax Invoices'

    def __str__(self):
        return f"{self.invoice_number} — {self.customer.name} ({self.get_status_display()})"

    @property
    def total_tax(self) -> Decimal:
        return self.cgst_amount + self.sgst_amount + self.igst_amount

    @property
    def is_dispatched(self) -> bool:
        return self.dispatched_at is not None

    @property
    def amount_paid(self) -> Decimal:
        """Total payments received against this invoice."""
        if self.status == InvoiceStatus.CANCELLED:
            return Decimal('0.00')
        res = self.payments.aggregate(total=models.Sum('amount'))['total']
        return res or Decimal('0.00')

    @property
    def outstanding_balance(self) -> Decimal:
        """Remaining unpaid balance on this invoice."""
        if self.status == InvoiceStatus.CANCELLED:
            return Decimal('0.00')
        bal = self.grand_total - self.amount_paid
        return max(Decimal('0.00'), bal)

    @property
    def is_fully_paid(self) -> bool:
        return self.status == InvoiceStatus.POSTED and self.outstanding_balance == Decimal('0.00')

    @property
    def payment_status(self) -> str:
        if self.status == InvoiceStatus.CANCELLED:
            return 'cancelled'
        paid = self.amount_paid
        if paid <= Decimal('0.00'):
            return 'unpaid'
        elif paid >= self.grand_total:
            return 'paid'
        return 'partially_paid'

    @property
    def payment_status_display(self) -> str:
        mapping = {
            'cancelled': 'Cancelled',
            'unpaid': 'Unpaid',
            'partially_paid': 'Partially Paid',
            'paid': 'Paid',
        }
        return mapping.get(self.payment_status, 'Unpaid')


class InvoiceLine(models.Model):
    """One product line on a GST Tax Invoice."""
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='invoice_lines',
    )
    hsn_code = models.CharField(max_length=15)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='invoice_lines')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2)

    # Tax amounts per line
    cgst_rate   = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    sgst_rate   = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_rate   = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    line_total  = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.invoice.invoice_number}: {self.product.name} × {self.quantity}"


class PaymentMode(models.TextChoices):
    BANK_TRANSFER = 'bank_transfer', 'Bank Transfer (NEFT/RTGS/IMPS)'
    UPI           = 'upi',           'UPI'
    CHEQUE        = 'cheque',        'Cheque'
    CASH          = 'cash',          'Cash'
    OTHER         = 'other',         'Other'


class Payment(models.Model):
    """
    A payment recorded against an Invoice.
    """
    payment_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        help_text='Auto-generated payment receipt number, e.g. PAY-2026-27-0001',
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name='payments',
        help_text='Invoice against which payment is recorded',
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='payments',
        help_text='Customer making the payment',
    )
    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Payment amount in INR',
    )
    payment_mode = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        default=PaymentMode.BANK_TRANSFER,
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Transaction ID, UTR, Cheque number, etc.',
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='recorded_payments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = 'Invoice Payment'
        verbose_name_plural = 'Invoice Payments'

    def __str__(self):
        return f"{self.payment_number} — ₹{self.amount} for {self.invoice.invoice_number}"

    def clean(self):
        if self.amount is not None and self.amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero.")
        if self.invoice_id and self.invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError("Cannot record payment against a cancelled invoice.")
        if self.invoice_id:
            existing_paid = self.invoice.payments.exclude(pk=self.pk).aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0.00')
            remaining = self.invoice.grand_total - existing_paid
            if self.amount is not None and self.amount > remaining:
                raise ValidationError(
                    f"Payment amount (₹{self.amount}) exceeds the remaining invoice balance (₹{remaining})."
                )

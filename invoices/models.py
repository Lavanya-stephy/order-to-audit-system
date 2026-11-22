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

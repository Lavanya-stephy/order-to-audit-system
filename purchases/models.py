from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from masters.models import RawMaterial, PackagingItem, Unit, Supplier


class PurchaseOrder(models.Model):
    """
    A purchase order records the receipt of raw materials or packaging items
    from a supplier. Saving it automatically appends a PURCHASE movement to
    the StockMovement ledger so the balance is always ledger-derived.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        RECEIVED = 'received', 'Received'
        CANCELLED = 'cancelled', 'Cancelled'

    po_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Purchase order / GRN number, e.g. PO-2026-001",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders',
    )
    order_date = models.DateField(default=timezone.now)
    received_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='purchase_orders_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'

    def __str__(self):
        return f"{self.po_number} — {self.supplier.name}"

    @property
    def total_value(self) -> Decimal:
        return sum(
            (line.line_total for line in self.lines.all()),
            Decimal('0.00')
        )


class PurchaseOrderLine(models.Model):
    """
    A single line item in a purchase order. Links to either a RawMaterial
    or a PackagingItem with quantity, unit, and rate per unit.
    When the PO is received, a StockMovement of type PURCHASE is recorded.
    """
    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='purchase_lines',
    )
    packaging_item = models.ForeignKey(
        PackagingItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='purchase_lines',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Quantity purchased",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='purchase_lines',
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Purchase rate per unit in INR (e.g. ₹45.00/kg)",
    )
    # Set to True once record_movement has been called for this line
    movement_recorded = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Purchase Order Line'
        verbose_name_plural = 'Purchase Order Lines'

    def clean(self):
        items_set = [bool(self.raw_material), bool(self.packaging_item)]
        if sum(items_set) != 1:
            raise ValidationError(
                "Each purchase line must link to exactly one item "
                "(Raw Material or Packaging Item)."
            )
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError("Quantity must be positive.")
        if self.unit_price is not None and self.unit_price <= Decimal('0'):
            raise ValidationError("Unit price must be positive.")

    @property
    def item(self):
        return self.raw_material or self.packaging_item

    @property
    def item_name(self) -> str:
        return self.item.name if self.item else ''

    @property
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.item_name}: {self.quantity} {self.unit.symbol} @ ₹{self.unit_price}"

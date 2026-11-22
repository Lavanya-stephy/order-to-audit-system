from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from masters.models import RawMaterial, PackagingItem, Product, Unit


class MovementType(models.TextChoices):
    OPENING = 'opening', 'Opening Balance'
    PURCHASE = 'purchase', 'Purchase Receipt'
    PRODUCTION_ISSUE = 'production_issue', 'Production Issue (Raw Material/Packaging)'
    PRODUCTION_OUTPUT = 'production_output', 'Production Output (Finished Goods)'
    DISPATCH = 'dispatch', 'Sales Dispatch'
    ADJUSTMENT = 'adjustment', 'Stock Adjustment (Physical Audit)'
    RETURN = 'return', 'Stock Return'


class StockMovement(models.Model):
    raw_material = models.ForeignKey(
        RawMaterial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='stock_movements'
    )
    packaging_item = models.ForeignKey(
        PackagingItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='stock_movements'
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='stock_movements'
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Signed quantity: positive for inward/receipts (+), negative for outward/issues (-)"
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        help_text="Unit of measure for this movement"
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Unit cost/rate at movement time in INR"
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MovementType.choices,
        help_text="Operational transaction type"
    )
    source_document = models.CharField(
        max_length=100,
        help_text="Source document reference e.g. PO-001, RUN-001, INV-2026-001, ADJ-001"
    )
    batch_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Batch or Lot number for traceability"
    )
    notes = models.TextField(blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recorded_stock_movements'
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'

    def clean(self):
        items_set = [bool(self.raw_material), bool(self.packaging_item), bool(self.product)]
        if sum(items_set) != 1:
            raise ValidationError(
                "A StockMovement must link to exactly one item (Raw Material, Packaging Item, or Product)."
            )
        if self.quantity == Decimal('0'):
            raise ValidationError("Movement quantity cannot be zero.")

    @property
    def item(self):
        return self.raw_material or self.packaging_item or self.product

    @property
    def item_type(self) -> str:
        if self.raw_material:
            return 'Raw Material'
        elif self.packaging_item:
            return 'Packaging'
        elif self.product:
            return 'Finished Good'
        return 'Unknown'

    @property
    def item_code(self) -> str:
        item = self.item
        return item.code if item else ''

    @property
    def item_name(self) -> str:
        item = self.item
        return item.name if item else ''

    @property
    def is_inward(self) -> bool:
        return self.quantity > Decimal('0')

    @property
    def is_outward(self) -> bool:
        return self.quantity < Decimal('0')

    @property
    def inward_quantity(self) -> Decimal:
        return self.quantity if self.is_inward else Decimal('0.0000')

    @property
    def outward_quantity(self) -> Decimal:
        return abs(self.quantity) if self.is_outward else Decimal('0.0000')

    def __str__(self):
        direction = "+" if self.is_inward else ""
        return f"{self.item_name}: {direction}{self.quantity} {self.unit.symbol} ({self.get_movement_type_display()} - {self.source_document})"

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from masters.models import Product, BillOfMaterial, RawMaterial, PackagingItem, Unit

User = get_user_model()

VARIANCE_TOLERANCE_PCT = Decimal('3.00')


class ProductionRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft / Planned'
        IN_PROGRESS = 'in_progress', 'In Progress (Materials Issued)'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    run_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique production run identifier, e.g. PR-20261122-0001"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='production_runs'
    )
    bom = models.ForeignKey(
        BillOfMaterial,
        on_delete=models.PROTECT,
        related_name='production_runs'
    )
    batch_multiplier = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Number of standard batches (e.g. 1.00 for 1 standard batch)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )
    start_date = models.DateField(default=timezone.now)
    completion_date = models.DateField(null=True, blank=True)

    expected_yield = models.PositiveIntegerField(
        help_text="Expected output packets calculated from BOM and batch multiplier"
    )
    actual_yield = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Actual good output packets produced"
    )
    damaged_pouches = models.PositiveIntegerField(
        default=0,
        help_text="Number of pouches damaged during packing"
    )
    cartons_used = models.PositiveIntegerField(
        default=0,
        help_text="Number of outer shipping cartons used"
    )

    # Costing elements (Problem Section 4.5 & Step 8)
    labour_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Direct labour cost allocated to this run (₹)"
    )
    overhead_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Power, gas, and other overhead costs allocated to this run (₹)"
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_production_runs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Production Run'
        verbose_name_plural = 'Production Runs'

    def __str__(self):
        return f"{self.run_number} - {self.product.name} ({self.get_status_display()})"

    @property
    def yield_variance_packets(self) -> int:
        """Difference between actual yield and expected yield in packets."""
        if self.actual_yield is None:
            return 0
        return self.actual_yield - self.expected_yield

    @property
    def yield_variance_pct(self) -> Decimal:
        """
        Yield variance percentage = ((actual_yield - expected_yield) / expected_yield) * 100
        Negative means shortfall (e.g. -6.00%).
        """
        if self.actual_yield is None or not self.expected_yield:
            return Decimal('0.00')
        diff = Decimal(str(self.actual_yield - self.expected_yield))
        return ((diff / Decimal(str(self.expected_yield))) * Decimal('100')).quantize(Decimal('0.01'))

    @property
    def is_yield_variance_flagged(self) -> bool:
        """Returns True if yield variance exceeds tolerance (3%)."""
        if self.actual_yield is None:
            return False
        return abs(self.yield_variance_pct) > VARIANCE_TOLERANCE_PCT

    @property
    def total_raw_material_cost(self) -> Decimal:
        """Sum of actual costs for raw materials consumed."""
        total = Decimal('0.00')
        for item in self.items.filter(raw_material__isnull=False):
            total += item.actual_cost
        return total.quantize(Decimal('0.01'))

    @property
    def total_packaging_cost(self) -> Decimal:
        """Sum of actual costs for packaging consumed."""
        total = Decimal('0.00')
        for item in self.items.filter(packaging_item__isnull=False):
            total += item.actual_cost
        return total.quantize(Decimal('0.01'))

    @property
    def total_material_cost(self) -> Decimal:
        """Sum of raw material and packaging costs."""
        return (self.total_raw_material_cost + self.total_packaging_cost).quantize(Decimal('0.01'))

    @property
    def total_production_cost(self) -> Decimal:
        """Material cost + Labour + Overheads."""
        return (self.total_material_cost + self.labour_cost + self.overhead_cost).quantize(Decimal('0.01'))

    @property
    def actual_cost_per_packet(self) -> Decimal:
        """Actual total cost divided by actual good packets produced."""
        if self.actual_yield and self.actual_yield > 0:
            return (self.total_production_cost / Decimal(str(self.actual_yield))).quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def margin_per_packet(self) -> Decimal:
        """Selling price minus actual cost per packet."""
        if self.product and self.product.selling_price:
            return (self.product.selling_price - self.actual_cost_per_packet).quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def margin_pct(self) -> Decimal:
        """Profit margin as percentage of selling price."""
        if self.product and self.product.selling_price and self.product.selling_price > Decimal('0.00'):
            return ((self.margin_per_packet / self.product.selling_price) * Decimal('100')).quantize(Decimal('0.01'))
        return Decimal('0.00')


class ProductionRunItem(models.Model):
    run = models.ForeignKey(
        ProductionRun,
        on_delete=models.CASCADE,
        related_name='items'
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='production_run_items'
    )
    packaging_item = models.ForeignKey(
        PackagingItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='production_run_items'
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='production_run_items'
    )
    standard_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Standard recipe quantity from BOM"
    )
    actual_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Actual quantity issued / consumed"
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Rate per unit used for costing (₹)"
    )
    movement_recorded = models.BooleanField(
        default=False,
        help_text="True if StockMovement ledger entry has been recorded"
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Production Run Item'
        verbose_name_plural = 'Production Run Items'

    def clean(self):
        if not self.raw_material and not self.packaging_item:
            raise ValidationError("Item must specify either a Raw Material or a Packaging Item.")
        if self.raw_material and self.packaging_item:
            raise ValidationError("Item cannot specify both a Raw Material and a Packaging Item.")

    @property
    def item(self):
        return self.raw_material or self.packaging_item

    @property
    def item_name(self) -> str:
        return self.raw_material.name if self.raw_material else self.packaging_item.name

    @property
    def item_code(self) -> str:
        return self.raw_material.code if self.raw_material else self.packaging_item.code

    @property
    def item_type(self) -> str:
        return 'Raw Material' if self.raw_material else 'Packaging Item'

    @property
    def consumption_variance_quantity(self) -> Decimal:
        """Actual quantity minus standard quantity."""
        return (self.actual_quantity - self.standard_quantity).quantize(Decimal('0.0001'))

    @property
    def consumption_variance_pct(self) -> Decimal:
        """
        Consumption variance percentage = ((actual - standard) / standard) * 100
        Positive means over-consumption (e.g. +5.00% for oil).
        """
        if not self.standard_quantity or self.standard_quantity == Decimal('0.0000'):
            return Decimal('0.00')
        diff = self.actual_quantity - self.standard_quantity
        return ((diff / self.standard_quantity) * Decimal('100')).quantize(Decimal('0.01'))

    @property
    def is_variance_flagged(self) -> bool:
        """Flagged if consumption variance exceeds tolerance (3%)."""
        return abs(self.consumption_variance_pct) > VARIANCE_TOLERANCE_PCT

    @property
    def standard_cost(self) -> Decimal:
        return (self.standard_quantity * self.unit_cost).quantize(Decimal('0.01'))

    @property
    def actual_cost(self) -> Decimal:
        return (self.actual_quantity * self.unit_cost).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.item_name}: Std {self.standard_quantity} | Act {self.actual_quantity} {self.unit.symbol}"

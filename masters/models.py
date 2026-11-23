from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError


class UnitCategory(models.TextChoices):
    WEIGHT = 'weight', 'Weight (kg, g, etc.)'
    VOLUME = 'volume', 'Volume (litre, ml, etc.)'
    COUNT = 'count', 'Count / Discrete (piece, packet, carton)'


class Unit(models.Model):
    name = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=15, unique=True, help_text="e.g., kg, g, litre, ml, piece, packet, carton")
    category = models.CharField(max_length=20, choices=UnitCategory.choices, default=UnitCategory.COUNT)
    to_base_factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        help_text="Multiplier to convert into the standard reference base of this category (e.g. 0.001 for g to kg)."
    )

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.symbol})"

    def convert_to(self, quantity: Decimal, target_unit: 'Unit') -> Decimal:
        """Convenience instance method converting a quantity of this unit to target_unit."""
        return Unit.convert(quantity, self, target_unit)

    @classmethod
    def convert(cls, quantity: Decimal, from_unit: 'Unit', to_unit: 'Unit') -> Decimal:
        """
        Converts quantity from from_unit to to_unit using:
        1. Direct or reverse explicit UnitConversion rule.
        2. Standard metric category base ratio (for weight and volume).
        Raises ValueError if units are incompatible.
        """
        if not isinstance(quantity, Decimal):
            quantity = Decimal(str(quantity))

        if from_unit.id == to_unit.id or from_unit.symbol.strip().lower() == to_unit.symbol.strip().lower():
            return quantity

        # 1. Direct explicit conversion rule
        direct = UnitConversion.objects.filter(from_unit=from_unit, to_unit=to_unit).first()
        if direct:
            return quantity * direct.factor

        # 2. Reverse explicit conversion rule
        reverse = UnitConversion.objects.filter(from_unit=to_unit, to_unit=from_unit).first()
        if reverse:
            if reverse.factor == Decimal('0'):
                raise ZeroDivisionError("Conversion factor cannot be zero.")
            return quantity / reverse.factor

        # 3. Standard category ratio (weight / volume)
        if from_unit.category == to_unit.category and from_unit.category != UnitCategory.COUNT:
            if to_unit.to_base_factor == Decimal('0'):
                raise ZeroDivisionError("Target base factor cannot be zero.")
            qty_in_base = quantity * from_unit.to_base_factor
            return qty_in_base / to_unit.to_base_factor

        raise ValueError(
            f"Cannot convert between incompatible units: '{from_unit.symbol}' and '{to_unit.symbol}'."
        )


class UnitConversion(models.Model):
    from_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_from')
    to_unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='conversions_to')
    factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        help_text="1 from_unit = factor * to_unit (e.g. 1 carton = 20 packets: factor = 20)."
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ('from_unit', 'to_unit')
        verbose_name = 'Unit Conversion Rule'
        verbose_name_plural = 'Unit Conversion Rules'

    def clean(self):
        if self.from_unit_id and self.to_unit_id and self.from_unit_id == self.to_unit_id:
            raise ValidationError("From unit and To unit must be different.")
        if self.factor <= Decimal('0'):
            raise ValidationError("Conversion factor must be greater than zero.")

    def __str__(self):
        return f"1 {self.from_unit.symbol} = {self.factor} {self.to_unit.symbol}"


class RawMaterial(models.Model):
    name = models.CharField(max_length=150, unique=True, help_text="e.g. Flour, Cooking oil, Salt and spice mix")
    code = models.CharField(max_length=50, unique=True, help_text="SKU or internal code e.g. RM-FLOUR")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='raw_materials')
    standard_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Standard/purchase rate per unit in INR (e.g. 42.00 or 45.00 per kg)"
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text="Minimum stock threshold triggering reorder alert"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Raw Material'
        verbose_name_plural = 'Raw Materials'

    def __str__(self):
        return f"{self.name} [{self.code}] ({self.unit.symbol})"

    @property
    def unit_rate(self) -> Decimal:
        return self.standard_cost


class PackagingItem(models.Model):
    name = models.CharField(max_length=150, unique=True, help_text="e.g. 200 g pouch, Carton (holds 20 pkts)")
    code = models.CharField(max_length=50, unique=True, help_text="SKU code e.g. PM-POUCH-200G, PM-CARTON-20")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='packaging_items')
    standard_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Purchase cost per item in INR (e.g. 2.50 per pouch, 15.00 per carton)"
    )
    capacity_packets = models.PositiveIntegerField(
        default=1,
        help_text="Number of finished packets held (e.g. 20 for carton, 1 for individual pouch)"
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Minimum threshold for reorder alert"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Packaging Item'
        verbose_name_plural = 'Packaging Items'

    def __str__(self):
        return f"{self.name} [{self.code}]"

    @property
    def unit_rate(self) -> Decimal:
        return self.standard_cost


class Product(models.Model):
    name = models.CharField(max_length=150, unique=True, help_text="e.g. Murukku 200 g")
    code = models.CharField(max_length=50, unique=True, help_text="SKU e.g. FG-MURUKKU-200G")
    hsn_code = models.CharField(
        max_length=15,
        default='19059040',
        help_text="HSN code for GST taxation (e.g., 19059040 for namkeen/savouries)"
    )
    pack_size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('200.00'),
        help_text="Net weight/volume per packet (e.g. 200.00)"
    )
    pack_size_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='products_by_pack_unit',
        help_text="Pack unit (e.g., g, kg, ml)"
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='products_by_sales_unit',
        help_text="Billing / stock unit (typically 'packet')"
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text="Selling price per packet before tax in INR (e.g. ₹50.00)"
    )
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Total GST percentage rate (e.g. 5.00 for 5%)"
    )
    carton_pack_qty = models.PositiveIntegerField(
        default=20,
        help_text="Number of packets per master carton (standard: 20)"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Finished Product'
        verbose_name_plural = 'Finished Products'

    def __str__(self):
        return f"{self.name} [{self.code}] - ₹{self.selling_price}"

    @property
    def unit_rate(self) -> Decimal:
        return self.selling_price

    @property
    def cgst_rate(self) -> Decimal:
        """Central GST half-rate for intra-state supply (e.g. 2.50%)."""
        return self.gst_rate / Decimal('2')

    @property
    def sgst_rate(self) -> Decimal:
        """State GST half-rate for intra-state supply (e.g. 2.50%)."""
        return self.gst_rate / Decimal('2')

    @property
    def igst_rate(self) -> Decimal:
        """Integrated GST full rate for inter-state supply (e.g. 5.00%)."""
        return self.gst_rate

    @property
    def selling_price_with_tax(self) -> Decimal:
        """Price per packet including GST."""
        tax = (self.selling_price * self.gst_rate) / Decimal('100')
        return (self.selling_price + tax).quantize(Decimal('0.01'))


class CustomerType(models.TextChoices):
    RETAILER = 'retailer', 'Retailer'
    DISTRIBUTOR = 'distributor', 'Distributor'


class Customer(models.Model):
    name = models.CharField(max_length=150, help_text="e.g. Retailer A, Distributor B")
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.RETAILER,
        help_text="Type of customer channel"
    )
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(
        max_length=100,
        default='Tamil Nadu',
        help_text="State where supply takes place"
    )
    state_code = models.CharField(
        max_length=2,
        default='33',
        help_text="2-digit GST state code (e.g., 33 for Tamil Nadu, 29 for Karnataka)"
    )
    gstin = models.CharField(
        max_length=15,
        blank=True,
        help_text="15-character GSTIN (mandatory for distributors / tax invoices)"
    )
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum allowed outstanding credit in INR"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return f"{self.name} ({self.get_customer_type_display()}, {self.state})"

    def is_interstate(self, factory_state_code: str = '33') -> bool:
        """Determines whether supply to this customer is inter-state (IGST) or intra-state (CGST+SGST)."""
        return self.state_code.strip() != factory_state_code.strip()

    @property
    def total_invoiced(self) -> Decimal:
        """Total value of all posted invoices for this customer."""
        if not hasattr(self, 'invoices'):
            return Decimal('0.00')
        res = self.invoices.filter(status='posted').aggregate(total=models.Sum('grand_total'))['total']
        return res or Decimal('0.00')

    @property
    def total_paid(self) -> Decimal:
        """Total payments received against posted invoices for this customer."""
        if hasattr(self, 'payments'):
            res = self.payments.filter(invoice__status='posted').aggregate(total=models.Sum('amount'))['total']
            return res or Decimal('0.00')
        return Decimal('0.00')

    @property
    def outstanding_balance(self) -> Decimal:
        """Total unpaid balance across all posted invoices for this customer."""
        if not hasattr(self, 'invoices'):
            return Decimal('0.00')
        total = Decimal('0.00')
        for inv in self.invoices.filter(status='posted'):
            total += inv.outstanding_balance
        return total


class Supplier(models.Model):
    name = models.CharField(max_length=150, help_text="Supplier business name")
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, default='Tamil Nadu')
    state_code = models.CharField(max_length=2, default='33')
    gstin = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'

    def __str__(self):
        return f"{self.name} ({self.city or self.state})"


class BillOfMaterial(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='bom',
        help_text="Finished product this BOM recipe is for"
    )
    name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Recipe / BOM name (e.g. Standard Murukku 200g Batch)"
    )
    batch_size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Standard batch multiplier (typically 1.00)"
    )
    expected_yield_packets = models.PositiveIntegerField(
        default=200,
        help_text="Standard expected output in finished packets per batch (e.g. 200)"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name']
        verbose_name = 'Bill of Materials'
        verbose_name_plural = 'Bills of Materials'

    def __str__(self):
        return f"BOM: {self.product.name} (Yield: {self.expected_yield_packets} pkts)"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.product.name} Recipe (Standard Batch)"
        super().save(*args, **kwargs)

    @property
    def raw_material_lines(self):
        return self.lines.filter(raw_material__isnull=False).select_related('raw_material', 'unit')

    @property
    def packaging_lines(self):
        return self.lines.filter(packaging_item__isnull=False).select_related('packaging_item', 'unit')

    @property
    def total_raw_material_cost(self) -> Decimal:
        return sum((line.line_cost for line in self.raw_material_lines), Decimal('0.00'))

    @property
    def total_packaging_cost(self) -> Decimal:
        return sum((line.line_cost for line in self.packaging_lines), Decimal('0.00'))

    @property
    def total_standard_cost(self) -> Decimal:
        return self.total_raw_material_cost + self.total_packaging_cost

    @property
    def standard_cost_per_packet(self) -> Decimal:
        if self.expected_yield_packets > 0:
            return (self.total_standard_cost / Decimal(str(self.expected_yield_packets))).quantize(Decimal('0.01'))
        return Decimal('0.00')


class BOMLine(models.Model):
    bom = models.ForeignKey(
        BillOfMaterial,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bom_lines'
    )
    packaging_item = models.ForeignKey(
        PackagingItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bom_lines'
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Standard recipe consumption quantity per batch"
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='bom_lines',
        help_text="Unit of measure for this line (e.g. kg, litre, piece)"
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'BOM Line Item'
        verbose_name_plural = 'BOM Line Items'

    def clean(self):
        if not self.raw_material and not self.packaging_item:
            raise ValidationError("A BOM line must specify either a Raw Material or a Packaging Item.")
        if self.raw_material and self.packaging_item:
            raise ValidationError("A BOM line cannot specify both a Raw Material and a Packaging Item.")
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError("Quantity per batch must be greater than zero.")

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
    def standard_rate(self) -> Decimal:
        return self.raw_material.standard_cost if self.raw_material else self.packaging_item.standard_cost

    @property
    def line_cost(self) -> Decimal:
        """Computes cost for this line (taking unit conversion into account if unit differs from master unit)."""
        if not self.quantity:
            return Decimal('0.00')
        master_item = self.item
        if not master_item:
            return Decimal('0.00')
        if self.unit_id != master_item.unit_id:
            qty_in_master_unit = Unit.convert(self.quantity, self.unit, master_item.unit)
        else:
            qty_in_master_unit = self.quantity
        return (qty_in_master_unit * master_item.standard_cost).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.item_name}: {self.quantity} {self.unit.symbol}"

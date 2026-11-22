from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from masters.models import Customer, Product, Unit
from inventory.services import get_item_current_stock


class OrderStatus(models.TextChoices):
    SUBMITTED = 'submitted', 'Submitted'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    INVOICED = 'invoiced', 'Invoiced'
    DISPATCHED = 'dispatched', 'Dispatched'


class SalesOrder(models.Model):
    """
    Sales order placed by a salesman for a customer (Retailer or Distributor).
    Tracks status through submitted, approved, invoiced, dispatched (or rejected).
    """
    order_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique Sales Order Number, e.g. SO-2026-0001",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        help_text="Retailer or Distributor placing the order",
    )
    salesman = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        help_text="Salesman who booked the order",
    )
    order_date = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.SUBMITTED,
    )
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_sales_orders',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-created_at']
        verbose_name = 'Sales Order'
        verbose_name_plural = 'Sales Orders'

    def __str__(self):
        return f"{self.order_number} — {self.customer.name} ({self.get_status_display()})"

    @property
    def total_quantity(self) -> Decimal:
        return sum((line.quantity for line in self.lines.all()), Decimal('0.00'))

    @property
    def subtotal(self) -> Decimal:
        return sum((line.line_total for line in self.lines.all()), Decimal('0.00'))

    @property
    def total_tax(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines.all()), Decimal('0.00'))

    @property
    def grand_total(self) -> Decimal:
        return (self.subtotal + self.total_tax).quantize(Decimal('0.01'))

    def check_stock_coverage(self):
        """
        Evaluates finished-goods stock coverage for each product line.
        Returns a dict containing:
          - is_fully_covered: bool
          - lines: list of dicts with stock info per line
          - total_shortage: total packets short
        """
        lines_info = []
        is_fully_covered = True
        total_shortage = Decimal('0.00')

        for line in self.lines.select_related('product', 'product__unit').all():
            available = get_item_current_stock(line.product)
            covered = available >= line.quantity
            shortage = max(Decimal('0.00'), line.quantity - available)
            if not covered:
                is_fully_covered = False
                total_shortage += shortage

            lines_info.append({
                'line': line,
                'product': line.product,
                'requested_qty': line.quantity,
                'available_stock': available,
                'is_covered': covered,
                'shortage': shortage,
            })

        return {
            'is_fully_covered': is_fully_covered,
            'lines': lines_info,
            'total_shortage': total_shortage,
        }

    @property
    def is_stock_covered(self) -> bool:
        return self.check_stock_coverage()['is_fully_covered']

    @property
    def status_badge_class(self) -> str:
        mapping = {
            OrderStatus.SUBMITTED: 'badge-submitted',
            OrderStatus.APPROVED: 'badge-approved',
            OrderStatus.REJECTED: 'badge-rejected',
            OrderStatus.INVOICED: 'badge-invoiced',
            OrderStatus.DISPATCHED: 'badge-dispatched',
        }
        return mapping.get(self.status, 'badge-secondary')


class SalesOrderLine(models.Model):
    """
    Line item on a sales order. Links to a finished Product.
    Quantity in packets, rate from price list (product.selling_price).
    """
    order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='order_lines',
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Quantity ordered (packets)",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='order_lines',
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Unit selling price in INR (from price list)",
    )

    class Meta:
        ordering = ['id']
        verbose_name = 'Sales Order Line'
        verbose_name_plural = 'Sales Order Lines'

    def clean(self):
        if self.quantity is not None and self.quantity <= Decimal('0'):
            raise ValidationError("Quantity must be greater than zero.")
        if self.unit_price is not None and self.unit_price < Decimal('0'):
            raise ValidationError("Unit price cannot be negative.")

    @property
    def line_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def tax_rate(self) -> Decimal:
        return self.product.gst_rate

    @property
    def tax_amount(self) -> Decimal:
        return (self.line_total * self.tax_rate / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def total_with_tax(self) -> Decimal:
        return self.line_total + self.tax_amount

    def get_available_stock(self) -> Decimal:
        return get_item_current_stock(self.product)

    @property
    def is_covered(self) -> bool:
        return self.get_available_stock() >= self.quantity

    @property
    def shortage(self) -> Decimal:
        return max(Decimal('0.00'), self.quantity - self.get_available_stock())

    def __str__(self):
        return f"{self.product.name}: {self.quantity} {self.unit.symbol} @ ₹{self.unit_price}"


class SalesOrderLog(models.Model):
    """
    Audit trail for changes and status transitions on a Sales Order.
    """
    order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='audit_logs',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=50)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = 'Sales Order Audit Log'
        verbose_name_plural = 'Sales Order Audit Logs'

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.action} by {self.user}"

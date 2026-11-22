from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from masters.models import Customer, Product, Unit
from .models import SalesOrder, SalesOrderLine, SalesOrderLog, OrderStatus


def generate_order_number() -> str:
    """Generates sequential sales order number: SO-YYYY-XXXX (e.g. SO-2026-0001)."""
    current_year = timezone.now().strftime('%Y')
    prefix = f"SO-{current_year}-"
    last_order = SalesOrder.objects.filter(
        order_number__startswith=prefix
    ).order_by('-order_number').first()

    if last_order:
        try:
            seq = int(last_order.order_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"


def log_order_action(order: SalesOrder, action: str, user=None, details: str = '') -> SalesOrderLog:
    """Helper to record audit trail entries for orders."""
    return SalesOrderLog.objects.create(
        order=order,
        user=user,
        action=action,
        details=details,
        timestamp=timezone.now(),
    )


@transaction.atomic
def create_sales_order(
    salesman,
    customer: Customer,
    lines_data: List[Dict[str, Any]],
    order_number: Optional[str] = None,
    order_date=None,
    notes: str = '',
) -> SalesOrder:
    """
    Creates a new SalesOrder submitted by a salesman.
    lines_data: list of dicts:
      [{'product': Product, 'quantity': Decimal, 'unit_price': Optional[Decimal]}, ...]
    If unit_price is not provided, defaults to product.selling_price.
    """
    if not lines_data:
        raise ValidationError("An order must have at least one product line item.")

    if not order_number:
        order_number = generate_order_number()

    if not order_date:
        order_date = timezone.now().date()

    order = SalesOrder.objects.create(
        order_number=order_number,
        customer=customer,
        salesman=salesman,
        order_date=order_date,
        status=OrderStatus.SUBMITTED,
        notes=notes,
    )

    for item in lines_data:
        product = item['product']
        quantity = Decimal(str(item['quantity']))
        unit_price = item.get('unit_price')
        if unit_price is None or unit_price == '':
            unit_price = product.selling_price
        else:
            unit_price = Decimal(str(unit_price))

        unit = item.get('unit') or product.unit

        SalesOrderLine.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
        )

    log_order_action(
        order=order,
        action='Submitted',
        user=salesman,
        details=f"Order submitted by {salesman.username} for {customer.name} ({len(lines_data)} items).",
    )

    return order


@transaction.atomic
def admin_update_order(
    order: SalesOrder,
    admin_user,
    updated_lines: List[Dict[str, Any]],
    notes: Optional[str] = None,
) -> SalesOrder:
    """
    Admin edits quantities or prices on an existing order.
    Logs each change in the audit trail.
    updated_lines: list of dicts:
      [{'line_id': Optional[int], 'product': Product, 'quantity': Decimal, 'unit_price': Decimal}, ...]
    """
    changes = []

    if notes is not None and notes != order.notes:
        changes.append(f"Notes updated: '{notes}'")
        order.notes = notes

    existing_lines_by_id = {line.id: line for line in order.lines.all()}
    processed_line_ids = set()

    for item in updated_lines:
        line_id = item.get('line_id')
        qty = Decimal(str(item['quantity']))
        price = Decimal(str(item['unit_price']))
        product = item.get('product')

        if line_id and line_id in existing_lines_by_id:
            line = existing_lines_by_id[line_id]
            processed_line_ids.add(line_id)
            line_changes = []
            if line.quantity != qty:
                line_changes.append(f"qty {line.quantity} -> {qty}")
                line.quantity = qty
            if line.unit_price != price:
                line_changes.append(f"price ₹{line.unit_price} -> ₹{price}")
                line.unit_price = price
            if line_changes:
                line.save()
                changes.append(f"{line.product.name}: {', '.join(line_changes)}")
        elif product:
            # New line added
            unit = item.get('unit') or product.unit
            new_line = SalesOrderLine.objects.create(
                order=order,
                product=product,
                quantity=qty,
                unit=unit,
                unit_price=price,
            )
            changes.append(f"Added item: {product.name} ({qty} pkts @ ₹{price})")

    # Delete lines removed
    for line_id, line in existing_lines_by_id.items():
        if line_id not in processed_line_ids and updated_lines:
            # If line wasn't processed and we were supplied line_ids
            pass

    order.save()

    details_str = "; ".join(changes) if changes else "No line items modified."
    log_order_action(
        order=order,
        action='Edited',
        user=admin_user,
        details=f"Admin {admin_user.username} edited order: {details_str}",
    )

    return order


@transaction.atomic
def approve_sales_order(order: SalesOrder, admin_user, notes: str = '') -> SalesOrder:
    """
    Approves a submitted sales order.
    """
    if order.status not in [OrderStatus.SUBMITTED, OrderStatus.REJECTED]:
        raise ValidationError(f"Cannot approve an order with status '{order.get_status_display()}'.")

    order.status = OrderStatus.APPROVED
    order.approved_by = admin_user
    order.approved_at = timezone.now()
    if notes:
        order.notes = f"{order.notes}\n[Approval Notes]: {notes}".strip()
    order.save()

    coverage = order.check_stock_coverage()
    coverage_status = "Stock fully covers order." if coverage['is_fully_covered'] else f"Stock shortage flagged: {coverage['total_shortage']} packets short."

    log_order_action(
        order=order,
        action='Approved',
        user=admin_user,
        details=f"Order approved by {admin_user.username}. {coverage_status}",
    )

    return order


@transaction.atomic
def reject_sales_order(order: SalesOrder, admin_user, reason: str = '') -> SalesOrder:
    """
    Rejects a submitted sales order.
    """
    if order.status not in [OrderStatus.SUBMITTED, OrderStatus.APPROVED]:
        raise ValidationError(f"Cannot reject an order with status '{order.get_status_display()}'.")

    order.status = OrderStatus.REJECTED
    order.rejection_reason = reason
    order.save()

    log_order_action(
        order=order,
        action='Rejected',
        user=admin_user,
        details=f"Order rejected by {admin_user.username}. Reason: {reason or 'Not specified'}",
    )

    return order

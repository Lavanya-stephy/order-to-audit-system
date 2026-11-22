"""
purchases/services.py
Handles the business logic for receiving a PurchaseOrder:
  - Validates that the PO is in DRAFT status
  - For each line, records a PURCHASE StockMovement through inventory.services.record_movement
  - Marks each line as movement_recorded=True
  - Updates PO status to RECEIVED and sets received_date
All writes are wrapped in a single atomic transaction.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from inventory.models import MovementType
from inventory.services import record_movement


@transaction.atomic
def receive_purchase_order(po, received_date=None, user=None):
    """
    Marks a PurchaseOrder as RECEIVED and appends one PURCHASE StockMovement
    per line to the inventory ledger.

    Returns a list of StockMovement instances created.

    Raises ValueError if the PO is not in DRAFT status.
    """
    from .models import PurchaseOrder  # avoid circular at module level

    if po.status != PurchaseOrder.Status.DRAFT:
        raise ValueError(
            f"Cannot receive PO '{po.po_number}': status is '{po.get_status_display()}', expected 'Draft'."
        )

    movements = []

    for line in po.lines.select_related('raw_material', 'packaging_item', 'unit').all():
        if line.movement_recorded:
            continue  # idempotent guard

        item = line.item
        movement = record_movement(
            item=item,
            quantity=line.quantity,
            movement_type=MovementType.PURCHASE,
            source_document=po.po_number,
            user=user,
            unit=line.unit,
            unit_cost=line.unit_price,
            notes=f"Purchase receipt from {po.supplier.name}",
        )

        line.movement_recorded = True
        line.save(update_fields=['movement_recorded'])

        movements.append(movement)

    po.status = PurchaseOrder.Status.RECEIVED
    po.received_date = received_date or timezone.now().date()
    po.save(update_fields=['status', 'received_date'])

    return movements

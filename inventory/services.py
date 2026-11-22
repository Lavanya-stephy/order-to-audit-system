from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from django.db.models import Sum, Q
from django.utils import timezone

from masters.models import RawMaterial, PackagingItem, Product, Unit
from .models import StockMovement, MovementType

InventoryItem = Union[RawMaterial, PackagingItem, Product]


def record_movement(
    item: InventoryItem,
    quantity: Decimal,
    movement_type: str,
    source_document: str,
    user=None,
    unit: Optional[Unit] = None,
    unit_cost: Optional[Decimal] = None,
    batch_number: str = '',
    notes: str = '',
    created_at=None,
) -> StockMovement:
    """
    Core atomic function to append an entry to the StockMovement ledger.
    Signed quantity convention:
      - Positive (+) for inward receipts, output, positive adjustment.
      - Negative (-) for outward issues, dispatch, scrap/damage, negative adjustment.
    """
    if not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))

    rm = item if isinstance(item, RawMaterial) else None
    pm = item if isinstance(item, PackagingItem) else None
    prod = item if isinstance(item, Product) else None

    if unit is None:
        unit = item.unit

    if unit_cost is None:
        unit_cost = getattr(item, 'standard_cost', Decimal('0.00'))

    movement = StockMovement(
        raw_material=rm,
        packaging_item=pm,
        product=prod,
        quantity=quantity,
        unit=unit,
        unit_cost=unit_cost,
        movement_type=movement_type,
        source_document=source_document,
        batch_number=batch_number,
        notes=notes,
        user=user,
    )
    if created_at:
        movement.created_at = created_at

    movement.full_clean()
    movement.save()
    return movement


def get_item_filter(item: InventoryItem) -> Q:
    """Returns a Q object filtering StockMovement records for a given item."""
    if isinstance(item, RawMaterial):
        return Q(raw_material=item)
    elif isinstance(item, PackagingItem):
        return Q(packaging_item=item)
    elif isinstance(item, Product):
        return Q(product=item)
    raise ValueError(f"Unsupported item type: {type(item)}")


def get_item_current_stock(item: InventoryItem, at_date=None) -> Decimal:
    """
    Calculates the exact current stock balance for an item by summing all ledger movements.
    Formula: Closing Balance = sum(signed quantity)
    """
    qs = StockMovement.objects.filter(get_item_filter(item))
    if at_date:
        qs = qs.filter(created_at__lte=at_date)
    total = qs.aggregate(balance=Sum('quantity'))['balance']
    return total if total is not None else Decimal('0.0000')


def get_all_inventory_items() -> List[Dict[str, Any]]:
    """Returns a combined list of all inventory items (Raw Materials, Packaging, Products)."""
    items = []
    for rm in RawMaterial.objects.select_related('unit').filter(is_active=True):
        items.append({
            'obj': rm,
            'id_str': f"rm_{rm.id}",
            'type_code': 'raw_material',
            'type_name': 'Raw Material',
            'name': rm.name,
            'code': rm.code,
            'unit': rm.unit,
            'cost': rm.standard_cost,
            'reorder_level': rm.reorder_level,
        })
    for pm in PackagingItem.objects.select_related('unit').filter(is_active=True):
        items.append({
            'obj': pm,
            'id_str': f"pm_{pm.id}",
            'type_code': 'packaging',
            'type_name': 'Packaging Item',
            'name': pm.name,
            'code': pm.code,
            'unit': pm.unit,
            'cost': pm.standard_cost,
            'reorder_level': pm.reorder_level,
        })
    for prod in Product.objects.select_related('unit').filter(is_active=True):
        items.append({
            'obj': prod,
            'id_str': f"prod_{prod.id}",
            'type_code': 'product',
            'type_name': 'Finished Product',
            'name': prod.name,
            'code': prod.code,
            'unit': prod.unit,
            'cost': getattr(prod, 'selling_price', Decimal('0.00')),
            'reorder_level': Decimal('0.000'),
        })
    return items


def get_stock_summary(item_type_filter: Optional[str] = None, start_date=None, end_date=None) -> List[Dict[str, Any]]:
    """
    Generates the complete stock summary table across all inventory items.
    For every item: Opening Balance + Receipts (Inward) - Issues (Outward) = Closing Balance.
    """
    all_items = get_all_inventory_items()
    summary = []

    for item_meta in all_items:
        if item_type_filter and item_type_filter != 'all' and item_meta['type_code'] != item_type_filter:
            continue

        item_obj = item_meta['obj']
        q_filter = get_item_filter(item_obj)

        # 1. Opening Balance: Sum of movements strictly before start_date
        if start_date:
            opening_qs = StockMovement.objects.filter(q_filter, created_at__lt=start_date)
            opening_sum = opening_qs.aggregate(val=Sum('quantity'))['val'] or Decimal('0.0000')
        else:
            opening_sum = Decimal('0.0000')

        # 2. Period Movements: start_date <= created_at <= end_date
        period_qs = StockMovement.objects.filter(q_filter)
        if start_date:
            period_qs = period_qs.filter(created_at__gte=start_date)
        if end_date:
            period_qs = period_qs.filter(created_at__lte=end_date)

        # Inward receipts: quantity > 0
        receipts = period_qs.filter(quantity__gt=Decimal('0')).aggregate(val=Sum('quantity'))['val'] or Decimal('0.0000')

        # Outward issues: quantity < 0
        issues_sum = period_qs.filter(quantity__lt=Decimal('0')).aggregate(val=Sum('quantity'))['val'] or Decimal('0.0000')
        issues = abs(issues_sum)

        # 3. Closing Balance = Opening + Receipts - Issues
        closing = opening_sum + receipts - issues

        reorder = item_meta['reorder_level']
        is_low_stock = bool(reorder > Decimal('0') and closing <= reorder)

        summary.append({
            'item': item_obj,
            'id_str': item_meta['id_str'],
            'type_name': item_meta['type_name'],
            'type_code': item_meta['type_code'],
            'name': item_meta['name'],
            'code': item_meta['code'],
            'unit': item_meta['unit'],
            'opening': opening_sum,
            'receipts': receipts,
            'issues': issues,
            'closing': closing,
            'cost': item_meta['cost'],
            'valuation': (closing * item_meta['cost']).quantize(Decimal('0.01')),
            'reorder_level': reorder,
            'is_low_stock': is_low_stock,
        })

    return summary


def get_item_ledger(item: InventoryItem, start_date=None, end_date=None) -> Dict[str, Any]:
    """
    Computes an itemized chronological audit ledger for a specific item,
    including Opening Balance, each transaction with running balance, and Closing Balance.
    """
    q_filter = get_item_filter(item)

    # 1. Opening Balance
    if start_date:
        opening_qs = StockMovement.objects.filter(q_filter, created_at__lt=start_date)
        opening_balance = opening_qs.aggregate(val=Sum('quantity'))['val'] or Decimal('0.0000')
    else:
        opening_balance = Decimal('0.0000')

    # 2. Movements in range
    movements_qs = StockMovement.objects.filter(q_filter).select_related('unit', 'user')
    if start_date:
        movements_qs = movements_qs.filter(created_at__gte=start_date)
    if end_date:
        movements_qs = movements_qs.filter(created_at__lte=end_date)
    movements_qs = movements_qs.order_by('created_at', 'id')

    running = opening_balance
    ledger_entries = []
    total_inward = Decimal('0.0000')
    total_outward = Decimal('0.0000')

    for m in movements_qs:
        running += m.quantity
        if m.quantity > Decimal('0'):
            total_inward += m.quantity
        else:
            total_outward += abs(m.quantity)

        ledger_entries.append({
            'movement': m,
            'inward_qty': m.inward_quantity,
            'outward_qty': m.outward_quantity,
            'running_balance': running,
        })

    closing_balance = opening_balance + total_inward - total_outward

    return {
        'item': item,
        'opening_balance': opening_balance,
        'entries': ledger_entries,
        'total_inward': total_inward,
        'total_outward': total_outward,
        'closing_balance': closing_balance,
    }

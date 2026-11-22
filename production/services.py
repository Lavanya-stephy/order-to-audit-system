from decimal import Decimal
from typing import Optional, List, Dict, Any
from django.db import transaction
from django.utils import timezone

from masters.models import Product, BillOfMaterial, RawMaterial, PackagingItem
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement
from .models import ProductionRun, ProductionRunItem, ProductionRunLog, DEFAULT_VARIANCE_TOLERANCE_PCT


def generate_run_number() -> str:
    """Generates sequential production run number: PR-YYYYMMDD-XXXX."""
    today_str = timezone.now().strftime('%Y%m%d')
    prefix = f"PR-{today_str}-"
    last_run = ProductionRun.objects.filter(
        run_number__startswith=prefix
    ).order_by('-run_number').first()

    if last_run:
        try:
            seq = int(last_run.run_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"


def log_run_action(run: ProductionRun, action: str, user=None, details: str = '') -> ProductionRunLog:
    """Helper to log any creation, transition, or edit of a production run with user and time."""
    return ProductionRunLog.objects.create(
        run=run,
        user=user,
        action=action,
        timestamp=timezone.now(),
        details=details,
    )


def create_production_run(
    product: Product,
    bom: BillOfMaterial,
    batch_multiplier: Decimal = Decimal('1.00'),
    variance_tolerance_pct: Decimal = DEFAULT_VARIANCE_TOLERANCE_PCT,
    run_number: Optional[str] = None,
    start_date=None,
    notes: str = '',
    user=None,
) -> ProductionRun:
    """
    Creates a new Planned (Draft) ProductionRun populated with standard items from BOM.
    Logs creation with user and time.
    """
    if bom.product_id != product.id:
        raise ValueError(f"BOM '{bom.name}' does not belong to product '{product.name}'.")

    if not isinstance(batch_multiplier, Decimal):
        batch_multiplier = Decimal(str(batch_multiplier))
    if not isinstance(variance_tolerance_pct, Decimal):
        variance_tolerance_pct = Decimal(str(variance_tolerance_pct))

    if not run_number:
        run_number = generate_run_number()

    if not start_date:
        start_date = timezone.now().date()

    expected_yield = int(bom.expected_yield_packets * batch_multiplier)

    with transaction.atomic():
        run = ProductionRun.objects.create(
            run_number=run_number,
            product=product,
            bom=bom,
            batch_multiplier=batch_multiplier,
            variance_tolerance_pct=variance_tolerance_pct,
            status=ProductionRun.Status.DRAFT,
            start_date=start_date,
            expected_yield=expected_yield,
            notes=notes,
            created_by=user,
            updated_by=user,
        )

        for bom_line in bom.lines.select_related('raw_material', 'packaging_item', 'unit').all():
            std_qty = (bom_line.quantity * batch_multiplier).quantize(Decimal('0.0001'))
            unit_rate = bom_line.standard_rate

            ProductionRunItem.objects.create(
                run=run,
                raw_material=bom_line.raw_material,
                packaging_item=bom_line.packaging_item,
                unit=bom_line.unit,
                standard_quantity=std_qty,
                actual_quantity=std_qty,  # Defaults to standard until updated during issue
                unit_cost=unit_rate,
                notes=bom_line.notes,
            )

        log_run_action(
            run=run,
            action='Created',
            user=user,
            details=f"Production run planned for {product.name} ({expected_yield} pkts expected). Tolerance: {variance_tolerance_pct}%.",
        )

    return run


def issue_materials_for_run(
    run: ProductionRun,
    issues_data: Optional[List[Dict[str, Any]]] = None,
    user=None,
) -> List[StockMovement]:
    """
    Issues raw materials to production run:
    - Sets actual quantities for raw materials.
    - Appends negative StockMovement entries of type PRODUCTION_ISSUE to the ledger (stock down).
    - Transitions run to IN_PROGRESS.
    - Logs transition with user and time.
    """
    if run.status != ProductionRun.Status.DRAFT:
        raise ValueError(f"Cannot issue materials for run {run.run_number}: status is {run.get_status_display()} (expected Draft).")

    movements = []
    with transaction.atomic():
        if issues_data:
            lookup = {d['item_id']: d for d in issues_data}
            for item in run.items.filter(raw_material__isnull=False):
                if item.id in lookup:
                    data = lookup[item.id]
                    if 'actual_quantity' in data:
                        item.actual_quantity = Decimal(str(data['actual_quantity']))
                    if 'unit_cost' in data:
                        item.unit_cost = Decimal(str(data['unit_cost']))
                    item.save()

        # Record ledger issues for raw materials (reducing raw stock)
        issued_summary = []
        for item in run.items.filter(raw_material__isnull=False):
            if item.actual_quantity > Decimal('0') and not item.movement_recorded:
                m = record_movement(
                    item=item.raw_material,
                    quantity=-item.actual_quantity,  # Negative for outward issue (raw stock down)
                    movement_type=MovementType.PRODUCTION_ISSUE,
                    source_document=run.run_number,
                    user=user,
                    unit=item.unit,
                    unit_cost=item.unit_cost,
                    notes=f"Production issue for run {run.run_number}",
                )
                item.movement_recorded = True
                item.save(update_fields=['movement_recorded'])
                movements.append(m)
                issued_summary.append(f"{item.raw_material.name}: {item.actual_quantity} {item.unit.symbol}")

        run.status = ProductionRun.Status.IN_PROGRESS
        run.updated_by = user
        run.save(update_fields=['status', 'updated_by', 'updated_at'])

        log_run_action(
            run=run,
            action='Materials Issued',
            user=user,
            details=f"Raw materials issued to shop floor: {', '.join(issued_summary)}",
        )

    return movements


def record_production_output(
    run: ProductionRun,
    actual_yield: int,
    damaged_pouches: int = 0,
    cartons_used: int = 0,
    labour_cost: Decimal = Decimal('0.00'),
    overhead_cost: Decimal = Decimal('0.00'),
    completion_date=None,
    user=None,
) -> List[StockMovement]:
    """
    Records production output and packaging consumption:
    - Validates run status (IN_PROGRESS).
    - Issues packaging materials (pouches = actual_yield + damaged_pouches, cartons = cartons_used) -> packaging stock down.
    - Records finished goods output (actual_yield packets) -> finished goods stock up.
    - Allocates labour and overhead costs.
    - Transitions run to COMPLETED.
    - Logs completion with user, timestamp, yield and consumption variances.
    """
    if run.status != ProductionRun.Status.IN_PROGRESS:
        raise ValueError(f"Cannot record output for run {run.run_number}: status is {run.get_status_display()} (expected In Progress).")

    if not isinstance(labour_cost, Decimal):
        labour_cost = Decimal(str(labour_cost))
    if not isinstance(overhead_cost, Decimal):
        overhead_cost = Decimal(str(overhead_cost))

    movements = []
    with transaction.atomic():
        run.actual_yield = actual_yield
        run.damaged_pouches = damaged_pouches
        run.cartons_used = cartons_used
        run.labour_cost = labour_cost
        run.overhead_cost = overhead_cost
        run.completion_date = completion_date or timezone.now().date()
        run.updated_by = user
        run.save()

        # 1. Packaging items issues (packaging stock down)
        pkg_summary = []
        for item in run.items.filter(packaging_item__isnull=False):
            pkg = item.packaging_item
            if pkg.capacity_packets == 1 or 'pouch' in pkg.name.lower():
                qty = Decimal(str(actual_yield + damaged_pouches))
                note_str = f"Pouches for {run.run_number}: {actual_yield} good pkts + {damaged_pouches} damaged"
                pkg_summary.append(f"Pouches: {qty} pcs ({damaged_pouches} damaged)")
            else:
                qty = Decimal(str(cartons_used))
                note_str = f"Cartons for {run.run_number}: {cartons_used} cartons used"
                pkg_summary.append(f"Cartons: {qty} pcs")

            item.actual_quantity = qty
            item.save(update_fields=['actual_quantity'])

            if qty > Decimal('0') and not item.movement_recorded:
                m = record_movement(
                    item=pkg,
                    quantity=-qty,  # Negative for outward issue (packaging stock down)
                    movement_type=MovementType.PRODUCTION_ISSUE,
                    source_document=run.run_number,
                    user=user,
                    unit=item.unit,
                    unit_cost=item.unit_cost,
                    notes=note_str,
                )
                item.movement_recorded = True
                item.save(update_fields=['movement_recorded'])
                movements.append(m)

        # 2. Finished goods output (finished goods stock up)
        if actual_yield > 0:
            m_output = record_movement(
                item=run.product,
                quantity=Decimal(str(actual_yield)),  # Positive for inward finished goods (stock up)
                movement_type=MovementType.PRODUCTION_OUTPUT,
                source_document=run.run_number,
                user=user,
                unit=run.product.unit,
                unit_cost=run.actual_cost_per_packet,
                notes=f"Production output: {actual_yield} pkts for run {run.run_number}",
            )
            movements.append(m_output)

        run.status = ProductionRun.Status.COMPLETED
        run.save(update_fields=['status'])

        # Log completion
        flag_str = " (⚠️ FLAGGED - Exceeds tolerance)" if run.is_yield_variance_flagged else ""
        log_run_action(
            run=run,
            action='Completed',
            user=user,
            details=(
                f"Output: {actual_yield} good pkts. Yield variance: {run.yield_variance_pct}%{flag_str}. "
                f"Packaging: {', '.join(pkg_summary)}. "
                f"Labour: ₹{labour_cost}, Overhead: ₹{overhead_cost}."
            ),
        )

    return movements


def execute_full_production_run(
    product: Product,
    bom: BillOfMaterial,
    batch_multiplier: Decimal = Decimal('1.00'),
    raw_material_issues: Optional[Dict[str, Decimal]] = None,
    actual_yield: int = 0,
    damaged_pouches: int = 0,
    cartons_used: int = 0,
    variance_tolerance_pct: Decimal = DEFAULT_VARIANCE_TOLERANCE_PCT,
    labour_cost: Decimal = Decimal('0.00'),
    overhead_cost: Decimal = Decimal('0.00'),
    run_number: Optional[str] = None,
    start_date=None,
    completion_date=None,
    notes: str = '',
    user=None,
) -> ProductionRun:
    """
    Atomic execution of a complete production run:
    1. Creates planned run.
    2. Issues raw materials (raw stock down).
    3. Records output and packaging (packaging down, finished goods up).
    4. Computes variances and flags against configurable tolerance.
    5. Logs each action with user and timestamp.
    """
    run = create_production_run(
        product=product,
        bom=bom,
        batch_multiplier=batch_multiplier,
        variance_tolerance_pct=variance_tolerance_pct,
        run_number=run_number,
        start_date=start_date,
        notes=notes,
        user=user,
    )

    issues_data = []
    if raw_material_issues:
        for item in run.items.filter(raw_material__isnull=False):
            code = item.raw_material.code
            if code in raw_material_issues:
                issues_data.append({
                    'item_id': item.id,
                    'actual_quantity': raw_material_issues[code],
                })

    issue_materials_for_run(run, issues_data=issues_data, user=user)

    record_production_output(
        run=run,
        actual_yield=actual_yield,
        damaged_pouches=damaged_pouches,
        cartons_used=cartons_used,
        labour_cost=labour_cost,
        overhead_cost=overhead_cost,
        completion_date=completion_date,
        user=user,
    )

    return run

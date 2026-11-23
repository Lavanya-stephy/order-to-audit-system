from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from production.models import ProductionRun, ProductionRunItem
from inventory.models import StockMovement, MovementType
from inventory.services import get_weighted_average_unit_cost


class Command(BaseCommand):
    help = "Recalculates run-level costing using weighted average cost method for completed runs without changing ledger quantities."

    def add_arguments(self, parser):
        parser.add_argument(
            '--run',
            type=str,
            help='Specific run_number to recalculate (e.g. PR-20261122-0001). If omitted, recalculates all completed runs.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        run_filter = options.get('run')
        runs = ProductionRun.objects.filter(status=ProductionRun.Status.COMPLETED)
        if run_filter:
            runs = runs.filter(run_number=run_filter)

        count = runs.count()
        self.stdout.write(f"Found {count} completed production run(s) to recalculate.")

        for run in runs:
            self.stdout.write(f"\nRecalculating costing for run: {run.run_number} ({run.product.name})")

            # Collect all movement IDs originating from this run
            run_movements = StockMovement.objects.filter(source_document=run.run_number)
            run_movement_ids = list(run_movements.values_list('id', flat=True))

            # 1. Recalculate Raw Materials
            for item in run.items.filter(raw_material__isnull=False):
                m = run_movements.filter(raw_material=item.raw_material, movement_type=MovementType.PRODUCTION_ISSUE).first()
                before_id = m.id if m else None
                avg_unit_cost = get_weighted_average_unit_cost(
                    item.raw_material,
                    before_movement_id=before_id,
                    exclude_movement_ids=run_movement_ids,
                )
                item.unit_cost = avg_unit_cost
                item.total_cost = (item.actual_quantity * avg_unit_cost).quantize(Decimal('0.01'))
                item.save(update_fields=['unit_cost', 'total_cost'])

                if m:
                    m.unit_cost = avg_unit_cost
                    m.save(update_fields=['unit_cost'])

                self.stdout.write(
                    f"  [RM] {item.raw_material.name}: {item.actual_quantity} {item.unit.symbol} @ "
                    f"₹{item.unit_cost} = ₹{item.total_cost}"
                )

            # 2. Recalculate Packaging Items
            for item in run.items.filter(packaging_item__isnull=False):
                m = run_movements.filter(packaging_item=item.packaging_item, movement_type=MovementType.PRODUCTION_ISSUE).first()
                before_id = m.id if m else None
                avg_unit_cost = get_weighted_average_unit_cost(
                    item.packaging_item,
                    before_movement_id=before_id,
                    exclude_movement_ids=run_movement_ids,
                )
                item.unit_cost = avg_unit_cost
                item.total_cost = (item.actual_quantity * avg_unit_cost).quantize(Decimal('0.01'))
                item.save(update_fields=['unit_cost', 'total_cost'])

                if m:
                    m.unit_cost = avg_unit_cost
                    m.save(update_fields=['unit_cost'])

                self.stdout.write(
                    f"  [PKG] {item.packaging_item.name}: {item.actual_quantity} {item.unit.symbol} @ "
                    f"₹{item.unit_cost} = ₹{item.total_cost}"
                )

            # 3. Update Finished Goods Output Movement unit_cost
            cost_per_pkt = run.actual_cost_per_packet
            m_out = run_movements.filter(product=run.product, movement_type=MovementType.PRODUCTION_OUTPUT).first()
            if m_out:
                m_out.unit_cost = cost_per_pkt
                m_out.save(update_fields=['unit_cost'])

            self.stdout.write(f"  Summary: RM ₹{run.total_raw_material_cost} | PKG ₹{run.total_packaging_cost} | Labour ₹{run.labour_cost} | Power ₹{run.overhead_cost}")
            self.stdout.write(f"  Total Cost: ₹{run.total_production_cost}")
            self.stdout.write(f"  Cost / Pkt: ₹{cost_per_pkt} (Yield: {run.actual_yield} pkts)")
            self.stdout.write(f"  Margin: ₹{run.margin_per_packet} / pkt ({run.margin_pct}%)")

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully recalculated costs for {count} run(s) without changing any ledger quantities."))

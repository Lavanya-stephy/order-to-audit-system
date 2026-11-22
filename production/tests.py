from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import Role
from masters.models import Unit, UnitCategory, RawMaterial, PackagingItem, Product, BillOfMaterial, BOMLine, Supplier
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement, get_item_current_stock
from purchases.models import PurchaseOrder, PurchaseOrderLine
from purchases.services import receive_purchase_order
from production.models import ProductionRun, ProductionRunItem, ProductionRunLog
from production.services import (
    create_production_run,
    issue_materials_for_run,
    record_production_output,
    execute_full_production_run,
)

User = get_user_model()


class BenchmarkProductionRunTests(TestCase):
    """
    Mandatory Benchmark Scenario (PROBLEM.md Section 5):
    - Opening stock:
      * Flour: 100 kg
      * Cooking oil: 30 L
      * Spice mix: 5 kg
      * 200 g pouch: 500 pcs
      * Carton: 30 pcs
      * Finished Murukku 200 g: 50 pkts
    - Step 1: Purchase 60 kg flour @ ₹45/kg -> Flour becomes 160 kg.
    - Step 2: Production run issue: 40 kg flour, 10.5 L oil (+5% over standard), 1.2 kg spice mix.
    - Step 3: Record actual output 188 good pkts, 6 damaged pouches, 9 cartons used.
    - Expected checks:
      * Flour closing balance: 120 kg (100 + 60 - 40)
      * Oil closing balance: 19.5 L
      * Pouches closing balance: 306 (188 used + 6 damaged)
      * Finished goods after run: 238 packets (50 + 188)
      * Yield variance: 188 vs 200 expected = -6.00%, flagged
      * Oil consumption variance: +5.00%, flagged
    - Step 8 Costing:
      * Labour: ₹1,200.00, Overheads: ₹600.00
      * Cost per packet and margin computed
    """

    def setUp(self):
        self.user = User.objects.create_user(username='prod_admin', password='pw', role=Role.ADMIN)

        # Units
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        # Raw Materials
        self.flour = RawMaterial.objects.create(name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'))
        self.oil = RawMaterial.objects.create(name='Cooking oil', code='RM-OIL', unit=self.litre, standard_cost=Decimal('140.00'))
        self.spice = RawMaterial.objects.create(name='Salt and spice mix', code='RM-SPICE', unit=self.kg, standard_cost=Decimal('200.00'))

        # Packaging Items
        self.pouch = PackagingItem.objects.create(name='200 g pouch', code='PM-POUCH-200G', unit=self.piece, standard_cost=Decimal('2.50'), capacity_packets=1)
        self.carton = PackagingItem.objects.create(name='Carton (holds 20 packets)', code='PM-CARTON-20', unit=self.piece, standard_cost=Decimal('15.00'), capacity_packets=20)

        # Finished Product
        self.product = Product.objects.create(
            name='Murukku 200 g', code='FG-MURUKKU-200G', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.g,
            selling_price=Decimal('50.00'), gst_rate=Decimal('5.00'), carton_pack_qty=20,
        )

        # BOM for Murukku 200 g
        self.bom = BillOfMaterial.objects.create(
            product=self.product, name='Murukku 200 g Recipe', batch_size=Decimal('1.00'), expected_yield_packets=200,
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, raw_material=self.oil, quantity=Decimal('10.0000'), unit=self.litre)
        BOMLine.objects.create(bom=self.bom, raw_material=self.spice, quantity=Decimal('1.2000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.pouch, quantity=Decimal('200.0000'), unit=self.piece)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.carton, quantity=Decimal('10.0000'), unit=self.piece)

        # Opening Stock (Benchmark Section 5)
        record_movement(self.flour, Decimal('100.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)
        record_movement(self.oil, Decimal('30.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)
        record_movement(self.spice, Decimal('5.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)
        record_movement(self.pouch, Decimal('500.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)
        record_movement(self.carton, Decimal('30.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)
        record_movement(self.product, Decimal('50.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.user)

        # Step 1: Purchase 60 kg flour @ ₹45/kg
        supplier = Supplier.objects.create(name='Sri Murugan Flour Mills', city='Trichy', state='Tamil Nadu', state_code='33')
        po = PurchaseOrder.objects.create(po_number='PO-BENCH-001', supplier=supplier, created_by=self.user)
        PurchaseOrderLine.objects.create(po=po, raw_material=self.flour, quantity=Decimal('60.0000'), unit=self.kg, unit_price=Decimal('45.00'))
        receive_purchase_order(po, user=self.user)

    def test_benchmark_step2_and_step3_balances_and_variances(self):
        """
        Verify the complete benchmark scenario Steps 2 & 3:
        Issue 40 kg flour, 10.5 L oil, 1.2 kg spice mix.
        Output 188 good pkts, 6 damaged pouches, 9 cartons used.
        """
        # Prior to run: flour is 160 kg (100 opening + 60 purchase)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('160.0000'))
        self.assertEqual(get_item_current_stock(self.oil), Decimal('30.0000'))
        self.assertEqual(get_item_current_stock(self.spice), Decimal('5.0000'))
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('500.0000'))
        self.assertEqual(get_item_current_stock(self.carton), Decimal('30.0000'))
        self.assertEqual(get_item_current_stock(self.product), Decimal('50.0000'))

        # Step 2: Create planned run and issue raw materials
        run = create_production_run(
            product=self.product,
            bom=self.bom,
            batch_multiplier=Decimal('1.00'),
            run_number='PR-20261122-0001',
            user=self.user,
        )
        self.assertEqual(run.status, ProductionRun.Status.DRAFT)
        self.assertEqual(run.expected_yield, 200)

        # Verify creation audit log
        create_log = run.audit_logs.filter(action='Created').first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.user, self.user)
        self.assertIsNotNone(create_log.timestamp)

        # Issue actual materials: 40 kg flour, 10.5 L oil (+5%), 1.2 kg spice
        issues_data = []
        for item in run.items.filter(raw_material__isnull=False):
            if item.raw_material.code == 'RM-FLOUR':
                issues_data.append({'item_id': item.id, 'actual_quantity': Decimal('40.0000'), 'unit_cost': Decimal('45.00')})
            elif item.raw_material.code == 'RM-OIL':
                issues_data.append({'item_id': item.id, 'actual_quantity': Decimal('10.5000')})
            elif item.raw_material.code == 'RM-SPICE':
                issues_data.append({'item_id': item.id, 'actual_quantity': Decimal('1.2000')})

        issue_materials_for_run(run, issues_data=issues_data, user=self.user)
        run.refresh_from_db()
        self.assertEqual(run.status, ProductionRun.Status.IN_PROGRESS)

        # Verify materials issued audit log
        issue_log = run.audit_logs.filter(action='Materials Issued').first()
        self.assertIsNotNone(issue_log)
        self.assertEqual(issue_log.user, self.user)

        # Check raw material stock immediately after Step 2 issue (ledger stock down)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('120.0000'))  # 160 - 40
        self.assertEqual(get_item_current_stock(self.oil), Decimal('19.5000'))     # 30 - 10.5
        self.assertEqual(get_item_current_stock(self.spice), Decimal('3.8000'))    # 5 - 1.2

        # Step 3: Record actual output of 188 good pkts, 6 pouches damaged, 9 cartons used
        # And Step 8: direct labour ₹1,200, power/gas overheads ₹600
        record_production_output(
            run=run,
            actual_yield=188,
            damaged_pouches=6,
            cartons_used=9,
            labour_cost=Decimal('1200.00'),
            overhead_cost=Decimal('600.00'),
            user=self.user,
        )
        run.refresh_from_db()
        self.assertEqual(run.status, ProductionRun.Status.COMPLETED)

        # Verify completion audit log
        complete_log = run.audit_logs.filter(action='Completed').first()
        self.assertIsNotNone(complete_log)
        self.assertEqual(complete_log.user, self.user)

        # ---------------------------------------------------------------------
        # 1. Closing Balances Checks (PROBLEM.md Section 5 Results table)
        # ---------------------------------------------------------------------
        # Flour closing balance: 120 kg (100 + 60 − 40)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('120.0000'))

        # Oil closing balance: 19.5 L
        self.assertEqual(get_item_current_stock(self.oil), Decimal('19.5000'))

        # Pouches closing balance: 306 (188 used + 6 damaged out of 500)
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('306.0000'))

        # Cartons closing balance: 21 (30 - 9)
        self.assertEqual(get_item_current_stock(self.carton), Decimal('21.0000'))

        # Finished goods after run: 238 packets (50 + 188) (finished goods up)
        self.assertEqual(get_item_current_stock(self.product), Decimal('238.0000'))

        # ---------------------------------------------------------------------
        # 2. Variance Checks (PROBLEM.md Section 5 Results table)
        # ---------------------------------------------------------------------
        # Yield variance: 188 vs 200 expected, −6%, flagged (> 3% threshold)
        self.assertEqual(run.yield_variance_pct, Decimal('-6.00'))
        self.assertTrue(run.is_yield_variance_flagged)

        # Oil consumption variance: +5%, flagged (> 3% threshold)
        oil_item = run.items.get(raw_material__code='RM-OIL')
        self.assertEqual(oil_item.consumption_variance_pct, Decimal('5.00'))
        self.assertTrue(oil_item.is_variance_flagged)

        # Flour consumption variance: 0%, not flagged
        flour_item = run.items.get(raw_material__code='RM-FLOUR')
        self.assertEqual(flour_item.consumption_variance_pct, Decimal('0.00'))
        self.assertFalse(flour_item.is_variance_flagged)

        # Spice consumption variance: 0%, not flagged
        spice_item = run.items.get(raw_material__code='RM-SPICE')
        self.assertEqual(spice_item.consumption_variance_pct, Decimal('0.00'))
        self.assertFalse(spice_item.is_variance_flagged)

        # ---------------------------------------------------------------------
        # 3. Costing & Margin Checks (Section 4.5 & Step 8)
        # ---------------------------------------------------------------------
        self.assertEqual(run.total_raw_material_cost, Decimal('3510.00'))
        self.assertEqual(run.total_packaging_cost, Decimal('620.00'))
        self.assertEqual(run.total_material_cost, Decimal('4130.00'))
        self.assertEqual(run.total_production_cost, Decimal('5930.00'))
        self.assertEqual(run.actual_cost_per_packet, Decimal('31.54'))
        self.assertEqual(run.margin_per_packet, Decimal('18.46'))
        self.assertEqual(run.margin_pct, Decimal('36.92'))

    def test_configurable_variance_tolerance(self):
        """
        Verify that tolerance threshold is configurable per run.
        """
        # Run with 10% tolerance: -6% yield variance and +5% oil variance must NOT be flagged
        run_wide = execute_full_production_run(
            product=self.product,
            bom=self.bom,
            batch_multiplier=Decimal('1.00'),
            raw_material_issues={'RM-OIL': Decimal('10.5000')},
            actual_yield=188,
            damaged_pouches=6,
            cartons_used=9,
            variance_tolerance_pct=Decimal('10.00'),
            run_number='PR-TOL-10',
            user=self.user,
        )
        self.assertFalse(run_wide.is_yield_variance_flagged)
        oil_item = run_wide.items.get(raw_material__code='RM-OIL')
        self.assertFalse(oil_item.is_variance_flagged)

        # Run with 2% tolerance: both are flagged
        run_narrow = execute_full_production_run(
            product=self.product,
            bom=self.bom,
            batch_multiplier=Decimal('1.00'),
            raw_material_issues={'RM-OIL': Decimal('10.5000')},
            actual_yield=188,
            damaged_pouches=6,
            cartons_used=9,
            variance_tolerance_pct=Decimal('2.00'),
            run_number='PR-TOL-2',
            user=self.user,
        )
        self.assertTrue(run_narrow.is_yield_variance_flagged)
        oil_narrow = run_narrow.items.get(raw_material__code='RM-OIL')
        self.assertTrue(oil_narrow.is_variance_flagged)

    def test_edit_run_is_logged_with_user_and_time(self):
        """
        Verify that edits to a production run are logged in the audit trail with user and timestamp.
        """
        run = create_production_run(
            product=self.product, bom=self.bom, run_number='PR-EDIT-001', user=self.user
        )
        c = Client()
        c.login(username=self.user.username, password='pw')

        res = c.post(reverse('production:production_run_edit', kwargs={'pk': run.pk}), {
            'variance_tolerance_pct': '4.50',
            'start_date': '2026-11-22',
            'completion_date': '',
            'notes': 'Updated run notes for supervisor shift handover',
            'edit_reason': 'Shift handover parameter update',
        })
        self.assertEqual(res.status_code, 302)

        run.refresh_from_db()
        self.assertEqual(run.variance_tolerance_pct, Decimal('4.50'))
        self.assertEqual(run.updated_by, self.user)

        # Check edit log in audit trail
        edit_log = run.audit_logs.filter(action='Edited').first()
        self.assertIsNotNone(edit_log)
        self.assertEqual(edit_log.user, self.user)
        self.assertIn('Shift handover parameter update', edit_log.details)
        self.assertIsNotNone(edit_log.timestamp)


class ProductionPermissionsTests(TestCase):
    """Verifies role-based access for Production Run URLs."""

    def setUp(self):
        self.password = 'Pass123!'
        self.admin = User.objects.create_user(username='adm', password=self.password, role=Role.ADMIN)
        self.production = User.objects.create_user(username='prod', password=self.password, role=Role.PRODUCTION)
        self.accountant = User.objects.create_user(username='acct', password=self.password, role=Role.ACCOUNTANT)
        self.owner = User.objects.create_user(username='ownr', password=self.password, role=Role.OWNER)
        self.salesman = User.objects.create_user(username='sale', password=self.password, role=Role.SALESMAN)

        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)
        self.flour = RawMaterial.objects.create(name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'))
        self.product = Product.objects.create(
            name='Murukku 200 g', code='FG-MURUKKU-200G', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.g,
            selling_price=Decimal('50.00')
        )
        self.bom = BillOfMaterial.objects.create(product=self.product, name='Recipe', batch_size=Decimal('1.00'), expected_yield_packets=200)
        BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)

        self.run = create_production_run(
            product=self.product, bom=self.bom, run_number='PR-PERM-001', user=self.admin
        )

    def test_salesman_cannot_view_or_manage_production(self):
        c = Client()
        c.login(username='sale', password=self.password)
        self.assertEqual(c.get(reverse('production:production_run_list')).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_detail', kwargs={'pk': self.run.pk})).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_create')).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_edit', kwargs={'pk': self.run.pk})).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_issue', kwargs={'pk': self.run.pk})).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_output', kwargs={'pk': self.run.pk})).status_code, 403)

    def test_accountant_can_view_runs_but_cannot_create_or_issue_or_edit(self):
        c = Client()
        c.login(username='acct', password=self.password)
        self.assertEqual(c.get(reverse('production:production_run_list')).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_detail', kwargs={'pk': self.run.pk})).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_create')).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_edit', kwargs={'pk': self.run.pk})).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_issue', kwargs={'pk': self.run.pk})).status_code, 403)

    def test_owner_can_view_runs_but_cannot_create_or_issue_or_edit(self):
        c = Client()
        c.login(username='ownr', password=self.password)
        self.assertEqual(c.get(reverse('production:production_run_list')).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_detail', kwargs={'pk': self.run.pk})).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_create')).status_code, 403)
        self.assertEqual(c.get(reverse('production:production_run_edit', kwargs={'pk': self.run.pk})).status_code, 403)

    def test_admin_and_production_can_create_and_manage(self):
        c = Client()
        c.login(username='prod', password=self.password)
        self.assertEqual(c.get(reverse('production:production_run_list')).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_detail', kwargs={'pk': self.run.pk})).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_create')).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_edit', kwargs={'pk': self.run.pk})).status_code, 200)
        self.assertEqual(c.get(reverse('production:production_run_issue', kwargs={'pk': self.run.pk})).status_code, 200)

    def test_create_planned_run_via_post_with_exact_values(self):
        """
        POSTs the production run create form with:
          - product, bom, batch_multiplier=1.00, start_date filled in
          - variance_tolerance_pct intentionally omitted → must default to 3.00
          - notes intentionally omitted → must be optional
        Expects a redirect (302) on success and a ProductionRun with correct values.
        """
        import datetime
        c = Client()
        c.login(username='adm', password=self.password)
        res = c.post(reverse('production:production_run_create'), {
            'product': str(self.product.id),
            'bom': str(self.bom.id),
            'batch_multiplier': '1.00',
            'start_date': '2026-11-22',
            # variance_tolerance_pct intentionally omitted → must default to 3.00
            # notes intentionally omitted → must be optional
        })
        # On success the view should redirect (302); a 200 means form re-rendered with errors
        self.assertEqual(res.status_code, 302,
            msg=f"Expected redirect on success but got {res.status_code}. "
                f"Form may have errors.")
        run = ProductionRun.objects.filter(product=self.product).order_by('-created_at').first()
        self.assertIsNotNone(run, "ProductionRun was not created after successful POST")
        self.assertEqual(run.expected_yield, 200)
        self.assertEqual(run.variance_tolerance_pct, Decimal('3.00'))
        self.assertEqual(run.status, ProductionRun.Status.DRAFT)

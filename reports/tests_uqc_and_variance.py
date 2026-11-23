"""
Additional tests for:
  1. GST UQC mapper (get_gst_uqc)
  2. Production Variance material consumption (benchmark run values + flag labels)
  3. CSV export contains material consumption rows
  4. PDF export is a valid PDF containing material consumption data
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from masters.models import (
    Unit, UnitCategory, RawMaterial, PackagingItem,
    Product, BillOfMaterial, BOMLine, Customer, CustomerType, Supplier
)
from inventory.models import MovementType
from inventory.services import record_movement
from purchases.models import PurchaseOrder, PurchaseOrderLine
from purchases.services import receive_purchase_order
from production.services import create_production_run, issue_materials_for_run, record_production_output
from reports.services import get_gst_uqc, get_production_variance_report_data

User = get_user_model()


# ---------------------------------------------------------------------------
# 1. UQC Mapper Tests
# ---------------------------------------------------------------------------

class GSTUQCMapperTests(TestCase):
    """Tests for the GST portal UQC mapper: get_gst_uqc()."""

    def test_packet_symbols_map_to_PAC(self):
        for sym in ('packet', 'packets', 'pkt', 'pkts', 'PAC', 'pac', 'pack'):
            self.assertEqual(get_gst_uqc(sym), 'PAC', f"Expected PAC for '{sym}'")

    def test_kilogram_symbols_map_to_KGS(self):
        for sym in ('kg', 'kgs', 'kilogram', 'kilograms', 'KG', 'KGS'):
            self.assertEqual(get_gst_uqc(sym), 'KGS', f"Expected KGS for '{sym}'")

    def test_gram_symbols_map_to_GMS(self):
        for sym in ('g', 'gm', 'gms', 'gram', 'grams', 'GMS'):
            self.assertEqual(get_gst_uqc(sym), 'GMS', f"Expected GMS for '{sym}'")

    def test_litre_symbols_map_to_LTR(self):
        for sym in ('l', 'ltr', 'litre', 'litres', 'liter', 'liters', 'LTR', 'L'):
            self.assertEqual(get_gst_uqc(sym), 'LTR', f"Expected LTR for '{sym}'")

    def test_millilitre_symbols_map_to_MLT(self):
        for sym in ('ml', 'mlt', 'millilitre', 'milliliter', 'MLT', 'ML'):
            self.assertEqual(get_gst_uqc(sym), 'MLT', f"Expected MLT for '{sym}'")

    def test_piece_symbols_map_to_PCS(self):
        for sym in ('piece', 'pieces', 'pcs', 'pc', 'PCS', 'PC'):
            self.assertEqual(get_gst_uqc(sym), 'PCS', f"Expected PCS for '{sym}'")

    def test_carton_box_symbols_map_to_BOX(self):
        for sym in ('carton', 'cartons', 'ctn', 'box', 'boxes', 'BOX'):
            self.assertEqual(get_gst_uqc(sym), 'BOX', f"Expected BOX for '{sym}'")

    def test_unknown_symbol_returns_OTH(self):
        self.assertEqual(get_gst_uqc('banana'), 'OTH')
        self.assertEqual(get_gst_uqc(''), 'OTH')
        self.assertEqual(get_gst_uqc(None), 'OTH')

    def test_case_insensitive(self):
        self.assertEqual(get_gst_uqc('PACKET'), 'PAC')
        self.assertEqual(get_gst_uqc('Litre'), 'LTR')
        self.assertEqual(get_gst_uqc('KiloGram'), 'KGS')

    def test_whitespace_stripped(self):
        self.assertEqual(get_gst_uqc('  packet  '), 'PAC')
        self.assertEqual(get_gst_uqc('\tkg\n'), 'KGS')


# ---------------------------------------------------------------------------
# 2. Production Variance Material Consumption Tests
# ---------------------------------------------------------------------------

class ProductionVarianceMaterialConsumptionTests(TestCase):
    """
    Tests for the material consumption section of the Production Variance report.
    Uses the benchmark run:
      Flour  : planned 40 kg,    actual 40.0000 kg  → 0%
      Oil    : planned 10 litre, actual 10.5000 L   → +5.00% FLAGGED
      Spice  : planned 1.2 kg,   actual 1.2000 kg   → 0%
      Pouch  : planned 200 piece,actual 194 piece    → −3.00%  (188 good + 6 damaged)
      Carton : planned 10 piece, actual 9 piece      → −10.00%
    Flag label must include "Yield" and "Cooking oil".
    """

    def setUp(self):
        self.password = 'Pass1234!'
        self.admin = User.objects.create_user(username='var_admin', password=self.password, role=Role.ADMIN)
        self.accountant = User.objects.create_user(username='var_acct', password=self.password, role=Role.ACCOUNTANT)

        # Units
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        # Raw materials
        self.flour = RawMaterial.objects.create(name='Flour', code='VAR-RM-FLOUR', unit=self.kg, standard_cost=Decimal('43.125'))
        self.oil = RawMaterial.objects.create(name='Cooking oil', code='VAR-RM-OIL', unit=self.litre, standard_cost=Decimal('140.00'))
        self.spice = RawMaterial.objects.create(name='Spice mix', code='VAR-RM-SPICE', unit=self.kg, standard_cost=Decimal('200.00'))

        # Packaging
        self.pouch = PackagingItem.objects.create(name='200 g pouch', code='VAR-PM-POUCH', unit=self.piece, standard_cost=Decimal('2.50'), capacity_packets=1)
        self.carton = PackagingItem.objects.create(name='Carton', code='VAR-PM-CARTON', unit=self.piece, standard_cost=Decimal('15.00'), capacity_packets=20)

        # Product
        self.product = Product.objects.create(
            name='Murukku 200 g', code='VAR-FG-MURUKKU', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.kg,
            selling_price=Decimal('50.00'), gst_rate=Decimal('5.00'), carton_pack_qty=20,
            hsn_code='19059040',
        )

        # BOM (1 batch = 200 pkts)
        self.bom = BillOfMaterial.objects.create(
            product=self.product, name='Murukku Recipe', batch_size=Decimal('1.00'), expected_yield_packets=200,
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, raw_material=self.oil, quantity=Decimal('10.0000'), unit=self.litre)
        BOMLine.objects.create(bom=self.bom, raw_material=self.spice, quantity=Decimal('1.2000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.pouch, quantity=Decimal('200.0000'), unit=self.piece)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.carton, quantity=Decimal('10.0000'), unit=self.piece)

        # Seed opening stock
        record_movement(self.flour, Decimal('100.0000'), MovementType.OPENING, 'VAR-OPEN-01', user=self.admin, unit_cost=Decimal('43.125'))
        record_movement(self.oil, Decimal('30.0000'), MovementType.OPENING, 'VAR-OPEN-01', user=self.admin, unit_cost=Decimal('140.00'))
        record_movement(self.spice, Decimal('5.0000'), MovementType.OPENING, 'VAR-OPEN-01', user=self.admin, unit_cost=Decimal('200.00'))
        record_movement(self.pouch, Decimal('500.0000'), MovementType.OPENING, 'VAR-OPEN-01', user=self.admin, unit_cost=Decimal('2.50'))
        record_movement(self.carton, Decimal('30.0000'), MovementType.OPENING, 'VAR-OPEN-01', user=self.admin, unit_cost=Decimal('15.00'))

        # Create and complete benchmark run
        self.run = create_production_run(
            product=self.product, bom=self.bom,
            batch_multiplier=Decimal('1.00'),
            run_number='VAR-PR-BENCH-001',
            user=self.admin,
        )
        issue_materials_for_run(self.run, issues_data=[
            {'item_id': self.run.items.get(raw_material=self.flour).id, 'actual_quantity': Decimal('40.0000')},
            {'item_id': self.run.items.get(raw_material=self.oil).id, 'actual_quantity': Decimal('10.5000')},
            {'item_id': self.run.items.get(raw_material=self.spice).id, 'actual_quantity': Decimal('1.2000')},
        ], user=self.admin)
        record_production_output(
            run=self.run, actual_yield=188, damaged_pouches=6, cartons_used=9,
            labour_cost=Decimal('1200.00'), overhead_cost=Decimal('600.00'), user=self.admin,
        )
        self.run.refresh_from_db()

    # ---- Service layer ----

    def test_material_consumption_present_in_service_data(self):
        data = get_production_variance_report_data()
        rd = next(r for r in data['runs_data'] if r['run'].run_number == 'VAR-PR-BENCH-001')
        mc = {m['item_name']: m for m in rd['material_consumption']}

        # Flour: planned 40, actual 40, variance 0
        self.assertEqual(mc['Flour']['standard_quantity'], Decimal('40.0000'))
        self.assertEqual(mc['Flour']['actual_quantity'], Decimal('40.0000'))
        self.assertEqual(mc['Flour']['variance_quantity'], Decimal('0.0000'))
        self.assertEqual(mc['Flour']['variance_pct'], Decimal('0.00'))
        self.assertFalse(mc['Flour']['is_flagged'])

        # Oil: planned 10, actual 10.5, variance +0.5 (+5.00%), FLAGGED
        self.assertEqual(mc['Cooking oil']['standard_quantity'], Decimal('10.0000'))
        self.assertEqual(mc['Cooking oil']['actual_quantity'], Decimal('10.5000'))
        self.assertEqual(mc['Cooking oil']['variance_quantity'], Decimal('0.5000'))
        self.assertEqual(mc['Cooking oil']['variance_pct'], Decimal('5.00'))
        self.assertTrue(mc['Cooking oil']['is_flagged'])

        # Spice: planned 1.2, actual 1.2, variance 0
        self.assertEqual(mc['Spice mix']['standard_quantity'], Decimal('1.2000'))
        self.assertEqual(mc['Spice mix']['actual_quantity'], Decimal('1.2000'))
        self.assertEqual(mc['Spice mix']['variance_quantity'], Decimal('0.0000'))
        self.assertFalse(mc['Spice mix']['is_flagged'])

        # Pouch: planned 200, actual 194 (188 good + 6 damaged)
        self.assertEqual(mc['200 g pouch']['standard_quantity'], Decimal('200.0000'))
        self.assertEqual(mc['200 g pouch']['actual_quantity'], Decimal('194.0000'))
        # Pouch variance is -3.00% — within/at 3% tolerance; not flagged
        self.assertFalse(mc['200 g pouch']['is_flagged'])

        # Carton: planned 10, actual 9, variance -10.00% → exceeds 3% tolerance → flagged UNDER
        self.assertEqual(mc['Carton']['standard_quantity'], Decimal('10.0000'))
        self.assertEqual(mc['Carton']['actual_quantity'], Decimal('9.0000'))
        self.assertTrue(mc['Carton']['is_flagged'])
        # Variance is negative → UNDER direction
        self.assertLess(mc['Carton']['variance_quantity'], Decimal('0'))

    def test_flag_label_names_yield_and_oil(self):
        data = get_production_variance_report_data()
        rd = next(r for r in data['runs_data'] if r['run'].run_number == 'VAR-PR-BENCH-001')
        self.assertTrue(rd['has_variance_flag'])
        label = rd['flag_label']
        self.assertIn('Yield', label)
        self.assertIn('Cooking oil', label)
        self.assertTrue(label.startswith('FLAGGED ('))

    def test_flagged_reasons_list(self):
        data = get_production_variance_report_data()
        rd = next(r for r in data['runs_data'] if r['run'].run_number == 'VAR-PR-BENCH-001')
        reasons = rd['flagged_reasons']
        self.assertIn('Yield', reasons)
        self.assertIn('Cooking oil', reasons)

    def test_item_types_correctly_labelled(self):
        data = get_production_variance_report_data()
        rd = next(r for r in data['runs_data'] if r['run'].run_number == 'VAR-PR-BENCH-001')
        mc = {m['item_name']: m for m in rd['material_consumption']}
        self.assertEqual(mc['Flour']['item_type'], 'Raw Material')
        self.assertEqual(mc['200 g pouch']['item_type'], 'Packaging')
        self.assertEqual(mc['Carton']['item_type'], 'Packaging')

    # ---- Web view ----

    def test_production_variance_view_shows_flag_label_with_reasons(self):
        c = Client()
        c.login(username='var_acct', password=self.password)
        res = c.get(reverse('reports:production_variance'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('VAR-PR-BENCH-001', content)
        self.assertIn('FLAGGED', content)
        self.assertIn('Yield', content)
        self.assertIn('Cooking oil', content)
        # Material consumption table should appear
        self.assertIn('Material Consumption', content)
        # Benchmark values
        self.assertIn('10.5', content)   # actual oil
        self.assertIn('+5.00', content)  # variance pct
        # Oil is OVER (actual > planned); alert label must say OVER, not UNDER
        self.assertIn('OVER', content)

    def test_alert_labels_over_vs_under_in_web_view(self):
        """
        Oil (+5%) is flagged OVER (actual > planned) → red badge.
        Carton (−10%) is flagged UNDER (actual < planned, exceeds tolerance) → amber badge.
        Both labels must appear in the page.
        """
        c = Client()
        c.login(username='var_acct', password=self.password)
        res = c.get(reverse('reports:production_variance'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        # Oil is flagged positive → OVER badge (red)
        self.assertIn('OVER', content)
        # Carton is flagged negative → UNDER badge (amber)
        self.assertIn('UNDER', content)

    # ---- CSV export ----

    def test_csv_export_contains_material_consumption_rows(self):
        c = Client()
        c.login(username='var_acct', password=self.password)
        res = c.get(reverse('reports:production_variance'), {'export': 'csv'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('production_variance_report.csv', res['Content-Disposition'])
        content = res.content.decode('utf-8-sig')  # strip BOM
        # Flag label present in run summary row
        self.assertIn('FLAGGED', content)
        # Material consumption rows present
        self.assertIn('Cooking oil', content)
        self.assertIn('10.50', content)   # actual quantity formatted
        # Oil alert cell must say OVER (positive variance)
        self.assertIn('OVER', content)
        # Carton is flagged negative → must say UNDER
        self.assertIn('UNDER', content)
        self.assertIn('Flour', content)
        self.assertIn('200 g pouch', content)
        self.assertIn('Carton', content)

    def test_csv_alert_cell_values(self):
        """
        Verifies OVER/UNDER alert values in CSV material consumption rows.
        Oil (+5%) → "OVER"; Carton (−10%, exceeds tolerance) → "UNDER".
        No row should say the old "FLAGGED" text in the alert column.
        """
        c = Client()
        c.login(username='var_acct', password=self.password)
        res = c.get(reverse('reports:production_variance'), {'export': 'csv'})
        content = res.content.decode('utf-8-sig')
        # Detail rows are indented with two leading spaces in item_name column
        oil_rows = [line for line in content.splitlines() if '  Cooking oil' in line]
        self.assertTrue(len(oil_rows) > 0, "No Cooking oil detail row found in CSV")
        # The oil detail row must contain OVER (positive over-consumption)
        self.assertIn('OVER', oil_rows[0])
        # Must NOT contain the old "FLAGGED" text in the alert cell
        self.assertNotIn('FLAGGED', oil_rows[0])

        # Carton detail row: −10% → UNDER
        carton_rows = [line for line in content.splitlines() if '  Carton' in line]
        self.assertTrue(len(carton_rows) > 0, "No Carton detail row found in CSV")
        self.assertIn('UNDER', carton_rows[0])

    # ---- PDF export ----

    def test_pdf_export_is_valid_pdf(self):
        c = Client()
        c.login(username='var_acct', password=self.password)
        res = c.get(reverse('reports:production_variance'), {'export': 'pdf'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.content.startswith(b'%PDF-'))


# ---------------------------------------------------------------------------
# 3. HSN Summary UQC = PAC for packet products
# ---------------------------------------------------------------------------

class GSTHSNSummaryUQCTests(TestCase):
    """Tests that the HSN summary uses PAC for packet-unit products."""

    def setUp(self):
        self.password = 'Pass1234!'
        self.admin = User.objects.create_user(username='hsn_admin', password=self.password, role=Role.ADMIN)
        self.accountant = User.objects.create_user(username='hsn_acct', password=self.password, role=Role.ACCOUNTANT)

        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)
        self.product = Product.objects.create(
            name='Murukku 200 g HSN', code='HSN-FG-MRK', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.g,
            selling_price=Decimal('50.00'), gst_rate=Decimal('5.00'), hsn_code='19059040',
        )
        self.customer = Customer.objects.create(
            name='HSN Customer', customer_type=CustomerType.RETAILER,
            city='Chennai', state='Tamil Nadu', state_code='33',
        )
        from orders.models import SalesOrder, SalesOrderLine, OrderStatus
        from invoices.services import generate_invoice
        order = SalesOrder.objects.create(
            order_number='HSN-SO-001', customer=self.customer,
            salesman=self.admin, status=OrderStatus.APPROVED,
        )
        SalesOrderLine.objects.create(
            order=order, product=self.product,
            quantity=Decimal('100.00'), unit_price=Decimal('50.00'), unit=self.packet,
        )
        self.invoice = generate_invoice(order, user=self.admin)

    def test_hsn_summary_uqc_is_PAC_for_packet_product(self):
        from reports.services import get_gst_summary_data
        data = get_gst_summary_data()
        hsn_rows = data['hsn_summary']
        murukku_rows = [r for r in hsn_rows if r['hsn_code'] == '19059040']
        self.assertTrue(len(murukku_rows) > 0, "No HSN row found for 19059040")
        for row in murukku_rows:
            self.assertEqual(row['uqc'], 'PAC', f"Expected PAC, got {row['uqc']!r}")

    def test_gst_summary_view_shows_PAC(self):
        c = Client()
        c.login(username='hsn_acct', password=self.password)
        res = c.get(reverse('reports:gst_summary'))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('PAC', content)

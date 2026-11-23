"""
End-to-End Test for PROBLEM.md Section 5 Benchmark Scenario.

Runs the complete 9-step benchmark scenario from clean seed data and asserts
every expected result in the "Results we will check" table:
  1. Flour closing balance: 120 kg (100 + 60 − 40)
  2. Oil closing balance: 19.5 L (30 − 10.5)
  3. Pouches closing balance: 306 (500 − 194, where 194 = 188 used + 6 damaged)
  4. Finished goods after run: 238 packets (50 opening + 188 produced)
  5. Finished goods after Retailer A dispatch: 88 packets (238 − 150)
  6. Yield variance: 188 vs 200 expected, −6.00%, flagged
  7. Oil consumption variance: 10.5 vs 10 L standard, +5.00%, flagged
  8. Retailer A invoice: ₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875 grand total
  9. Retailer A outstanding: ₹3,875 (after ₹4,000 payment)
  10. Distributor B order: Shortage of 32 packets flagged; IGST applies if invoiced
  11. Cost per packet: ₹31.14 (valuation method: weighted average; overhead rule: run allocation)
  12. Owner Dashboard: displays today's orders, stock levels, variance alerts, cost per packet, and outstanding dues.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from masters.models import (
    Unit,
    UnitCategory,
    UnitConversion,
    RawMaterial,
    PackagingItem,
    Product,
    Customer,
    CustomerType,
    Supplier,
    BillOfMaterial,
    BOMLine,
)
from inventory.models import MovementType
from inventory.services import (
    record_movement,
    get_item_current_stock,
    get_stock_summary,
    get_weighted_average_unit_cost,
)
from purchases.models import PurchaseOrder, PurchaseOrderLine
from purchases.services import receive_purchase_order
from production.models import ProductionRun
from production.services import (
    create_production_run,
    issue_materials_for_run,
    record_production_output,
)
from orders.models import SalesOrder, OrderStatus
from orders.services import (
    create_sales_order,
    approve_sales_order,
)
from invoices.models import InvoiceStatus, PaymentMode
from invoices.services import (
    generate_invoice,
    dispatch_invoice,
    record_payment,
    get_ageing_report,
)

User = get_user_model()


class Section5BenchmarkEndToEndTests(TestCase):
    """
    Mandatory Section 5 Benchmark Scenario End-to-End Test.
    Executes steps 1 through 9 sequentially and asserts every result in the table.
    """

    def setUp(self):
        self.password = 'BenchPass123!'

        # ---------------------------------------------------------------------
        # 1. Users
        # ---------------------------------------------------------------------
        self.admin = User.objects.create_user(
            username='bench_admin', password=self.password, role=Role.ADMIN
        )
        self.salesman_a = User.objects.create_user(
            username='bench_salesman_a', password=self.password, role=Role.SALESMAN
        )
        self.salesman_b = User.objects.create_user(
            username='bench_salesman_b', password=self.password, role=Role.SALESMAN
        )
        self.production = User.objects.create_user(
            username='bench_production', password=self.password, role=Role.PRODUCTION
        )
        self.accountant = User.objects.create_user(
            username='bench_accountant', password=self.password, role=Role.ACCOUNTANT
        )
        self.owner = User.objects.create_user(
            username='bench_owner', password=self.password, role=Role.OWNER
        )

        # ---------------------------------------------------------------------
        # 2. Units of Measure
        # ---------------------------------------------------------------------
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT, to_base_factor=Decimal('1.000000'))
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT, to_base_factor=Decimal('0.001000'))
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME, to_base_factor=Decimal('1.000000'))
        self.ml = Unit.objects.create(name='Millilitre', symbol='ml', category=UnitCategory.VOLUME, to_base_factor=Decimal('0.001000'))
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))
        self.carton_unit = Unit.objects.create(name='Carton', symbol='carton', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))

        # Conversion rules
        UnitConversion.objects.create(from_unit=self.carton_unit, to_unit=self.packet, factor=Decimal('20.0000'), description='1 carton holds 20 packets')
        UnitConversion.objects.create(from_unit=self.kg, to_unit=self.g, factor=Decimal('1000.0000'), description='1 kg = 1000 g')
        UnitConversion.objects.create(from_unit=self.litre, to_unit=self.ml, factor=Decimal('1000.0000'), description='1 litre = 1000 ml')

        # ---------------------------------------------------------------------
        # 3. Masters Data (Section 5 Benchmark)
        # ---------------------------------------------------------------------
        self.flour = RawMaterial.objects.create(
            name='Flour', code='RM-FLOUR', unit=self.kg,
            standard_cost=Decimal('42.00'), reorder_level=Decimal('20.000')
        )
        self.oil = RawMaterial.objects.create(
            name='Cooking oil', code='RM-OIL', unit=self.litre,
            standard_cost=Decimal('140.00'), reorder_level=Decimal('10.000')
        )
        self.spice = RawMaterial.objects.create(
            name='Salt and spice mix', code='RM-SPICE', unit=self.kg,
            standard_cost=Decimal('200.00'), reorder_level=Decimal('2.000')
        )
        self.pouch = PackagingItem.objects.create(
            name='200 g pouch', code='PM-POUCH-200G', unit=self.piece,
            standard_cost=Decimal('2.50'), capacity_packets=1
        )
        self.carton = PackagingItem.objects.create(
            name='Carton (holds 20 packets)', code='PM-CARTON-20', unit=self.piece,
            standard_cost=Decimal('15.00'), capacity_packets=20
        )

        # Finished Goods Product: Murukku 200 g
        self.product = Product.objects.create(
            name='Murukku 200 g', code='FG-MURUKKU-200G', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.g,
            selling_price=Decimal('50.00'), gst_rate=Decimal('5.00'),
            carton_pack_qty=20, hsn_code='19059040',
        )

        # BOM for Murukku 200 g: 1 batch = 200 packets expected
        self.bom = BillOfMaterial.objects.create(
            product=self.product, name='Murukku Recipe', batch_size=Decimal('1.00'),
            expected_yield_packets=200, notes='1 batch = 200 packets'
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, raw_material=self.oil, quantity=Decimal('10.0000'), unit=self.litre)
        BOMLine.objects.create(bom=self.bom, raw_material=self.spice, quantity=Decimal('1.2000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.pouch, quantity=Decimal('200.0000'), unit=self.piece)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.carton, quantity=Decimal('10.0000'), unit=self.piece)

        # Customers (Factory in Tamil Nadu, state code 33)
        self.retailer_a = Customer.objects.create(
            name='Retailer A', customer_type=CustomerType.RETAILER,
            city='Trichy', state='Tamil Nadu', state_code='33',
            gstin='33AABCR1234A1Z5', credit_limit=Decimal('25000.00')
        )
        self.distributor_b = Customer.objects.create(
            name='Distributor B', customer_type=CustomerType.DISTRIBUTOR,
            city='Bengaluru', state='Karnataka', state_code='29',
            gstin='29AABCD5678B1Z6', credit_limit=Decimal('50000.00')
        )

        # Supplier
        self.supplier = Supplier.objects.create(
            name='Sri Murugan Flour Mills', city='Trichy',
            state='Tamil Nadu', state_code='33', gstin='33SUPPLIER001Z1'
        )

        # ---------------------------------------------------------------------
        # 4. Opening Stock (Section 5 Benchmark)
        # flour 100 kg, oil 30 L, spice mix 5 kg, pouches 500, cartons 30, Murukku 200 g 50 pkts
        # ---------------------------------------------------------------------
        record_movement(self.flour, Decimal('100.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('42.00'))
        record_movement(self.oil, Decimal('30.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('140.00'))
        record_movement(self.spice, Decimal('5.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('200.00'))
        record_movement(self.pouch, Decimal('500.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('2.50'))
        record_movement(self.carton, Decimal('30.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('15.00'))
        record_movement(self.product, Decimal('50.0000'), MovementType.OPENING, 'OPENING-BENCHMARK-2026', user=self.admin, unit_cost=Decimal('31.14'))

    def test_full_section_5_benchmark_scenario_and_results_we_will_check(self):
        """
        Executes the exact 9 steps of Section 5 in order and verifies
        every single row in the 'Results we will check' table.
        """
        # =====================================================================
        # Step 1: Record a purchase of 60 kg flour at ₹45/kg
        # =====================================================================
        po = PurchaseOrder.objects.create(
            po_number='PO-BENCH-001',
            supplier=self.supplier,
            created_by=self.admin,
        )
        PurchaseOrderLine.objects.create(
            po=po,
            raw_material=self.flour,
            quantity=Decimal('60.0000'),
            unit=self.kg,
            unit_price=Decimal('45.00'),
        )
        receive_purchase_order(po, user=self.admin)

        # Verification after Step 1:
        # Total flour in stock: 100 opening + 60 purchased = 160 kg
        self.assertEqual(get_item_current_stock(self.flour), Decimal('160.0000'))
        # Weighted average cost of flour = (100*42 + 60*45) / 160 = 6900 / 160 = ₹43.125
        w_cost = get_weighted_average_unit_cost(self.flour)
        self.assertEqual(w_cost, Decimal('43.1250'))

        # =====================================================================
        # Step 2: Start one production run of Murukku 200 g.
        # Issue 40 kg flour, 10.5 L oil (0.5 L over standard), 1.2 kg spice mix.
        # =====================================================================
        run = create_production_run(
            product=self.product,
            bom=self.bom,
            batch_multiplier=Decimal('1.00'),
            run_number='PR-20261122-0001',
            user=self.production,
        )

        flour_item = run.items.get(raw_material=self.flour)
        oil_item = run.items.get(raw_material=self.oil)
        spice_item = run.items.get(raw_material=self.spice)

        issue_materials_for_run(
            run=run,
            issues_data=[
                {'item_id': flour_item.id, 'actual_quantity': Decimal('40.0000')},
                {'item_id': oil_item.id, 'actual_quantity': Decimal('10.5000')},
                {'item_id': spice_item.id, 'actual_quantity': Decimal('1.2000')},
            ],
            user=self.production,
        )

        # Raw material stock immediately after issue:
        # CHECK 1: Flour closing balance: 120 kg (100 + 60 − 40)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('120.0000'))
        # CHECK 2: Oil closing balance: 19.5 L (30 − 10.5)
        self.assertEqual(get_item_current_stock(self.oil), Decimal('19.5000'))
        # Spice stock: 5 − 1.2 = 3.8 kg
        self.assertEqual(get_item_current_stock(self.spice), Decimal('3.8000'))

        # =====================================================================
        # Step 3 & Step 8: Record actual output of 188 good packets, 6 pouches damaged,
        # 9 cartons used. Add labour of ₹1,200 and gas/power of ₹600 for the run.
        # =====================================================================
        record_production_output(
            run=run,
            actual_yield=188,
            damaged_pouches=6,
            cartons_used=9,
            labour_cost=Decimal('1200.00'),
            overhead_cost=Decimal('600.00'),
            user=self.production,
        )
        run.refresh_from_db()

        # CHECK 3: Pouches closing balance: 306 (500 opening − 194 consumed, where 194 = 188 used + 6 damaged)
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('306.0000'))
        # Cartons closing balance: 21 (30 opening − 9 used)
        self.assertEqual(get_item_current_stock(self.carton), Decimal('21.0000'))

        # CHECK 4: Finished goods after run: 238 packets (50 opening + 188 produced)
        self.assertEqual(get_item_current_stock(self.product), Decimal('238.0000'))

        # CHECK 6: Yield variance: 188 vs 200 expected, −6%, flagged
        self.assertEqual(run.expected_yield, 200)
        self.assertEqual(run.actual_yield, 188)
        self.assertEqual(run.yield_variance_pct, Decimal('-6.00'))
        self.assertTrue(run.is_yield_variance_flagged)

        # CHECK 7: Oil consumption variance: +5%, flagged
        oil_run_item = run.items.get(raw_material=self.oil)
        self.assertEqual(oil_run_item.standard_quantity, Decimal('10.0000'))
        self.assertEqual(oil_run_item.actual_quantity, Decimal('10.5000'))
        self.assertEqual(oil_run_item.consumption_variance_pct, Decimal('5.00'))
        self.assertTrue(oil_run_item.is_variance_flagged)

        # CHECK 11: Cost per packet: figure with valuation method and overhead rule stated
        # Flour: 40 kg @ 43.125 = 1,725.00
        # Oil: 10.5 L @ 140.00 = 1,470.00
        # Spice: 1.2 kg @ 200.00 = 240.00
        # Pouches: 194 pcs @ 2.50 = 485.00
        # Cartons: 9 pcs @ 15.00 = 135.00
        # Labour = 1,200.00, Power/Overhead = 600.00
        # Total batch cost = 1725 + 1470 + 240 + 485 + 135 + 1200 + 600 = ₹5,855.00
        # Cost per packet = 5855 / 188 = ₹31.14
        # Margin = 50.00 - 31.14 = ₹18.86 (37.71%)
        self.assertEqual(run.total_raw_material_cost, Decimal('3435.00'))
        self.assertEqual(run.total_packaging_cost, Decimal('620.00'))
        self.assertEqual(run.labour_cost, Decimal('1200.00'))
        self.assertEqual(run.overhead_cost, Decimal('600.00'))
        self.assertEqual(run.total_production_cost, Decimal('5855.00'))
        self.assertEqual(run.actual_cost_per_packet, Decimal('31.14'))
        self.assertEqual(run.margin_per_packet, Decimal('18.86'))
        self.assertEqual(run.margin_pct, Decimal('37.71'))

        # =====================================================================
        # Step 4: Salesman A, on mobile, places an order for Retailer A (Tamil Nadu): 150 packets.
        # =====================================================================
        order_a = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{
                'product': self.product,
                'quantity': Decimal('150.00'),
                'unit_price': Decimal('50.00'),
                'unit': self.packet,
            }],
            order_number='SO-BENCH-001',
            notes='Benchmark Retailer A order: 150 packets',
        )
        self.assertEqual(order_a.status, OrderStatus.SUBMITTED)
        # Check stock coverage: 238 packets available, covers 150 packets
        cov_a = order_a.check_stock_coverage()
        self.assertTrue(cov_a['is_fully_covered'])
        self.assertEqual(cov_a['total_shortage'], Decimal('0.00'))
        self.assertTrue(order_a.is_stock_covered)

        # =====================================================================
        # Step 5: Admin approves it, raises the GST invoice (CGST + SGST) and records dispatch.
        # =====================================================================
        approve_sales_order(order_a, admin_user=self.admin)
        self.assertEqual(order_a.status, OrderStatus.APPROVED)

        invoice_a = generate_invoice(order_a, user=self.admin)
        self.assertEqual(invoice_a.status, InvoiceStatus.POSTED)

        # CHECK 8: Retailer A invoice: ₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875
        self.assertFalse(invoice_a.is_interstate)  # Tamil Nadu to Tamil Nadu: Intra-state
        self.assertEqual(invoice_a.taxable_value, Decimal('7500.00'))
        self.assertEqual(invoice_a.cgst_amount, Decimal('187.50'))
        self.assertEqual(invoice_a.sgst_amount, Decimal('187.50'))
        self.assertEqual(invoice_a.igst_amount, Decimal('0.00'))
        self.assertEqual(invoice_a.grand_total, Decimal('7875.00'))

        # Record dispatch
        dispatch_invoice(invoice_a, user=self.admin)
        self.assertTrue(invoice_a.is_dispatched)
        order_a.refresh_from_db()
        self.assertEqual(order_a.status, OrderStatus.DISPATCHED)

        # CHECK 5: Finished goods after Retailer A dispatch: 88 packets (238 − 150)
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.0000'))

        # =====================================================================
        # Step 6: Salesman B places an order for Distributor B (Karnataka): 120 packets.
        # Show how the system handles insufficient stock.
        # =====================================================================
        order_b = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{
                'product': self.product,
                'quantity': Decimal('120.00'),
                'unit_price': Decimal('50.00'),
                'unit': self.packet,
            }],
            order_number='SO-BENCH-002',
            notes='Benchmark Distributor B order: 120 packets',
        )

        # CHECK 10: Distributor B order: Shortage of 32 packets flagged; IGST applies if invoiced
        cov_b = order_b.check_stock_coverage()
        self.assertFalse(cov_b['is_fully_covered'])
        # Available stock is 88 packets, requested is 120 packets -> shortage of 32 packets
        self.assertEqual(cov_b['lines'][0]['available_stock'], Decimal('88.00'))
        self.assertEqual(cov_b['lines'][0]['requested_qty'], Decimal('120.00'))
        self.assertEqual(cov_b['total_shortage'], Decimal('32.00'))
        self.assertEqual(cov_b['lines'][0]['shortage'], Decimal('32.00'))
        self.assertFalse(order_b.is_stock_covered)

        # Tax verification: Distributor B is in Karnataka (state_code '29')
        # Factory is in Tamil Nadu (state_code '33') -> Interstate supply -> IGST applies
        self.assertTrue(self.distributor_b.is_interstate('33'))

        # =====================================================================
        # Step 7: Record a payment of ₹4,000 from Retailer A.
        # =====================================================================
        record_payment(
            invoice=invoice_a,
            amount=Decimal('4000.00'),
            payment_date=timezone.localdate(),
            payment_mode=PaymentMode.BANK_TRANSFER,
            reference_number='UTR-BENCH-4000',
            user=self.admin,
        )
        invoice_a.refresh_from_db()

        # CHECK 9: Retailer A outstanding: ₹3,875 (7,875 − 4,000)
        self.assertEqual(invoice_a.amount_paid, Decimal('4000.00'))
        self.assertEqual(invoice_a.outstanding_balance, Decimal('3875.00'))

        # Ageing summary confirms customer outstanding
        ageing = get_ageing_report()
        ret_a_ageing = next(c for c in ageing['customers'] if c['customer'].id == self.retailer_a.id)
        self.assertEqual(ret_a_ageing['total_outstanding'], Decimal('3875.00'))
        self.assertEqual(ageing['summary']['total_receivables'], Decimal('3875.00'))

        # =====================================================================
        # Step 9: Owner Dashboard Verification
        # Asserts the owner dashboard accurately displays all benchmark figures:
        # - Today's orders
        # - Stock levels
        # - Variance alerts
        # - Cost per packet
        # - Outstanding dues
        # =====================================================================
        client = Client()
        client.login(username='bench_owner', password=self.password)
        res = client.get(reverse('owner_dashboard'))
        self.assertEqual(res.status_code, 200)

        content = res.content.decode('utf-8')

        # 1. Today's orders
        self.assertIn('SO-BENCH-001', content)
        self.assertIn('SO-BENCH-002', content)
        self.assertIn('Retailer A', content)
        self.assertIn('Distributor B', content)
        self.assertIn('32 pkts short', content)  # Shortage flagged on dashboard

        # 2. Stock levels
        self.assertIn('120', content)     # Flour closing
        self.assertIn('19.5', content)    # Oil closing
        self.assertIn('306', content)     # Pouches closing
        self.assertIn('88', content)      # Finished goods after dispatch

        # 3. Variance alerts
        self.assertIn('FLAGGED', content)
        self.assertIn('PR-20261122-0001', content)
        self.assertIn('-6.00%', content)  # Yield variance
        self.assertIn('OVER', content)    # Oil over-consumption alert

        # 4. Cost per packet
        self.assertIn('31.14', content)   # Cost per packet
        self.assertIn('50.00', content)   # Selling price
        self.assertIn('18.86', content)   # Margin
        self.assertIn('37.71%', content)  # Margin %

        # 5. Outstanding dues
        self.assertIn('3875.00', content) # Outstanding balance from Retailer A

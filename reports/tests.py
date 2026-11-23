from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from masters.models import Unit, UnitCategory, RawMaterial, PackagingItem, Product, BillOfMaterial, BOMLine, Customer, CustomerType, Supplier
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement
from purchases.models import PurchaseOrder, PurchaseOrderLine
from purchases.services import receive_purchase_order
from production.models import ProductionRun
from production.services import create_production_run, issue_materials_for_run, record_production_output
from orders.models import SalesOrder, SalesOrderLine, OrderStatus
from invoices.models import Invoice, InvoiceStatus, Payment, PaymentMode
from invoices.services import generate_invoice, record_payment

User = get_user_model()


class Section46ReportsTests(TestCase):
    """
    Test suite for Section 4.6 Reports for accounts and audit:
    - Sales Register (detail, customer-wise, product-wise)
    - GST Summary (GSTR-1 & GSTR-3B)
    - Purchase Register
    - Stock Summary & Ledger
    - Production Variance & Wastage
    - Receivables Ageing & Payments
    - CSV/Excel and PDF exports
    - Read-only enforcement for Accountant role
    """

    def setUp(self):
        self.password = 'Pass1234!'
        self.admin = User.objects.create_user(username='rep_admin', password=self.password, role=Role.ADMIN)
        self.accountant = User.objects.create_user(username='rep_accountant', password=self.password, role=Role.ACCOUNTANT)
        self.owner = User.objects.create_user(username='rep_owner', password=self.password, role=Role.OWNER)
        self.production = User.objects.create_user(username='rep_production', password=self.password, role=Role.PRODUCTION)
        self.salesman = User.objects.create_user(username='rep_salesman', password=self.password, role=Role.SALESMAN)

        # Units
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        # Masters
        self.flour = RawMaterial.objects.create(name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'))
        self.oil = RawMaterial.objects.create(name='Cooking oil', code='RM-OIL', unit=self.litre, standard_cost=Decimal('140.00'))
        self.spice = RawMaterial.objects.create(name='Spice mix', code='RM-SPICE', unit=self.kg, standard_cost=Decimal('200.00'))
        self.pouch = PackagingItem.objects.create(name='200 g pouch', code='PM-POUCH-200G', unit=self.piece, standard_cost=Decimal('2.50'), capacity_packets=1)
        self.carton = PackagingItem.objects.create(name='Carton', code='PM-CARTON-20', unit=self.piece, standard_cost=Decimal('15.00'), capacity_packets=20)

        self.product = Product.objects.create(
            name='Murukku 200 g', code='FG-MURUKKU-200G', unit=self.packet,
            pack_size=Decimal('200.00'), pack_size_unit=self.g,
            selling_price=Decimal('50.00'), gst_rate=Decimal('5.00'), carton_pack_qty=20,
            hsn_code='19059040',
        )

        self.bom = BillOfMaterial.objects.create(
            product=self.product, name='Murukku Recipe', batch_size=Decimal('1.00'), expected_yield_packets=200,
        )
        BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, raw_material=self.oil, quantity=Decimal('10.0000'), unit=self.litre)
        BOMLine.objects.create(bom=self.bom, raw_material=self.spice, quantity=Decimal('1.2000'), unit=self.kg)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.pouch, quantity=Decimal('200.0000'), unit=self.piece)
        BOMLine.objects.create(bom=self.bom, packaging_item=self.carton, quantity=Decimal('10.0000'), unit=self.piece)

        self.supplier = Supplier.objects.create(name='Mill Supplier', city='Trichy', state='Tamil Nadu', state_code='33', gstin='33SUPPLIER001Z1')
        self.customer_a = Customer.objects.create(name='Retailer A', customer_type=CustomerType.RETAILER, city='Trichy', state='Tamil Nadu', state_code='33', gstin='33AABCR1234A1Z5')
        self.customer_b = Customer.objects.create(name='Distributor B', customer_type=CustomerType.DISTRIBUTOR, city='Bengaluru', state='Karnataka', state_code='29', gstin='29AABCD5678B1Z6')

        # Seed initial data
        record_movement(self.flour, Decimal('100.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('42.00'))
        record_movement(self.oil, Decimal('30.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('140.00'))
        record_movement(self.spice, Decimal('5.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('200.00'))
        record_movement(self.pouch, Decimal('500.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('2.50'))
        record_movement(self.carton, Decimal('30.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('15.00'))
        record_movement(self.product, Decimal('50.0000'), MovementType.OPENING, 'OPENING-01', user=self.admin, unit_cost=Decimal('31.14'))

        # Purchase
        po = PurchaseOrder.objects.create(po_number='PO-TEST-001', supplier=self.supplier, created_by=self.admin)
        PurchaseOrderLine.objects.create(po=po, raw_material=self.flour, quantity=Decimal('60.0000'), unit=self.kg, unit_price=Decimal('45.00'))
        receive_purchase_order(po, user=self.admin)

        # Production Run
        self.run = create_production_run(product=self.product, bom=self.bom, batch_multiplier=Decimal('1.00'), run_number='PR-TEST-001', user=self.admin)
        issue_materials_for_run(self.run, issues_data=[
            {'item_id': self.run.items.get(raw_material=self.flour).id, 'actual_quantity': Decimal('40.0000')},
            {'item_id': self.run.items.get(raw_material=self.oil).id, 'actual_quantity': Decimal('10.5000')},
            {'item_id': self.run.items.get(raw_material=self.spice).id, 'actual_quantity': Decimal('1.2000')},
        ], user=self.admin)
        record_production_output(
            run=self.run, actual_yield=188, damaged_pouches=6, cartons_used=9,
            labour_cost=Decimal('1200.00'), overhead_cost=Decimal('600.00'), user=self.admin
        )

        # Sales Order & Invoice
        order = SalesOrder.objects.create(
            order_number='SO-TEST-001', customer=self.customer_a, salesman=self.salesman,
            status=OrderStatus.APPROVED,
        )
        SalesOrderLine.objects.create(order=order, product=self.product, quantity=Decimal('150.00'), unit_price=Decimal('50.00'), unit=self.packet)
        self.invoice = generate_invoice(order, user=self.admin)

        # Payment
        record_payment(
            invoice=self.invoice,
            amount=Decimal('4000.00'),
            payment_date=timezone.localdate(),
            payment_mode=PaymentMode.BANK_TRANSFER,
            user=self.admin,
        )

    # -------------------------------------------------------------------------
    # 1. Reports Hub Access
    # -------------------------------------------------------------------------

    def test_reports_hub_access_by_role(self):
        c = Client()
        # Admin can view
        c.login(username='rep_admin', password=self.password)
        res = c.get(reverse('reports:hub'))
        self.assertEqual(res.status_code, 200)

        # Accountant can view (Read-Only)
        c.login(username='rep_accountant', password=self.password)
        res = c.get(reverse('reports:hub'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Read-Only Auditor Access')

        # Owner can view
        c.login(username='rep_owner', password=self.password)
        res = c.get(reverse('reports:hub'))
        self.assertEqual(res.status_code, 200)

        # Salesman cannot view (403)
        c.login(username='rep_salesman', password=self.password)
        res = c.get(reverse('reports:hub'))
        self.assertEqual(res.status_code, 403)

    def test_reports_hub_receivables_ageing_card_amounts(self):
        """
        Verify that the 'Customer Receivables & Ageing' card on the Reports Hub:
        1. Correctly outputs non-empty amounts for total receivables outstanding and all four buckets.
        2. Shows total outstanding of ₹3,875.00 (from Retailer A: 7,875 − 4,000 paid).
        3. Shows all four buckets as of today: 0-30d: ₹3,875.00, 31-60d: ₹0.00, 61-90d: ₹0.00, 90+d: ₹0.00.
        4. Matches the total displayed on the full Ageing Report page.
        """
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        # 1. Load Reports Hub
        res_hub = c.get(reverse('reports:hub'))
        self.assertEqual(res_hub.status_code, 200)

        # Verify context variables
        summary = res_hub.context['ageing_summary']
        self.assertEqual(summary['total_outstanding'], Decimal('3875.00'))
        self.assertEqual(summary['total_receivables'], Decimal('3875.00'))
        self.assertEqual(summary['bucket_0_30'], Decimal('3875.00'))
        self.assertEqual(summary['bucket_31_60'], Decimal('0.00'))
        self.assertEqual(summary['bucket_61_90'], Decimal('0.00'))
        self.assertEqual(summary['bucket_90_plus'], Decimal('0.00'))

        # Verify rendered HTML content on Reports Hub
        content_hub = res_hub.content.decode('utf-8')
        self.assertIn('Total Receivables Outstanding', content_hub)
        self.assertIn('₹3875.00', content_hub)
        self.assertIn('0-30d: ₹3875.00', content_hub)
        self.assertIn('31-60d: ₹0.00', content_hub)
        self.assertIn('61-90d: ₹0.00', content_hub)
        self.assertIn('90+d: ₹0.00', content_hub)

        # 2. Load Ageing Report page and verify match
        res_ageing = c.get(reverse('reports:receivables_ageing'))
        self.assertEqual(res_ageing.status_code, 200)
        content_ageing = res_ageing.content.decode('utf-8')
        # Total outstanding on ageing page must match
        self.assertIn('₹3875.00', content_ageing)
        self.assertEqual(res_ageing.context['summary']['total_outstanding'], summary['total_outstanding'])

    # -------------------------------------------------------------------------
    # 2. Sales Register & Exports
    # -------------------------------------------------------------------------

    def test_sales_register_view_and_tabs(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        # Invoices detail tab
        res = c.get(reverse('reports:sales_register'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.invoice.invoice_number)
        self.assertContains(res, 'Retailer A')
        self.assertContains(res, '7500.00')

        # Customer-wise tab
        res_cust = c.get(reverse('reports:sales_register'), {'tab': 'customer'})
        self.assertEqual(res_cust.status_code, 200)
        self.assertContains(res_cust, 'Retailer A')

        # Product-wise tab
        res_prod = c.get(reverse('reports:sales_register'), {'tab': 'product'})
        self.assertEqual(res_prod.status_code, 200)
        self.assertContains(res_prod, 'Murukku 200 g')

    def test_sales_register_csv_export(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:sales_register'), {'export': 'csv'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="sales_register.csv"', res['Content-Disposition'])
        content = res.content.decode('utf-8')
        self.assertIn('Invoice No,Date,Customer Name', content)
        self.assertIn(self.invoice.invoice_number, content)
        self.assertIn('7500.00', content)

    def test_sales_register_pdf_export(self):
        c = Client()
        c.login(username='rep_admin', password=self.password)

        res = c.get(reverse('reports:sales_register'), {'export': 'pdf'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF-'))

    # -------------------------------------------------------------------------
    # 3. GST Summary (GSTR-1 & GSTR-3B)
    # -------------------------------------------------------------------------

    def test_gst_summary_view_and_exports(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:gst_summary'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'GSTR-3B Table 3.1')
        self.assertContains(res, 'GSTR-1 Table 12')
        self.assertContains(res, 'GSTR-1 Table 4')
        self.assertContains(res, '19059040')  # HSN

        # CSV Export
        res_csv = c.get(reverse('reports:gst_summary'), {'export': 'csv'})
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv['Content-Type'], 'text/csv; charset=utf-8')
        content = res_csv.content.decode('utf-8')
        self.assertIn('GSTR-3B TABLE 3.1', content)
        self.assertIn('GSTR-1 TABLE 12', content)

        # PDF Export
        res_pdf = c.get(reverse('reports:gst_summary'), {'export': 'pdf'})
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

    # -------------------------------------------------------------------------
    # 4. Purchase Register
    # -------------------------------------------------------------------------

    def test_purchase_register_view_and_exports(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:purchase_register'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'PO-TEST-001')
        self.assertContains(res, 'Mill Supplier')
        self.assertContains(res, 'Flour')

        # CSV Export
        res_csv = c.get(reverse('reports:purchase_register'), {'export': 'csv'})
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('purchase_register.csv', res_csv['Content-Disposition'])

        # PDF Export
        res_pdf = c.get(reverse('reports:purchase_register'), {'export': 'pdf'})
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

    # -------------------------------------------------------------------------
    # 5. Stock Report & Inventory Ledger Export
    # -------------------------------------------------------------------------

    def test_stock_report_view_and_exports(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:stock_report'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Flour')
        self.assertContains(res, 'Cooking oil')
        self.assertContains(res, 'Murukku 200 g')

        # CSV Export
        res_csv = c.get(reverse('reports:stock_report'), {'export': 'csv'})
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('stock_summary.csv', res_csv['Content-Disposition'])

        # PDF Export
        res_pdf = c.get(reverse('reports:stock_report'), {'export': 'pdf'})
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

        # Direct inventory summary view CSV export
        res_inv_csv = c.get(reverse('inventory:stock_summary'), {'export': 'csv'})
        self.assertEqual(res_inv_csv.status_code, 200)
        self.assertEqual(res_inv_csv['Content-Type'], 'text/csv; charset=utf-8')

        # Direct inventory summary view PDF export
        res_inv_pdf = c.get(reverse('inventory:stock_summary'), {'export': 'pdf'})
        self.assertEqual(res_inv_pdf.status_code, 200)
        self.assertEqual(res_inv_pdf['Content-Type'], 'application/pdf')

    # -------------------------------------------------------------------------
    # 6. Production Variance Report
    # -------------------------------------------------------------------------

    def test_production_variance_report_view_and_exports(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:production_variance'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'PR-TEST-001')
        self.assertContains(res, '-6.00%')  # Yield variance
        self.assertContains(res, 'FLAGGED')

        # CSV Export
        res_csv = c.get(reverse('reports:production_variance'), {'export': 'csv'})
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('production_variance_report.csv', res_csv['Content-Disposition'])

        # PDF Export
        res_pdf = c.get(reverse('reports:production_variance'), {'export': 'pdf'})
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

    # -------------------------------------------------------------------------
    # 7. Receivables, Ageing & Payments
    # -------------------------------------------------------------------------

    def test_receivables_ageing_view_and_exports(self):
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        res = c.get(reverse('reports:receivables_ageing'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Retailer A')
        self.assertContains(res, '3875.00')  # Outstanding balance (7875 - 4000)

        # Payments tab
        res_pay = c.get(reverse('reports:receivables_ageing'), {'tab': 'payments'})
        self.assertEqual(res_pay.status_code, 200)
        self.assertContains(res_pay, '4000.00')

        # CSV Export for ageing
        res_csv = c.get(reverse('reports:receivables_ageing'), {'export': 'csv'})
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('accounts_receivable_ageing_', res_csv['Content-Disposition'])

        # PDF Export for ageing
        res_pdf = c.get(reverse('reports:receivables_ageing'), {'export': 'pdf'})
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

        # Direct ageing report view in invoices app
        res_inv_ageing_csv = c.get(reverse('invoices:ageing_report'), {'export': 'csv'})
        self.assertEqual(res_inv_ageing_csv.status_code, 200)
        res_inv_ageing_pdf = c.get(reverse('invoices:ageing_report'), {'export': 'pdf'})
        self.assertEqual(res_inv_ageing_pdf.status_code, 200)

    # -------------------------------------------------------------------------
    # 8. Accountant Read-Only Restrictions
    # -------------------------------------------------------------------------

    def test_accountant_is_strictly_read_only_on_operational_mutations(self):
        """
        Accountant can view and export all reports, but is forbidden (403)
        from modifying operational transactions.
        """
        c = Client()
        c.login(username='rep_accountant', password=self.password)

        # Cannot dispatch invoices
        res1 = c.post(reverse('invoices:invoice_dispatch', kwargs={'pk': self.invoice.pk}))
        self.assertEqual(res1.status_code, 403)

        # Cannot cancel invoices
        res2 = c.post(reverse('invoices:invoice_cancel', kwargs={'pk': self.invoice.pk}), {'cancellation_reason': 'test'})
        self.assertEqual(res2.status_code, 403)

        # Cannot create production runs
        res3 = c.get(reverse('production:production_run_create'))
        self.assertEqual(res3.status_code, 403)

        # Cannot create purchase orders
        res4 = c.get(reverse('purchases:purchase_create'))
        self.assertEqual(res4.status_code, 403)

        # Cannot record physical stock adjustments
        res5 = c.get(reverse('inventory:stock_adjust'))
        self.assertEqual(res5.status_code, 403)

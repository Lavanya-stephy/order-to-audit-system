from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from masters.models import Unit, UnitCategory, Product, Customer, CustomerType
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement, get_item_current_stock
from orders.models import SalesOrder, SalesOrderLine, SalesOrderLog, OrderStatus
from orders.services import (
    create_sales_order,
    admin_update_order,
    approve_sales_order,
    reject_sales_order,
)

User = get_user_model()


class SalesOrderTests(TestCase):
    def setUp(self):
        self.password = 'Pass123!'
        self.salesman_a = User.objects.create_user(
            username='salesman_a', password=self.password, role=Role.SALESMAN
        )
        self.salesman_b = User.objects.create_user(
            username='salesman_b', password=self.password, role=Role.SALESMAN
        )
        self.admin = User.objects.create_user(
            username='admin_user', password=self.password, role=Role.ADMIN
        )

        # Units
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)

        # Finished Product with standard selling price ₹50.00, GST 5%
        self.product = Product.objects.create(
            name='Murukku 200 g',
            code='FG-MURUKKU-200G',
            unit=self.packet,
            pack_size=Decimal('200.00'),
            pack_size_unit=self.g,
            selling_price=Decimal('50.00'),
            gst_rate=Decimal('5.00'),
            carton_pack_qty=20,
        )

        # Customers: Retailer A (Tamil Nadu, Intra-state) and Distributor B (Karnataka, Inter-state)
        self.retailer_a = Customer.objects.create(
            name='Retailer A',
            customer_type=CustomerType.RETAILER,
            state='Tamil Nadu',
            state_code='33',
        )
        self.distributor_b = Customer.objects.create(
            name='Distributor B',
            customer_type=CustomerType.DISTRIBUTOR,
            state='Karnataka',
            state_code='29',
            gstin='29ABCDE1234F1Z5',
        )

    def test_salesman_order_creation_price_from_price_list(self):
        """
        Salesman places an order for Retailer A (150 packets).
        Price should automatically default to the product's selling price (₹50.00).
        Status should be 'submitted'.
        """
        order = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )

        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        self.assertEqual(order.salesman, self.salesman_a)
        self.assertEqual(order.customer, self.retailer_a)
        self.assertEqual(order.lines.count(), 1)

        line = order.lines.first()
        self.assertEqual(line.quantity, Decimal('150.00'))
        self.assertEqual(line.unit_price, Decimal('50.00'))  # from price list
        self.assertEqual(line.line_total, Decimal('7500.00'))
        self.assertEqual(order.total_quantity, Decimal('150.00'))
        self.assertEqual(order.subtotal, Decimal('7500.00'))
        # GST at 5% = ₹375.00
        self.assertEqual(order.total_tax, Decimal('375.00'))
        self.assertEqual(order.grand_total, Decimal('7875.00'))

        # Audit log verification
        log = order.audit_logs.first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, 'Submitted')
        self.assertEqual(log.user, self.salesman_a)

    def test_salesman_isolation_in_order_list_and_detail(self):
        """
        Salesman A and Salesman B each create an order.
        - Salesman A should only see Salesman A's order in list.
        - Salesman B should only see Salesman B's order in list.
        - Salesman A cannot access Salesman B's order detail (returns 403 Forbidden).
        """
        order_a = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )
        order_b = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )

        # Salesman A client
        client_a = Client()
        client_a.login(username='salesman_a', password=self.password)

        res_a = client_a.get(reverse('orders:salesman_order_list'))
        self.assertEqual(res_a.status_code, 200)
        self.assertIn(order_a, res_a.context['orders'])
        self.assertNotIn(order_b, res_a.context['orders'])

        # Salesman A views their own order -> 200 OK
        res_detail_a = client_a.get(reverse('orders:order_detail', kwargs={'pk': order_a.pk}))
        self.assertEqual(res_detail_a.status_code, 200)

        # Salesman A attempts to view Salesman B's order -> 403 Forbidden
        res_forbidden = client_a.get(reverse('orders:order_detail', kwargs={'pk': order_b.pk}))
        self.assertEqual(res_forbidden.status_code, 403)

        # Salesman B client
        client_b = Client()
        client_b.login(username='salesman_b', password=self.password)

        res_b = client_b.get(reverse('orders:salesman_order_list'))
        self.assertEqual(res_b.status_code, 200)
        self.assertIn(order_b, res_b.context['orders'])
        self.assertNotIn(order_a, res_b.context['orders'])

    def test_admin_sees_all_incoming_orders(self):
        """
        Admin sees incoming orders from both Salesman A and Salesman B.
        """
        order_a = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )
        order_b = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )

        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)

        res = admin_client.get(reverse('orders:admin_order_list'))
        self.assertEqual(res.status_code, 200)
        orders = [item['order'] for item in res.context['orders_with_coverage']]
        self.assertIn(order_a, orders)
        self.assertIn(order_b, orders)

    def test_finished_goods_stock_coverage_check(self):
        """
        Tests whether finished-goods stock covers the order:
        - When stock is 238 packets, order of 150 packets is COVERED (no shortage).
        - When stock is 88 packets, order of 120 packets has a SHORTAGE of 32 packets flagged.
        (Matches Benchmark Scenario Steps 4 & 6).
        """
        # Step 4 check: 238 finished goods in stock
        record_movement(
            item=self.product,
            quantity=Decimal('238.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-BENCHMARK-RUN-01',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('238.00'))

        order_150 = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )

        cov_150 = order_150.check_stock_coverage()
        self.assertTrue(cov_150['is_fully_covered'])
        self.assertEqual(cov_150['total_shortage'], Decimal('0.00'))
        self.assertTrue(order_150.is_stock_covered)

        # Dispatch 150 pkts -> stock reduces to 88 pkts (238 - 150)
        record_movement(
            item=self.product,
            quantity=Decimal('-150.00'),
            movement_type=MovementType.DISPATCH,
            source_document='INV-2026-001',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # Step 6 check: Salesman B places order for Distributor B: 120 packets
        order_120 = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )

        cov_120 = order_120.check_stock_coverage()
        self.assertFalse(cov_120['is_fully_covered'])
        # Shortage should be exactly 32 packets (120 - 88)
        self.assertEqual(cov_120['total_shortage'], Decimal('32.00'))
        line_cov = cov_120['lines'][0]
        self.assertEqual(line_cov['available_stock'], Decimal('88.00'))
        self.assertEqual(line_cov['requested_qty'], Decimal('120.00'))
        self.assertEqual(line_cov['shortage'], Decimal('32.00'))
        self.assertFalse(line_cov['is_covered'])

    def test_admin_can_edit_quantity_and_price(self):
        """
        Admin can edit the quantity and/or price of line items on an incoming order.
        Edits must be logged in the audit trail.
        """
        order = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )
        line = order.lines.first()

        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)

        # POST edit form: adjust quantity from 150 to 140, price from 50.00 to 48.00
        edit_url = reverse('orders:admin_order_edit', kwargs={'pk': order.pk})
        post_data = {
            'customer': str(self.retailer_a.id),
            'order_date': '2026-11-22',
            'notes': 'Admin adjusted quantity per customer credit review',
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '1',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-id': str(line.id),
            'lines-0-product': str(self.product.id),
            'lines-0-quantity': '140',
            'lines-0-unit': str(self.packet.id),
            'lines-0-unit_price': '48.00',
        }
        res = admin_client.post(edit_url, post_data)
        self.assertEqual(res.status_code, 302)  # Redirects to detail view

        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal('140.00'))
        self.assertEqual(line.unit_price, Decimal('48.00'))
        self.assertEqual(line.line_total, Decimal('6720.00'))  # 140 * 48

        order.refresh_from_db()
        self.assertEqual(order.notes, 'Admin adjusted quantity per customer credit review')

        # Check audit log
        edit_log = order.audit_logs.filter(action='Edited').first()
        self.assertIsNotNone(edit_log)
        self.assertEqual(edit_log.user, self.admin)
        self.assertIn('qty=140', edit_log.details)
        self.assertIn('price=₹48.00', edit_log.details)

    def test_admin_approve_and_reject_order(self):
        """
        Admin can approve or reject an order.
        Salesman cannot approve or reject (returns 403).
        """
        order = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )

        # Provide sufficient stock for order
        record_movement(
            item=self.product,
            quantity=Decimal('200.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-TEST-APPROVE',
        )

        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)

        # 1. Admin approves
        approve_url = reverse('orders:admin_order_approve', kwargs={'pk': order.pk})
        res = admin_client.post(approve_url, {'approval_notes': 'Stock checked, ready for billing'})
        self.assertEqual(res.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.APPROVED)
        self.assertEqual(order.approved_by, self.admin)
        self.assertIsNotNone(order.approved_at)

        log = order.audit_logs.filter(action='Approved').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.admin)

        # 2. Rejection test on another order
        order2 = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )
        reject_url = reverse('orders:admin_order_reject', kwargs={'pk': order2.pk})
        res_rej = admin_client.post(reject_url, {'rejection_reason': 'Insufficient production stock'})
        self.assertEqual(res_rej.status_code, 302)

        order2.refresh_from_db()
        self.assertEqual(order2.status, OrderStatus.REJECTED)
        self.assertEqual(order2.rejection_reason, 'Insufficient production stock')

        # 3. Salesman cannot approve or reject
        salesman_client = Client()
        salesman_client.login(username='salesman_a', password=self.password)
        order3 = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('50.00')}],
        )
        res_sec = salesman_client.post(reverse('orders:admin_order_approve', kwargs={'pk': order3.pk}))
        self.assertEqual(res_sec.status_code, 403)

    def test_mobile_order_entry_via_post(self):
        """
        Simulates the mobile order entry screen submitted by Salesman A.
        """
        client = Client()
        client.login(username='salesman_a', password=self.password)

        res = client.post(reverse('orders:order_create'), {
            'customer': str(self.retailer_a.id),
            'order_date': '2026-11-22',
            'notes': 'Urgent delivery before festival',
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-product': str(self.product.id),
            'lines-0-quantity': '150',
            'lines-0-unit': str(self.packet.id),
            'lines-0-unit_price': '',  # Omitted -> auto-fills from product price list
        })
        self.assertEqual(res.status_code, 302)

        order = SalesOrder.objects.filter(salesman=self.salesman_a).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.customer, self.retailer_a)
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        self.assertEqual(order.lines.count(), 1)
        line = order.lines.first()
        self.assertEqual(line.quantity, Decimal('150.00'))
        self.assertEqual(line.unit_price, Decimal('50.00'))  # Auto-filled!

    # ------------------------------------------------------------------
    # Role-visibility tests: salesman sees no ledger link / no stock qty
    # ------------------------------------------------------------------

    def _make_order_a(self):
        """Helper: create a submitted order owned by salesman_a."""
        return create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('50.00')}],
        )

    def test_salesman_order_detail_has_no_ledger_link_and_no_stock_numbers(self):
        """
        Salesman's order detail page must NOT contain:
          - 'View Stock Ledger' (the link text)
          - 'stock_summary' or 'stock_ledger' URLs
          - 'Current Stock in Ledger' (the stock quantity label)
        And it MUST contain one of 'Stock available' or 'Awaiting stock'.
        Backend 403 rules must remain intact for inventory pages.
        """
        order_a = self._make_order_a()
        client = Client()
        client.login(username='salesman_a', password=self.password)

        url = reverse('orders:order_detail', kwargs={'pk': order_a.pk})
        res = client.get(url)
        self.assertEqual(res.status_code, 200)

        content = res.content.decode()

        # No ledger link
        self.assertNotIn('View Stock Ledger', content)
        self.assertNotIn('stock_summary', content)
        self.assertNotIn('stock_ledger', content)

        # No raw stock quantity text
        self.assertNotIn('Current Stock in Ledger', content)

        # Exactly one of the two status messages must be present
        has_available = 'Stock available' in content
        has_awaiting = 'Awaiting stock' in content
        self.assertTrue(
            has_available or has_awaiting,
            "Expected 'Stock available' or 'Awaiting stock' in salesman order detail page",
        )

        # Backend permission: salesman still gets 403 on inventory pages
        res_stock = client.get(reverse('inventory:stock_summary'))
        self.assertEqual(res_stock.status_code, 403)
        res_ledger = client.get(reverse('inventory:stock_ledger'))
        self.assertEqual(res_ledger.status_code, 403)

    def test_admin_order_detail_shows_stock_numbers_and_ledger_link(self):
        """
        Admin's order detail page MUST contain:
          - 'View Stock Ledger' (the link text)
          - 'Current Stock in Ledger' (the stock quantity label)
        """
        order_a = self._make_order_a()

        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)

        url = reverse('orders:order_detail', kwargs={'pk': order_a.pk})
        res = admin_client.get(url)
        self.assertEqual(res.status_code, 200)

        content = res.content.decode()
        self.assertIn('View Stock Ledger', content)
        self.assertIn('Current Stock in Ledger', content)

    def test_dispatched_order_shows_no_shortage_and_neutral_message(self):
        """
        For Dispatched orders:
        - stock coverage check is not calculated as shortage (total_shortage == 0, is_fully_covered == True)
        - Detail page displays neutral message 'Dispatched: 150 packets deducted from stock on <date>'
        - Detail page includes a link to the ledger entry for non-salesmen
        - No shortage banner is shown
        """
        # Set up 238 pkts initial stock
        record_movement(
            item=self.product,
            quantity=Decimal('238.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-BENCHMARK-RUN-01',
        )
        order = create_sales_order(
            salesman=self.salesman_a,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('150.00')}],
        )
        approve_sales_order(order, self.admin)
        from invoices.services import generate_invoice, dispatch_invoice
        invoice = generate_invoice(order, self.admin)
        dispatch_invoice(invoice, self.admin)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DISPATCHED)
        # Current stock is now 88 (238 - 150)
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # Check coverage logic: must NOT flag shortage of 62 pkts
        cov = order.check_stock_coverage()
        self.assertFalse(cov['is_applicable'])
        self.assertTrue(cov['is_dispatched'])
        self.assertTrue(cov['is_fully_covered'])
        self.assertEqual(cov['total_shortage'], Decimal('0.00'))
        self.assertTrue(order.is_stock_covered)

        # Admin client views order detail page
        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)
        res = admin_client.get(reverse('orders:order_detail', kwargs={'pk': order.pk}))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode()

        # Must display neutral message
        self.assertIn("Dispatched: 150 packets deducted from stock on", content)
        # Must link to the ledger entry
        self.assertIn("View Ledger Entry", content)
        self.assertIn(reverse('inventory:stock_ledger'), content)
        # Must NOT show shortage banner
        self.assertNotIn("Stock Shortage Flagged", content)
        self.assertNotIn("Shortage of 62 packets", content)

        # In admin incoming orders list, should show Dispatched pill and no shortage
        res_list = admin_client.get(reverse('orders:admin_order_list'))
        self.assertEqual(res_list.status_code, 200)
        content_list = res_list.content.decode()
        self.assertIn("Dispatched (Deducted)", content_list)

    def test_pending_order_shows_exact_shortage_when_stock_insufficient(self):
        """
        For a pending order (Submitted/Approved/Invoiced before dispatch):
        shortage = requested quantity minus current stock, only when positive.
        Distributor B's 120-packet order must show a shortage of exactly 32 when stock is 88.
        """
        # Ensure stock is exactly 88 packets
        record_movement(
            item=self.product,
            quantity=Decimal('88.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-BENCHMARK-RUN-INIT',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # Distributor B places 120 packets order
        order_120 = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )
        self.assertEqual(order_120.status, OrderStatus.SUBMITTED)

        cov = order_120.check_stock_coverage()
        self.assertTrue(cov['is_applicable'])
        self.assertFalse(cov['is_fully_covered'])
        self.assertEqual(cov['total_shortage'], Decimal('32.00'))
        self.assertEqual(cov['lines'][0]['shortage'], Decimal('32.00'))
        self.assertEqual(cov['lines'][0]['available_stock'], Decimal('88.00'))
        self.assertEqual(cov['lines'][0]['requested_qty'], Decimal('120.00'))
        self.assertFalse(order_120.is_stock_covered)

        # Admin view should show shortage banner with 32 packets
        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)
        res = admin_client.get(reverse('orders:order_detail', kwargs={'pk': order_120.pk}))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode()
        self.assertIn("Stock Shortage Flagged! Shortage of 32 packets", content)
        self.assertIn("32 pkts short!", content)

    def test_order_approval_blocked_on_insufficient_stock_and_allowed_after_production(self):
        """
        Verify that when available stock is 88 packets and salesman requests 120 packets:
        1. Shortage of 32 packets is displayed in order detail with available stock 88.
        2. Frontend blocks/disables the approval action in both detail view and admin list.
        3. Backend validation in approve_sales_order blocks approval, keeping order in Pending status.
        4. Invoice generation is blocked for pending/insufficient orders, and no stock is deducted.
        5. Once sufficient stock is replenished through production (e.g. +50 pkts -> 138 pkts >= 120),
           admin is allowed to approve order, generate invoice, and dispatch normally.
        """
        from django.core.exceptions import ValidationError
        from invoices.services import generate_invoice

        # 1. Ensure finished-goods stock is 88 packets
        record_movement(
            item=self.product,
            quantity=Decimal('88.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-BENCHMARK-RUN-88',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # Salesman B orders 120 packets
        order = create_sales_order(
            salesman=self.salesman_b,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )
        self.assertEqual(order.status, OrderStatus.SUBMITTED)

        # Verify stock coverage calculates shortage of 32 packets
        cov = order.check_stock_coverage()
        self.assertFalse(cov['is_fully_covered'])
        self.assertEqual(cov['total_shortage'], Decimal('32.00'))
        self.assertEqual(cov['lines'][0]['available_stock'], Decimal('88.00'))
        self.assertEqual(cov['lines'][0]['requested_qty'], Decimal('120.00'))
        self.assertEqual(cov['lines'][0]['shortage'], Decimal('32.00'))

        admin_client = Client()
        admin_client.login(username='admin_user', password=self.password)

        # 2. Frontend verification: approval action is disabled/blocked in UI
        res_detail = admin_client.get(reverse('orders:order_detail', kwargs={'pk': order.pk}))
        self.assertEqual(res_detail.status_code, 200)
        content_detail = res_detail.content.decode()
        self.assertIn("Approval Blocked", content_detail)
        self.assertIn("Shortage of 32 packets", content_detail)
        self.assertIn("Shortage: 32 pkts short!", content_detail)

        # In admin orders list, approve button is disabled
        res_list = admin_client.get(reverse('orders:admin_order_list'))
        self.assertEqual(res_list.status_code, 200)
        content_list = res_list.content.decode()
        self.assertIn("Cannot approve: Insufficient stock (Shortage: 32 pkts)", content_list)

        # 3. Backend validation enforcement in approve_sales_order
        with self.assertRaises(ValidationError) as ctx:
            approve_sales_order(order, self.admin)
        self.assertIn("Insufficient finished-goods stock", str(ctx.exception))
        self.assertIn("shortage of 32 packets", str(ctx.exception))

        # Order must remain in Pending (SUBMITTED) status
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)

        # Attempting approval via POST view must also be blocked and keep order pending
        res_post = admin_client.post(
            reverse('orders:admin_order_approve', kwargs={'pk': order.pk}),
            {'approval_notes': 'Trying to force approval'},
            follow=True
        )
        self.assertEqual(res_post.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        content_after_post = res_post.content.decode()
        self.assertIn("Insufficient finished-goods stock", content_after_post)
        self.assertIn("shortage of 32 packets", content_after_post)

        # 4. Invoicing and stock deduction blocked for pending/insufficient orders
        with self.assertRaises(ValueError):
            generate_invoice(order, user=self.admin)

        inv_post = admin_client.post(
            reverse('invoices:invoice_generate', kwargs={'order_pk': order.pk}),
            follow=True
        )
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
        self.assertFalse(hasattr(order, 'invoice') and order.invoice is not None)
        # Verify no stock deduction happened (still exactly 88 packets)
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # 5. Replenish stock through production: +50 packets -> 138 packets total
        record_movement(
            item=self.product,
            quantity=Decimal('50.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-PROD-REPLENISH-01',
            user=self.admin,
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('138.00'))

        # Now stock is sufficient: 138 >= 120
        cov_after = order.check_stock_coverage()
        self.assertTrue(cov_after['is_fully_covered'])
        self.assertEqual(cov_after['total_shortage'], Decimal('0.00'))

        # Frontend allows approval
        res_detail_ready = admin_client.get(reverse('orders:order_detail', kwargs={'pk': order.pk}))
        self.assertEqual(res_detail_ready.status_code, 200)
        self.assertIn("✅ Approve Order", res_detail_ready.content.decode())

        # Admin approves order successfully
        res_approve = admin_client.post(
            reverse('orders:admin_order_approve', kwargs={'pk': order.pk}),
            {'approval_notes': 'Stock replenished via production, approved.'},
            follow=True
        )
        self.assertEqual(res_approve.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.APPROVED)
        self.assertEqual(order.approved_by, self.admin)

        # Admin generates GST invoice normally
        res_inv = admin_client.post(
            reverse('invoices:invoice_generate', kwargs={'order_pk': order.pk}),
            follow=True
        )
        self.assertEqual(res_inv.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.INVOICED)
        invoice = order.invoice
        self.assertIsNotNone(invoice)

        # Admin dispatches invoice, deducting the 120 packets from stock
        res_dispatch = admin_client.post(
            reverse('invoices:invoice_dispatch', kwargs={'pk': invoice.pk}),
            follow=True
        )
        self.assertEqual(res_dispatch.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DISPATCHED)
        # Remaining stock: 138 - 120 = 18 packets
        self.assertEqual(get_item_current_stock(self.product), Decimal('18.00'))


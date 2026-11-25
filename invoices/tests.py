"""
invoices/tests.py

GST Invoice test suite covering:
  1. Intra-state (Retailer A, Tamil Nadu): 150 pkts → ₹7500 taxable + CGST ₹187.50 + SGST ₹187.50 = ₹7875
     After dispatch, finished-goods stock goes from 238 to 88.
  2. Inter-state (Distributor B, Karnataka): 120-pkt order shows shortage of 32; uses IGST.
  3. Credit-note cancellation: invoice not deleted, CN number issued, stock reversed if dispatched.
  4. Invoice numbering per financial year.
  5. Double-invoice guard.
  6. PDF generation (content-type check).
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role
from masters.models import Unit, UnitCategory, Product, Customer, CustomerType
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement, get_item_current_stock
from orders.models import SalesOrder, OrderStatus
from orders.services import create_sales_order, approve_sales_order
from invoices.models import Invoice, InvoiceLine, InvoiceStatus
from invoices.services import (
    generate_invoice,
    dispatch_invoice,
    cancel_invoice,
    _financial_year,
)

User = get_user_model()


class InvoiceTestBase(TestCase):
    """Shared setUp for all invoice tests."""

    def setUp(self):
        self.password = 'Pass123!'
        self.admin = User.objects.create_user(
            username='admin', password=self.password, role=Role.ADMIN
        )
        self.salesman = User.objects.create_user(
            username='salesman', password=self.password, role=Role.SALESMAN
        )
        self.accountant = User.objects.create_user(
            username='accountant', password=self.password, role=Role.ACCOUNTANT
        )

        # Units
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)

        # Finished product: Murukku 200g, GST 5%, ₹50/pkt
        self.product = Product.objects.create(
            name='Murukku 200 g',
            code='FG-MURUKKU-200G',
            unit=self.packet,
            pack_size=Decimal('200.00'),
            pack_size_unit=self.g,
            selling_price=Decimal('50.00'),
            gst_rate=Decimal('5.00'),
            carton_pack_qty=20,
            hsn_code='19059040',
        )

        # Customers
        self.retailer_a = Customer.objects.create(
            name='Retailer A',
            customer_type=CustomerType.RETAILER,
            state='Tamil Nadu',
            state_code='33',       # Intra-state
        )
        self.distributor_b = Customer.objects.create(
            name='Distributor B',
            customer_type=CustomerType.DISTRIBUTOR,
            state='Karnataka',
            state_code='29',       # Inter-state
            gstin='29ABCDE1234F1Z5',
        )

    def _ensure_stock(self, product=None, qty=Decimal('100.00')):
        prod = product or self.product
        current = get_item_current_stock(prod)
        if current < qty:
            record_movement(
                item=prod,
                quantity=qty - current,
                movement_type=MovementType.PRODUCTION_OUTPUT,
                source_document='PR-TEST-HELPER',
                user=self.admin,
            )


# ---------------------------------------------------------------------------
# 1. Intra-state invoice: CGST + SGST
# ---------------------------------------------------------------------------

class IntraStateInvoiceTests(InvoiceTestBase):

    def _approved_order(self, qty=Decimal('150.00')):
        """Create and approve a 150-pkt order for Retailer A."""
        self._ensure_stock(self.product, qty)
        order = create_sales_order(
            salesman=self.salesman,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': qty}],
        )
        approve_sales_order(order, self.admin)
        return order

    def test_invoice_amounts_intra_state(self):
        """
        150 pkts × ₹50 = ₹7500 taxable
        CGST 2.5% = ₹187.50, SGST 2.5% = ₹187.50
        Grand Total = ₹7875.00
        """
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)

        self.assertEqual(inv.status, InvoiceStatus.POSTED)
        self.assertFalse(inv.is_interstate)
        self.assertEqual(inv.taxable_value, Decimal('7500.00'))
        self.assertEqual(inv.cgst_amount,   Decimal('187.50'))
        self.assertEqual(inv.sgst_amount,   Decimal('187.50'))
        self.assertEqual(inv.igst_amount,   Decimal('0.00'))
        self.assertEqual(inv.grand_total,   Decimal('7875.00'))

        # Verify line-level breakdown
        line = inv.lines.first()
        self.assertEqual(line.hsn_code,     '19059040')
        self.assertEqual(line.taxable_value, Decimal('7500.00'))
        self.assertEqual(line.cgst_rate,    Decimal('2.50'))
        self.assertEqual(line.sgst_rate,    Decimal('2.50'))
        self.assertEqual(line.igst_rate,    Decimal('0.00'))
        self.assertEqual(line.cgst_amount,  Decimal('187.50'))
        self.assertEqual(line.sgst_amount,  Decimal('187.50'))
        self.assertEqual(line.igst_amount,  Decimal('0.00'))
        self.assertEqual(line.line_total,   Decimal('7875.00'))

        # Order transitions to INVOICED
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.INVOICED)

    def test_dispatch_reduces_finished_goods_stock(self):
        """
        Start with 238 pkts in stock.
        Invoice 150 pkts to Retailer A, then dispatch.
        Finished goods must become 238 - 150 = 88 pkts.
        """
        # Seed 238 pkts of finished goods
        record_movement(
            item=self.product,
            quantity=Decimal('238.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-TEST-01',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('238.00'))

        order = self._approved_order(qty=Decimal('150.00'))
        inv = generate_invoice(order, user=self.admin)
        dispatch_invoice(inv, user=self.admin)

        inv.refresh_from_db()
        self.assertTrue(inv.is_dispatched)
        self.assertIsNotNone(inv.dispatched_at)

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DISPATCHED)

        # Closing stock = 238 - 150 = 88
        closing = get_item_current_stock(self.product)
        self.assertEqual(closing, Decimal('88.00'))

    def test_invoice_number_format_financial_year(self):
        """Invoice numbers follow INV-YYYY-YY-NNNN per FY."""
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)

        today = timezone.localdate()
        expected_fy = _financial_year(today)
        self.assertTrue(
            inv.invoice_number.startswith(f"INV-{expected_fy}-"),
            f"Expected prefix 'INV-{expected_fy}-', got '{inv.invoice_number}'",
        )
        # Sequence part is a 4-digit number
        seq = inv.invoice_number.rsplit('-', 1)[-1]
        self.assertTrue(seq.isdigit() and len(seq) == 4)

    def test_no_double_invoice(self):
        """Generating a second invoice for the same order raises ValueError."""
        order = self._approved_order()
        generate_invoice(order, user=self.admin)
        order.refresh_from_db()
        # Artificially re-approve to try again (bypasses status guard)
        order.status = OrderStatus.APPROVED
        order.save()
        with self.assertRaises(ValueError):
            generate_invoice(order, user=self.admin)

    def test_generate_requires_approved_status(self):
        """Generating from a submitted (not yet approved) order raises ValueError."""
        order = create_sales_order(
            salesman=self.salesman,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('50.00')}],
        )
        # Order is SUBMITTED not APPROVED
        with self.assertRaises(ValueError):
            generate_invoice(order, user=self.admin)


# ---------------------------------------------------------------------------
# 2. Inter-state invoice: IGST + shortage check
# ---------------------------------------------------------------------------

class InterStateInvoiceTests(InvoiceTestBase):

    def test_distributor_b_120_pkts_uses_igst_and_shows_shortage(self):
        """
        Distributor B (Karnataka) orders 120 pkts.
        Stock seeded at 88 pkts → shortage = 32 pkts.
        Invoice uses IGST (full 5% = ₹300), not CGST+SGST.
        """
        # Stock: 88 pkts only
        record_movement(
            item=self.product,
            quantity=Decimal('88.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-TEST-02',
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('88.00'))

        # Verify stock coverage shows shortage of 32
        order_b = create_sales_order(
            salesman=self.salesman,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )
        coverage = order_b.check_stock_coverage()
        self.assertFalse(coverage['is_fully_covered'])
        self.assertEqual(coverage['total_shortage'], Decimal('32.00'))

        # Approval and invoicing blocked while stock is insufficient
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            approve_sales_order(order_b, self.admin)

        with self.assertRaises(ValueError):
            generate_invoice(order_b, user=self.admin)

        # Replenish stock through production: +50 pkts -> 138 pkts total
        record_movement(
            item=self.product,
            quantity=Decimal('50.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-REPLENISH-02',
            user=self.admin,
        )
        self.assertEqual(get_item_current_stock(self.product), Decimal('138.00'))

        # Now admin can approve and invoice
        approve_sales_order(order_b, self.admin)
        inv = generate_invoice(order_b, user=self.admin)

        self.assertTrue(inv.is_interstate)
        self.assertEqual(inv.customer_gstin, '29ABCDE1234F1Z5')

        # IGST: 120 × 50 = 6000 taxable; 5% IGST = 300; total 6300
        self.assertEqual(inv.taxable_value, Decimal('6000.00'))
        self.assertEqual(inv.igst_amount,   Decimal('300.00'))
        self.assertEqual(inv.cgst_amount,   Decimal('0.00'))
        self.assertEqual(inv.sgst_amount,   Decimal('0.00'))
        self.assertEqual(inv.grand_total,   Decimal('6300.00'))

        line = inv.lines.first()
        self.assertEqual(line.igst_rate,   Decimal('5.00'))
        self.assertEqual(line.cgst_rate,   Decimal('0.00'))
        self.assertEqual(line.sgst_rate,   Decimal('0.00'))
        self.assertEqual(line.igst_amount, Decimal('300.00'))


# ---------------------------------------------------------------------------
# 3. Credit-note cancellation
# ---------------------------------------------------------------------------

class InvoiceCancellationTests(InvoiceTestBase):

    def _post_invoice(self):
        self._ensure_stock(self.product, Decimal('50.00'))
        order = create_sales_order(
            salesman=self.salesman,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('50.00')}],
        )
        approve_sales_order(order, self.admin)
        return generate_invoice(order, user=self.admin)

    def test_cancel_posted_invoice_issues_credit_note(self):
        """Cancel a posted invoice: get a CN number, never deleted, order back to APPROVED."""
        inv = self._post_invoice()
        self.assertEqual(inv.status, InvoiceStatus.POSTED)

        cancel_invoice(inv, reason='Customer cancelled order', user=self.admin)
        inv.refresh_from_db()

        self.assertEqual(inv.status, InvoiceStatus.CANCELLED)
        self.assertIsNotNone(inv.cancelled_at)
        self.assertTrue(inv.credit_note_number.startswith('CN-'))
        self.assertEqual(inv.cancellation_reason, 'Customer cancelled order')
        self.assertEqual(inv.cancelled_by, self.admin)

        # Invoice is still in DB (never deleted)
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())

        # Order returns to APPROVED for re-invoicing
        inv.order.refresh_from_db()
        self.assertEqual(inv.order.status, OrderStatus.APPROVED)

    def test_cancel_dispatched_invoice_reverses_stock(self):
        """
        Dispatch then cancel: stock must be fully restored.
        """
        record_movement(
            item=self.product,
            quantity=Decimal('100.00'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='PR-TEST-03',
        )
        inv = self._post_invoice()      # 50 pkts
        dispatch_invoice(inv, user=self.admin)
        self.assertEqual(get_item_current_stock(self.product), Decimal('50.00'))

        cancel_invoice(inv, reason='Goods returned', user=self.admin)
        # Stock reversed: 50 + 50 = 100 again
        self.assertEqual(get_item_current_stock(self.product), Decimal('100.00'))

    def test_cannot_cancel_already_cancelled(self):
        """Double cancellation raises ValueError."""
        inv = self._post_invoice()
        cancel_invoice(inv, reason='First cancellation', user=self.admin)
        inv.refresh_from_db()
        with self.assertRaises(ValueError):
            cancel_invoice(inv, reason='Second cancellation', user=self.admin)


# ---------------------------------------------------------------------------
# 4. View / permission tests
# ---------------------------------------------------------------------------

class InvoiceViewTests(InvoiceTestBase):

    def _approved_order(self):
        self._ensure_stock(self.product, Decimal('30.00'))
        order = create_sales_order(
            salesman=self.salesman,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': Decimal('30.00')}],
        )
        approve_sales_order(order, self.admin)
        return order

    def test_admin_can_generate_invoice_via_post(self):
        order = self._approved_order()
        c = Client()
        c.login(username='admin', password=self.password)
        url = reverse('invoices:invoice_generate', kwargs={'order_pk': order.pk})
        res = c.post(url)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Invoice.objects.filter(order=order).exists())

    def test_salesman_cannot_access_invoice_list(self):
        c = Client()
        c.login(username='salesman', password=self.password)
        res = c.get(reverse('invoices:invoice_list'))
        self.assertEqual(res.status_code, 403)

    def test_accountant_can_view_invoice_list_and_detail(self):
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)
        c = Client()
        c.login(username='accountant', password=self.password)
        res = c.get(reverse('invoices:invoice_list'))
        self.assertEqual(res.status_code, 200)
        res2 = c.get(reverse('invoices:invoice_detail', kwargs={'pk': inv.pk}))
        self.assertEqual(res2.status_code, 200)

    def test_accountant_cannot_dispatch(self):
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)
        c = Client()
        c.login(username='accountant', password=self.password)
        res = c.post(reverse('invoices:invoice_dispatch', kwargs={'pk': inv.pk}))
        self.assertEqual(res.status_code, 403)

    def test_pdf_download_returns_pdf(self):
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)
        c = Client()
        c.login(username='admin', password=self.password)
        res = c.get(reverse('invoices:invoice_pdf', kwargs={'pk': inv.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        # PDF starts with %PDF header
        self.assertTrue(res.content[:5] == b'%PDF-')
        # Content-Disposition has the invoice number
        self.assertIn(inv.invoice_number, res['Content-Disposition'])

    def test_pdf_generation_without_errors(self):
        """Tests that build_invoice_pdf runs without errors and produces valid PDF bytes."""
        from invoices.pdf import build_invoice_pdf, amount_to_words
        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)

        # Test amount in words for 7875.00 and invoice total
        self.assertEqual(amount_to_words(Decimal('7875.00')), "Rupees Seven Thousand Eight Hundred and Seventy-Five Only")
        words = amount_to_words(inv.grand_total)
        self.assertEqual(words, "Rupees One Thousand Five Hundred and Seventy-Five Only")

        # Test direct PDF building without error
        buf = build_invoice_pdf(inv)
        pdf_bytes = buf.getvalue()
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_pdf_generation_interstate_without_errors(self):
        """Tests that build_invoice_pdf for an inter-state invoice (IGST) builds without errors."""
        from invoices.pdf import build_invoice_pdf
        self._ensure_stock(self.product, Decimal('120.00'))
        order_b = create_sales_order(
            salesman=self.salesman,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('120.00')}],
        )
        approve_sales_order(order_b, self.admin)
        inv = generate_invoice(order_b, user=self.admin)

        buf = build_invoice_pdf(inv)
        pdf_bytes = buf.getvalue()
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_factory_seller_details_and_dummy_data_note(self):
        """
        Verify that factory (seller) details use the fictional company 'Demo Snacks Pvt Ltd',
        dummy GSTIN in valid format, and includes the evaluation notice.
        """
        from invoices.pdf import FACTORY_NAME, FACTORY_ADDRESS, FACTORY_GSTIN, FACTORY_STATE, build_invoice_pdf
        from invoices.models import FACTORY_NAME as M_FACTORY_NAME, FACTORY_GSTIN as M_FACTORY_GSTIN
        from django.conf import settings

        self.assertEqual(FACTORY_NAME, "Demo Snacks Pvt Ltd")
        self.assertEqual(M_FACTORY_NAME, "Demo Snacks Pvt Ltd")
        self.assertEqual(settings.FACTORY_NAME, "Demo Snacks Pvt Ltd")
        self.assertEqual(FACTORY_ADDRESS, "12 Industrial Estate, Tiruchirappalli - 620001, Tamil Nadu")
        self.assertEqual(FACTORY_STATE, "Tamil Nadu (33)")
        self.assertEqual(FACTORY_GSTIN, "33AAAAA0000A1Z5")
        self.assertEqual(M_FACTORY_GSTIN, "33AAAAA0000A1Z5")

        # Verify GSTIN structure: 2 digits (33), 10 char PAN (5 letters + 4 digits + 1 letter), 1 entity digit, Z, 1 check digit
        self.assertTrue(FACTORY_GSTIN.startswith('33'))
        self.assertEqual(len(FACTORY_GSTIN), 15)

        order = self._approved_order()
        inv = generate_invoice(order, user=self.admin)
        buf = build_invoice_pdf(inv)
        pdf_bytes = buf.getvalue()
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))


# ---------------------------------------------------------------------------
# Payment Recording, Customer Balances & Ageing Report Tests
# ---------------------------------------------------------------------------

class InvoicePaymentAndAgeingTests(InvoiceTestBase):
    def _create_retailer_a_invoice(self, qty=Decimal('150.00')):
        self._ensure_stock(self.product, qty)
        order = create_sales_order(
            salesman=self.salesman,
            customer=self.retailer_a,
            lines_data=[{'product': self.product, 'quantity': qty}],
        )
        approve_sales_order(order, self.admin)
        return generate_invoice(order, user=self.admin)

    def test_retailer_a_pays_4000_outstanding_is_3875(self):
        """
        User Requirement Test:
        Retailer A orders 150 packets -> Invoice grand total = 7500 + 187.50 + 187.50 = 7875.00
        Retailer A pays 4000.
        Outstanding is 3875 (7875 - 4000 = 3875).
        """
        from invoices.models import PaymentMode
        from invoices.services import record_payment, get_ageing_report, get_customer_outstanding_balance

        inv = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        self.assertEqual(inv.grand_total, Decimal('7875.00'))
        self.assertEqual(inv.amount_paid, Decimal('0.00'))
        self.assertEqual(inv.outstanding_balance, Decimal('7875.00'))
        self.assertEqual(self.retailer_a.outstanding_balance, Decimal('7875.00'))

        # Record payment of 4000
        payment = record_payment(
            invoice=inv,
            amount=Decimal('4000.00'),
            payment_mode=PaymentMode.BANK_TRANSFER,
            reference_number='NEFT-RET-A-001',
            user=self.accountant,
        )

        self.assertIsNotNone(payment.payment_number)
        self.assertTrue(payment.payment_number.startswith('PAY-'))
        self.assertEqual(payment.amount, Decimal('4000.00'))

        # Invoice balances after payment
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal('4000.00'))
        self.assertEqual(inv.outstanding_balance, Decimal('3875.00'))
        self.assertEqual(inv.payment_status, 'partially_paid')

        # Customer outstanding balance after payment
        self.assertEqual(self.retailer_a.outstanding_balance, Decimal('3875.00'))
        self.assertEqual(get_customer_outstanding_balance(self.retailer_a), Decimal('3875.00'))

        # Check Ageing Report reflects the 3875 outstanding in 0-30 days
        report = get_ageing_report(as_of_date=inv.invoice_date)
        self.assertEqual(report['summary']['total_receivables'], Decimal('3875.00'))
        self.assertEqual(report['summary']['total_0_30'], Decimal('3875.00'))
        cust_entry = next(c for c in report['customers'] if c['customer'].id == self.retailer_a.id)
        self.assertEqual(cust_entry['total_outstanding'], Decimal('3875.00'))
        self.assertEqual(cust_entry['bucket_0_30'], Decimal('3875.00'))

        # Full settlement: Retailer A pays remaining 3875
        payment_2 = record_payment(
            invoice=inv,
            amount=Decimal('3875.00'),
            payment_mode=PaymentMode.UPI,
            reference_number='UPI-RET-A-002',
            user=self.admin,
        )
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal('7875.00'))
        self.assertEqual(inv.outstanding_balance, Decimal('0.00'))
        self.assertEqual(inv.payment_status, 'paid')
        self.assertTrue(inv.is_fully_paid)
        self.assertEqual(self.retailer_a.outstanding_balance, Decimal('0.00'))

        # After full settlement, Ageing Report has 0 receivables
        report_settled = get_ageing_report(as_of_date=inv.invoice_date)
        self.assertEqual(report_settled['summary']['total_receivables'], Decimal('0.00'))

    def test_overpayment_validation(self):
        """Cannot record a payment amount greater than the outstanding invoice balance."""
        from invoices.services import record_payment
        inv = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        with self.assertRaises(ValueError):
            record_payment(inv, amount=Decimal('8000.00'), user=self.admin)

    def test_cannot_pay_cancelled_invoice(self):
        """Cannot record payment against a cancelled invoice."""
        from invoices.services import record_payment, cancel_invoice
        inv = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        cancel_invoice(inv, reason='Customer cancelled', user=self.admin)
        with self.assertRaises(ValueError):
            record_payment(inv, amount=Decimal('1000.00'), user=self.admin)

    def test_ageing_report_buckets(self):
        """
        Verify ageing buckets: 0-30, 31-60, 61-90, 90+ days.
        """
        from datetime import timedelta
        from invoices.services import get_ageing_report

        today = timezone.localdate()
        # Create an invoice for Retailer A with date 45 days in the past
        inv_45d = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        inv_45d.invoice_date = today - timedelta(days=45)
        inv_45d.save(update_fields=['invoice_date'])

        # Create an invoice for Distributor B with date 95 days in the past
        self._ensure_stock(self.product, Decimal('100.00'))
        order_b = create_sales_order(
            salesman=self.salesman,
            customer=self.distributor_b,
            lines_data=[{'product': self.product, 'quantity': Decimal('100.00')}],
        )
        approve_sales_order(order_b, self.admin)
        inv_95d = generate_invoice(order_b, user=self.admin)
        inv_95d.invoice_date = today - timedelta(days=95)
        inv_95d.save(update_fields=['invoice_date'])

        report = get_ageing_report(as_of_date=today)
        self.assertEqual(report['summary']['total_31_60'], Decimal('7875.00'))  # Retailer A
        self.assertEqual(report['summary']['total_90_plus'], inv_95d.grand_total)  # Distributor B
        self.assertEqual(report['summary']['total_0_30'], Decimal('0.00'))

    def test_payment_view_post_and_role_access(self):
        """
        Test HTTP POST to record payment:
        - Admin and Accountant can post payments
        - Salesman cannot post payments (403)
        """
        inv = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        client = Client()
        client.login(username='accountant', password=self.password)

        url = reverse('invoices:record_payment', kwargs={'pk': inv.pk})
        res = client.post(url, {
            'amount': '4000.00',
            'payment_date': str(timezone.localdate()),
            'payment_mode': 'bank_transfer',
            'reference_number': 'REF1234',
            'notes': 'Advance payment',
        })
        self.assertEqual(res.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.outstanding_balance, Decimal('3875.00'))

        # Salesman cannot record payments
        salesman_client = Client()
        salesman_client.login(username='salesman', password=self.password)
        res_salesman = salesman_client.post(url, {'amount': '1000.00'})
        self.assertEqual(res_salesman.status_code, 403)

    def test_customer_balances_view_and_ageing_view(self):
        """Test GET customer balances and ageing report views."""
        from invoices.services import record_payment

        inv = self._create_retailer_a_invoice(qty=Decimal('150.00'))
        record_payment(inv, amount=Decimal('4000.00'), user=self.admin)

        client = Client()
        client.login(username='admin', password=self.password)

        # Balances view
        res_bal = client.get(reverse('invoices:customer_balances'))
        self.assertEqual(res_bal.status_code, 200)
        content_bal = res_bal.content.decode()
        self.assertIn('Retailer A', content_bal)
        self.assertIn('3875', content_bal)

        # Ageing report view
        res_age = client.get(reverse('invoices:ageing_report'))
        self.assertEqual(res_age.status_code, 200)
        content_age = res_age.content.decode()
        self.assertIn('3875', content_age)
        self.assertIn('0 – 30 Days', content_age)

        # Payments list view
        res_pay = client.get(reverse('invoices:payment_list'))
        self.assertEqual(res_pay.status_code, 200)
        content_pay = res_pay.content.decode()
        self.assertIn('4000', content_pay)






from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import Role
from masters.models import Unit, UnitCategory, RawMaterial, PackagingItem, Supplier
from inventory.models import StockMovement, MovementType
from inventory.services import get_item_current_stock
from purchases.models import PurchaseOrder, PurchaseOrderLine
from purchases.services import receive_purchase_order

User = get_user_model()


class PurchaseLedgerTests(TestCase):
    """Tests that receiving a PO correctly increases stock through the ledger."""

    def setUp(self):
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)

        self.supplier = Supplier.objects.create(
            name='Sri Murugan Flour Mills',
            city='Trichy',
            state='Tamil Nadu',
            state_code='33',
        )
        self.flour = RawMaterial.objects.create(
            name='Flour', code='RM-FLOUR', unit=self.kg,
            standard_cost=Decimal('42.00'),
        )
        self.pouch = PackagingItem.objects.create(
            name='200 g pouch', code='PM-POUCH-200G', unit=self.piece,
            standard_cost=Decimal('2.50'), capacity_packets=1,
        )
        self.user = User.objects.create_user(
            username='admin_test', password='pw', role=Role.ADMIN
        )

        # Seed opening stock: flour = 100 kg
        StockMovement.objects.create(
            raw_material=self.flour,
            quantity=Decimal('100.0000'),
            unit=self.kg,
            movement_type=MovementType.OPENING,
            source_document='OPENING-TEST',
        )

    def _make_draft_po(self, po_number='PO-TEST-001', qty=Decimal('60.0000'),
                       rate=Decimal('45.00')):
        po = PurchaseOrder.objects.create(
            po_number=po_number,
            supplier=self.supplier,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            po=po,
            raw_material=self.flour,
            quantity=qty,
            unit=self.kg,
            unit_price=rate,
        )
        return po

    # ------------------------------------------------------------------
    # Benchmark test: 60 kg flour @ ₹45/kg → balance 160 kg
    # ------------------------------------------------------------------
    def test_benchmark_purchase_60kg_flour_balance_becomes_160(self):
        """
        PROBLEM.md Step 1:
        Purchase 60 kg flour at ₹45/kg.
        Opening balance: 100 kg.
        Expected closing balance: 100 + 60 = 160 kg.
        """
        self.assertEqual(get_item_current_stock(self.flour), Decimal('100.0000'))

        po = self._make_draft_po()
        movements = receive_purchase_order(po, user=self.user)

        self.assertEqual(len(movements), 1)
        movement = movements[0]
        self.assertEqual(movement.movement_type, MovementType.PURCHASE)
        self.assertEqual(movement.quantity, Decimal('60.0000'))
        self.assertEqual(movement.unit_cost, Decimal('45.00'))
        self.assertEqual(movement.source_document, 'PO-TEST-001')

        self.assertEqual(get_item_current_stock(self.flour), Decimal('160.0000'))

    def test_purchase_stores_rate_in_movement(self):
        """Unit cost (rate) must be stored on the StockMovement for costing."""
        po = self._make_draft_po(rate=Decimal('45.00'))
        receive_purchase_order(po, user=self.user)
        m = StockMovement.objects.get(source_document='PO-TEST-001', movement_type=MovementType.PURCHASE)
        self.assertEqual(m.unit_cost, Decimal('45.00'))

    def test_po_status_changes_to_received(self):
        po = self._make_draft_po()
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        receive_purchase_order(po, user=self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertIsNotNone(po.received_date)

    def test_receive_twice_does_not_duplicate_stock(self):
        """Calling receive_purchase_order twice must raise ValueError, not duplicate movements."""
        po = self._make_draft_po()
        receive_purchase_order(po, user=self.user)

        with self.assertRaises(ValueError):
            receive_purchase_order(po, user=self.user)

        # Balance must still be exactly 160 (100 + 60), not 220
        self.assertEqual(get_item_current_stock(self.flour), Decimal('160.0000'))
        purchase_count = StockMovement.objects.filter(
            movement_type=MovementType.PURCHASE,
            source_document='PO-TEST-001'
        ).count()
        self.assertEqual(purchase_count, 1)

    def test_purchase_packaging_item_increases_stock(self):
        """A packaging item PO line also increases its ledger balance."""
        po = PurchaseOrder.objects.create(
            po_number='PO-PKG-001',
            supplier=self.supplier,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            po=po,
            packaging_item=self.pouch,
            quantity=Decimal('200.0000'),
            unit=self.piece,
            unit_price=Decimal('2.50'),
        )
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('0.0000'))
        receive_purchase_order(po, user=self.user)
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('200.0000'))

    def test_multi_line_po_records_all_movements(self):
        """A PO with multiple lines creates one StockMovement per line."""
        po = PurchaseOrder.objects.create(
            po_number='PO-MULTI-001',
            supplier=self.supplier,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            po=po, raw_material=self.flour,
            quantity=Decimal('30.0000'), unit=self.kg, unit_price=Decimal('43.00'),
        )
        PurchaseOrderLine.objects.create(
            po=po, packaging_item=self.pouch,
            quantity=Decimal('100.0000'), unit=self.piece, unit_price=Decimal('2.75'),
        )
        movements = receive_purchase_order(po, user=self.user)
        self.assertEqual(len(movements), 2)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('130.0000'))  # 100 + 30
        self.assertEqual(get_item_current_stock(self.pouch), Decimal('100.0000'))

    def test_po_line_total_uses_decimal(self):
        """Line total must be exact Decimal arithmetic, never float."""
        po = self._make_draft_po(qty=Decimal('60.0000'), rate=Decimal('45.00'))
        line = po.lines.first()
        self.assertIsInstance(line.line_total, Decimal)
        self.assertEqual(line.line_total, Decimal('2700.00'))

    def test_po_total_value_sums_lines(self):
        """PO total_value must sum all lines correctly."""
        po = PurchaseOrder.objects.create(
            po_number='PO-TOTAL-001',
            supplier=self.supplier,
            created_by=self.user,
        )
        PurchaseOrderLine.objects.create(
            po=po, raw_material=self.flour,
            quantity=Decimal('60.0000'), unit=self.kg, unit_price=Decimal('45.00'),
        )
        PurchaseOrderLine.objects.create(
            po=po, packaging_item=self.pouch,
            quantity=Decimal('200.0000'), unit=self.piece, unit_price=Decimal('2.50'),
        )
        # 60 × 45 = 2700, 200 × 2.5 = 500 → total = 3200
        self.assertEqual(po.total_value, Decimal('3200.00'))


class PurchaseScreenPermissionTests(TestCase):
    """Tests that the purchase screens enforce role-based access."""

    def setUp(self):
        self.password = 'Pass123!'
        self.admin = User.objects.create_user(username='adm', password=self.password, role=Role.ADMIN)
        self.production = User.objects.create_user(username='prod', password=self.password, role=Role.PRODUCTION)
        self.accountant = User.objects.create_user(username='acct', password=self.password, role=Role.ACCOUNTANT)
        self.owner = User.objects.create_user(username='ownr', password=self.password, role=Role.OWNER)
        self.salesman = User.objects.create_user(username='sale', password=self.password, role=Role.SALESMAN)

        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.supplier = Supplier.objects.create(
            name='Test Supplier', city='Trichy', state='Tamil Nadu', state_code='33',
        )
        self.flour = RawMaterial.objects.create(
            name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'),
        )
        self.po = PurchaseOrder.objects.create(
            po_number='PO-PERM-001',
            supplier=self.supplier,
            created_by=self.admin,
        )
        PurchaseOrderLine.objects.create(
            po=self.po, raw_material=self.flour,
            quantity=Decimal('10.0000'), unit=self.kg, unit_price=Decimal('42.00'),
        )

    def test_salesman_cannot_view_purchase_list(self):
        c = Client()
        c.login(username='sale', password=self.password)
        res = c.get(reverse('purchases:purchase_list'))
        self.assertEqual(res.status_code, 403)

    def test_salesman_cannot_view_purchase_detail(self):
        c = Client()
        c.login(username='sale', password=self.password)
        res = c.get(reverse('purchases:purchase_detail', kwargs={'pk': self.po.pk}))
        self.assertEqual(res.status_code, 403)

    def test_salesman_cannot_create_purchase(self):
        c = Client()
        c.login(username='sale', password=self.password)
        res = c.get(reverse('purchases:purchase_create'))
        self.assertEqual(res.status_code, 403)

    def test_accountant_can_view_list_but_not_create(self):
        c = Client()
        c.login(username='acct', password=self.password)
        self.assertEqual(c.get(reverse('purchases:purchase_list')).status_code, 200)
        self.assertEqual(c.get(reverse('purchases:purchase_create')).status_code, 403)

    def test_owner_can_view_list_but_not_create(self):
        c = Client()
        c.login(username='ownr', password=self.password)
        self.assertEqual(c.get(reverse('purchases:purchase_list')).status_code, 200)
        self.assertEqual(c.get(reverse('purchases:purchase_create')).status_code, 403)

    def test_admin_can_view_and_create(self):
        c = Client()
        c.login(username='adm', password=self.password)
        self.assertEqual(c.get(reverse('purchases:purchase_list')).status_code, 200)
        self.assertEqual(c.get(reverse('purchases:purchase_create')).status_code, 200)
        self.assertEqual(c.get(reverse('purchases:purchase_detail', kwargs={'pk': self.po.pk})).status_code, 200)

    def test_production_can_view_and_create(self):
        c = Client()
        c.login(username='prod', password=self.password)
        self.assertEqual(c.get(reverse('purchases:purchase_list')).status_code, 200)
        self.assertEqual(c.get(reverse('purchases:purchase_create')).status_code, 200)

    def test_receive_via_post_records_ledger_movement(self):
        """POSTing the receive URL triggers ledger recording and redirects."""
        c = Client()
        c.login(username='adm', password=self.password)
        res = c.post(reverse('purchases:purchase_receive', kwargs={'pk': self.po.pk}))
        self.assertRedirects(res, reverse('purchases:purchase_detail', kwargs={'pk': self.po.pk}))
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=MovementType.PURCHASE,
                source_document='PO-PERM-001'
            ).count(),
            1
        )

    def test_save_po_with_one_filled_line_and_empty_extra_rows(self):
        """
        Verify that a purchase order with 1 filled line and empty extra rows
        saves successfully, ignoring the empty rows and not blocking on validation errors.
        """
        c = Client()
        c.login(username='adm', password=self.password)

        post_data = {
            'po_number': 'PO-TEST-EXTRA-001',
            'supplier': str(self.supplier.id),
            'order_date': '2026-11-22',
            'received_date': '',
            'notes': 'Test order with empty extra rows',
            'lines-TOTAL_FORMS': '3',
            'lines-INITIAL_FORMS': '0',
            # Form 0: filled
            'lines-0-item_type': 'raw_material',
            'lines-0-raw_material': str(self.flour.id),
            'lines-0-packaging_item': '',
            'lines-0-quantity': '60.0000',
            'lines-0-unit': str(self.kg.id),
            'lines-0-unit_price': '45.00',
            # Form 1: empty extra row (item_type defaults to raw_material)
            'lines-1-item_type': 'raw_material',
            'lines-1-raw_material': '',
            'lines-1-packaging_item': '',
            'lines-1-quantity': '',
            'lines-1-unit': '',
            'lines-1-unit_price': '',
            # Form 2: empty extra row
            'lines-2-item_type': 'raw_material',
            'lines-2-raw_material': '',
            'lines-2-packaging_item': '',
            'lines-2-quantity': '',
            'lines-2-unit': '',
            'lines-2-unit_price': '',
        }

        res = c.post(reverse('purchases:purchase_create'), post_data)
        self.assertEqual(res.status_code, 302)  # Redirects to detail view on success

        po = PurchaseOrder.objects.get(po_number='PO-TEST-EXTRA-001')
        self.assertEqual(po.lines.count(), 1)
        line = po.lines.first()
        self.assertEqual(line.raw_material, self.flour)
        self.assertEqual(line.quantity, Decimal('60.0000'))
        self.assertEqual(line.unit_price, Decimal('45.00'))

    def test_partly_filled_extra_row_shows_validation_error(self):
        """
        Rows that are partly filled in must trigger validation errors.
        """
        c = Client()
        c.login(username='adm', password=self.password)

        post_data = {
            'po_number': 'PO-TEST-PARTIAL-001',
            'supplier': str(self.supplier.id),
            'order_date': '2026-11-22',
            'received_date': '',
            'notes': '',
            'lines-TOTAL_FORMS': '2',
            'lines-INITIAL_FORMS': '0',
            # Form 0: filled
            'lines-0-item_type': 'raw_material',
            'lines-0-raw_material': str(self.flour.id),
            'lines-0-packaging_item': '',
            'lines-0-quantity': '60.0000',
            'lines-0-unit': str(self.kg.id),
            'lines-0-unit_price': '45.00',
            # Form 1: partial (quantity entered, but item missing)
            'lines-1-item_type': 'raw_material',
            'lines-1-raw_material': '',
            'lines-1-packaging_item': '',
            'lines-1-quantity': '20.0000',
            'lines-1-unit': str(self.kg.id),
            'lines-1-unit_price': '40.00',
        }

        res = c.post(reverse('purchases:purchase_create'), post_data)
        # Must not redirect, re-renders form with 200 and errors
        self.assertEqual(res.status_code, 200)
        self.assertFalse(PurchaseOrder.objects.filter(po_number='PO-TEST-PARTIAL-001').exists())


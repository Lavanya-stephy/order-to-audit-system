from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from accounts.models import Role
from masters.models import (
    Unit,
    UnitCategory,
    RawMaterial,
    PackagingItem,
    Product,
)
from inventory.models import StockMovement, MovementType
from inventory.services import (
    record_movement,
    get_item_current_stock,
    get_stock_summary,
    get_item_ledger,
)

User = get_user_model()


class StockLedgerDerivationTests(TestCase):
    """
    Validates the core inventory rule:
    Balances are strictly derived from movements, never overwritten.
    Formula: Opening Balance + Receipts (Inward) - Issues (Outward) = Closing Balance.
    """
    def setUp(self):
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        self.flour = RawMaterial.objects.create(
            name='Flour',
            code='RM-FLOUR',
            unit=self.kg,
            standard_cost=Decimal('42.00'),
            reorder_level=Decimal('20.000')
        )
        self.pouch = PackagingItem.objects.create(
            name='200 g pouch',
            code='PM-POUCH-200G',
            unit=self.piece,
            standard_cost=Decimal('2.50'),
            capacity_packets=1,
            reorder_level=Decimal('100.00')
        )
        self.murukku = Product.objects.create(
            name='Murukku 200 g',
            code='FG-MURUKKU-200G',
            pack_size=Decimal('200.00'),
            pack_size_unit=self.kg,
            unit=self.packet,
            selling_price=Decimal('50.00'),
            gst_rate=Decimal('5.00'),
        )

        self.user = User.objects.create_user(username='inv_supervisor', password='password123', role=Role.PRODUCTION)

    def test_opening_plus_receipts_minus_issues_equals_closing_raw_material(self):
        """
        Benchmark Section 5 Flour verification:
        Opening: 100 kg
        Receipt (Purchase): +60 kg
        Issue (Production Run): -40 kg
        Expected Closing: 120 kg (100 + 60 - 40)
        """
        # 1. Opening
        record_movement(
            item=self.flour,
            quantity=Decimal('100.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-2026',
            user=self.user,
        )
        self.assertEqual(get_item_current_stock(self.flour), Decimal('100.0000'))

        # 2. Receipt (+60 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('60.0000'),
            movement_type=MovementType.PURCHASE,
            source_document='PO-001',
            unit_cost=Decimal('45.00'),
            user=self.user,
        )
        self.assertEqual(get_item_current_stock(self.flour), Decimal('160.0000'))

        # 3. Issue (-40 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('-40.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-001',
            user=self.user,
        )

        # 4. Closing balance check
        closing = get_item_current_stock(self.flour)
        self.assertEqual(closing, Decimal('120.0000'))

        # Verify summary breakdown
        summary = get_stock_summary()
        flour_row = next(r for r in summary if r['code'] == 'RM-FLOUR')
        # Opening stock (100) is counted in the Opening column, not in Inward Receipts:
        self.assertEqual(flour_row['opening'], Decimal('100.0000'))
        self.assertEqual(flour_row['receipts'], Decimal('60.0000'))  # Only purchase (60 kg)
        self.assertEqual(flour_row['issues'], Decimal('40.0000'))    # Only production issue (40 kg)
        self.assertEqual(flour_row['closing'], Decimal('120.0000'))

        # Verify formula: Opening + Inward Receipts - Outward Issues = Closing
        self.assertEqual(flour_row['opening'] + flour_row['receipts'] - flour_row['issues'], flour_row['closing'])

    def test_packaging_pouch_ledger_derivation(self):
        """
        Benchmark Section 5 Pouches verification:
        Opening: 500 pcs
        Issue (used for good packets): -188 pcs
        Issue (damaged scrap): -6 pcs
        Expected Closing: 306 pcs (500 - 188 - 6)
        """
        record_movement(
            item=self.pouch,
            quantity=Decimal('500.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-2026',
            user=self.user,
        )
        record_movement(
            item=self.pouch,
            quantity=Decimal('-188.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-001',
            notes='Pouched 188 good packets',
            user=self.user,
        )
        record_movement(
            item=self.pouch,
            quantity=Decimal('-6.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-001',
            notes='Damaged pouches scrap',
            user=self.user,
        )

        closing = get_item_current_stock(self.pouch)
        self.assertEqual(closing, Decimal('306.0000'))

        ledger = get_item_ledger(self.pouch)
        self.assertEqual(ledger['total_inward'], Decimal('500.0000'))
        self.assertEqual(ledger['total_outward'], Decimal('194.0000'))  # 188 + 6
        self.assertEqual(ledger['closing_balance'], Decimal('306.0000'))
        self.assertEqual(ledger['opening_balance'] + ledger['total_inward'] - ledger['total_outward'], ledger['closing_balance'])

    def test_finished_goods_ledger_production_and_dispatch(self):
        """
        Benchmark Section 5 Murukku 200 g Finished Goods verification:
        Opening: 50 packets
        Production Output: +188 packets -> Balance: 238 packets
        Dispatch (Retailer A): -150 packets -> Balance: 88 packets
        """
        # Opening: 50 pkts
        record_movement(
            item=self.murukku,
            quantity=Decimal('50.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-2026',
            user=self.user,
        )
        self.assertEqual(get_item_current_stock(self.murukku), Decimal('50.0000'))

        # Production Output: +188 pkts
        record_movement(
            item=self.murukku,
            quantity=Decimal('188.0000'),
            movement_type=MovementType.PRODUCTION_OUTPUT,
            source_document='RUN-001',
            batch_number='BATCH-2026-01',
            user=self.user,
        )
        self.assertEqual(get_item_current_stock(self.murukku), Decimal('238.0000'))

        # Dispatch: -150 pkts
        record_movement(
            item=self.murukku,
            quantity=Decimal('-150.0000'),
            movement_type=MovementType.DISPATCH,
            source_document='INV-2026-001',
            notes='Dispatched to Retailer A',
            user=self.user,
        )
        self.assertEqual(get_item_current_stock(self.murukku), Decimal('88.0000'))

        # Verify running balance in chronological ledger
        ledger = get_item_ledger(self.murukku)
        self.assertEqual(len(ledger['entries']), 3)
        self.assertEqual(ledger['entries'][0]['running_balance'], Decimal('50.0000'))
        self.assertEqual(ledger['entries'][1]['running_balance'], Decimal('238.0000'))
        self.assertEqual(ledger['entries'][2]['running_balance'], Decimal('88.0000'))
        self.assertEqual(ledger['closing_balance'], Decimal('88.0000'))

    def test_ledger_date_range_filtering(self):
        """Verify opening balance computation when date filters are applied."""
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)

        # 1. Opening movement 2 days ago
        record_movement(
            item=self.flour,
            quantity=Decimal('100.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-2026',
            created_at=two_days_ago,
        )
        # 2. Movement yesterday
        record_movement(
            item=self.flour,
            quantity=Decimal('50.0000'),
            movement_type=MovementType.PURCHASE,
            source_document='PO-YESTERDAY',
            created_at=yesterday,
        )
        # 3. Movement today
        record_movement(
            item=self.flour,
            quantity=Decimal('-30.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-TODAY',
            created_at=now,
        )

        # Filter strictly for today:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        ledger = get_item_ledger(self.flour, start_date=today_start)

        # Movements before today = 100 + 50 = 150 kg opening
        self.assertEqual(ledger['opening_balance'], Decimal('150.0000'))
        # Today's outward issue = 30 kg
        self.assertEqual(ledger['total_outward'], Decimal('30.0000'))
        # Closing = 150 - 30 = 120 kg
        self.assertEqual(ledger['closing_balance'], Decimal('120.0000'))
        self.assertEqual(ledger['opening_balance'] + ledger['total_inward'] - ledger['total_outward'], ledger['closing_balance'])

    def test_stock_summary_opening_counts_in_opening_column_not_inward(self):
        """
        Verify:
        - Opening stock counts in Opening column, NOT in Inward Receipts.
        - After seed (flour 100 opening): Opening=100, Inward=0, Outward=0, Closing=100.
        - Inward Receipts only includes purchases, production output, returns, and positive adjustments.
        - Outward Issues only includes production issues, dispatches, and negative adjustments.
        - Closing = Opening + Inward - Outward.
        """
        # 1. Opening only: 100 kg
        record_movement(
            item=self.flour,
            quantity=Decimal('100.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-TEST',
            user=self.user,
        )

        summary = get_stock_summary()
        flour_row = next(r for r in summary if r['code'] == 'RM-FLOUR')
        self.assertEqual(flour_row['opening'], Decimal('100.0000'), "Opening stock must be counted in Opening column")
        self.assertEqual(flour_row['receipts'], Decimal('0.0000'), "Opening stock must NOT be in Inward Receipts")
        self.assertEqual(flour_row['issues'], Decimal('0.0000'), "Outward Issues must be 0")
        self.assertEqual(flour_row['closing'], Decimal('100.0000'), "Closing must equal Opening")
        self.assertEqual(flour_row['opening'] + flour_row['receipts'] - flour_row['issues'], flour_row['closing'])

        # 2. Add purchase (+60 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('60.0000'),
            movement_type=MovementType.PURCHASE,
            source_document='PO-001',
            user=self.user,
        )
        # Add return (+5 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('5.0000'),
            movement_type=MovementType.RETURN,
            source_document='RET-001',
            user=self.user,
        )
        # Add positive adjustment (+10 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('10.0000'),
            movement_type=MovementType.ADJUSTMENT,
            source_document='ADJ-PLUS',
            user=self.user,
        )
        # Add production issue (-40 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('-40.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-001',
            user=self.user,
        )
        # Add negative adjustment (-5 kg)
        record_movement(
            item=self.flour,
            quantity=Decimal('-5.0000'),
            movement_type=MovementType.ADJUSTMENT,
            source_document='ADJ-MINUS',
            user=self.user,
        )

        summary = get_stock_summary()
        flour_row = next(r for r in summary if r['code'] == 'RM-FLOUR')

        # Opening: 100
        self.assertEqual(flour_row['opening'], Decimal('100.0000'))
        # Inward receipts: 60 (purchase) + 5 (return) + 10 (positive adjustment) = 75
        self.assertEqual(flour_row['receipts'], Decimal('75.0000'))
        # Outward issues: 40 (issue) + 5 (negative adjustment) = 45
        self.assertEqual(flour_row['issues'], Decimal('45.0000'))
        # Closing: 100 + 75 - 45 = 130
        self.assertEqual(flour_row['closing'], Decimal('130.0000'))
        self.assertEqual(flour_row['opening'] + flour_row['receipts'] - flour_row['issues'], flour_row['closing'])
        self.assertEqual(flour_row['closing'], get_item_current_stock(self.flour))

    def test_stock_summary_date_range_opening_balance(self):
        """
        If a date range is used, Opening means the balance of all movements before start date.
        Closing = Opening + Inward - Outward, and closing balance matches current stock.
        """
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)

        # Day -2: Opening 100 kg
        record_movement(
            item=self.flour,
            quantity=Decimal('100.0000'),
            movement_type=MovementType.OPENING,
            source_document='OPENING-OLD',
            created_at=two_days_ago,
        )
        # Day -1: Purchase 50 kg
        record_movement(
            item=self.flour,
            quantity=Decimal('50.0000'),
            movement_type=MovementType.PURCHASE,
            source_document='PO-OLD',
            created_at=yesterday,
        )
        # Today: Production Issue -30 kg
        record_movement(
            item=self.flour,
            quantity=Decimal('-30.0000'),
            movement_type=MovementType.PRODUCTION_ISSUE,
            source_document='RUN-TODAY',
            created_at=now,
        )

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        summary = get_stock_summary(start_date=today_start)
        flour_row = next(r for r in summary if r['code'] == 'RM-FLOUR')

        # Balance before start_date = 100 (opening) + 50 (purchase) = 150 kg
        self.assertEqual(flour_row['opening'], Decimal('150.0000'))
        self.assertEqual(flour_row['receipts'], Decimal('0.0000'))
        self.assertEqual(flour_row['issues'], Decimal('30.0000'))
        self.assertEqual(flour_row['closing'], Decimal('120.0000'))
        self.assertEqual(flour_row['opening'] + flour_row['receipts'] - flour_row['issues'], flour_row['closing'])

    def test_stock_movement_validation_rules(self):
        """Validate signed quantity not zero, and exactly one item linked."""
        # Zero quantity not allowed
        with self.assertRaises(ValidationError):
            m = StockMovement(
                raw_material=self.flour,
                quantity=Decimal('0.0000'),
                unit=self.kg,
                movement_type=MovementType.PURCHASE,
                source_document='DOC-1'
            )
            m.full_clean()

        # No item specified
        with self.assertRaises(ValidationError):
            m = StockMovement(
                quantity=Decimal('10.0000'),
                unit=self.kg,
                movement_type=MovementType.PURCHASE,
                source_document='DOC-2'
            )
            m.full_clean()

        # Multiple items specified
        with self.assertRaises(ValidationError):
            m = StockMovement(
                raw_material=self.flour,
                packaging_item=self.pouch,
                quantity=Decimal('10.0000'),
                unit=self.kg,
                movement_type=MovementType.PURCHASE,
                source_document='DOC-3'
            )
            m.full_clean()


class StockScreensAndPermissionTests(TestCase):
    def setUp(self):
        self.password = 'Pass123!@#'
        self.admin = User.objects.create_user(username='admin_inv', password=self.password, role=Role.ADMIN)
        self.production = User.objects.create_user(username='prod_inv', password=self.password, role=Role.PRODUCTION)
        self.accountant = User.objects.create_user(username='acct_inv', password=self.password, role=Role.ACCOUNTANT)
        self.owner = User.objects.create_user(username='owner_inv', password=self.password, role=Role.OWNER)
        self.salesman = User.objects.create_user(username='sales_inv', password=self.password, role=Role.SALESMAN)

        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.flour = RawMaterial.objects.create(name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'))

    def test_stock_summary_and_ledger_access_permissions_for_all_roles(self):
        """
        Verify:
        - production, admin, accountant, owner can view stock summary and ledger (200 OK).
        - salesman is denied access (403 Forbidden), even when directly typing the URL.
        - unauthenticated visitor is redirected to login (302).
        """
        client = Client()

        # 1. Unauthenticated -> 302 redirect to login
        res_anon_summary = client.get(reverse('inventory:stock_summary'))
        self.assertEqual(res_anon_summary.status_code, 302)
        self.assertIn('/login/', res_anon_summary.url)

        res_anon_ledger = client.get(reverse('inventory:stock_ledger'))
        self.assertEqual(res_anon_ledger.status_code, 302)
        self.assertIn('/login/', res_anon_ledger.url)

        # 2. Salesman -> 403 Forbidden on both summary and ledger
        client.login(username=self.salesman.username, password=self.password)
        res_sales_summary = client.get(reverse('inventory:stock_summary'))
        self.assertEqual(res_sales_summary.status_code, 403)
        self.assertContains(res_sales_summary, "Access Denied", status_code=403)

        res_sales_ledger = client.get(reverse('inventory:stock_ledger'))
        self.assertEqual(res_sales_ledger.status_code, 403)
        self.assertContains(res_sales_ledger, "Access Denied", status_code=403)
        client.logout()

        # 3. Allowed roles: production, admin, accountant, owner -> 200 OK
        allowed_users = [
            (self.production, "production"),
            (self.admin, "admin"),
            (self.accountant, "accountant"),
            (self.owner, "owner"),
        ]

        for user_obj, role_name in allowed_users:
            client.login(username=user_obj.username, password=self.password)

            # Stock Summary access
            res_sum = client.get(reverse('inventory:stock_summary'))
            self.assertEqual(
                res_sum.status_code, 200,
                f"Role {role_name} should be able to view stock summary."
            )
            self.assertContains(res_sum, "Inventory Stock Summary")

            # Stock Ledger access
            res_led = client.get(reverse('inventory:stock_ledger'))
            self.assertEqual(
                res_led.status_code, 200,
                f"Role {role_name} should be able to view stock ledger."
            )
            self.assertContains(res_led, "Itemized Stock Ledger")

            client.logout()

    def test_stock_adjustment_permissions(self):
        """Admin and Production can record adjustments; Accountant (read-only) and Owner/Salesman access rules."""
        client = Client()

        # Accountant denied (403)
        client.login(username=self.accountant.username, password=self.password)
        res = client.get(reverse('inventory:stock_adjust'))
        self.assertEqual(res.status_code, 403)
        client.logout()

        # Salesman denied (403)
        client.login(username=self.salesman.username, password=self.password)
        res = client.get(reverse('inventory:stock_adjust'))
        self.assertEqual(res.status_code, 403)
        client.logout()

        # Production supervisor allowed (200)
        client.login(username=self.production.username, password=self.password)
        res = client.get(reverse('inventory:stock_adjust'))
        self.assertEqual(res.status_code, 200)
        client.logout()

    def test_record_adjustment_post(self):
        """Authorized user can post an adjustment to update ledger."""
        client = Client()
        client.login(username=self.admin.username, password=self.password)

        data = {
            'item_type': 'raw_material',
            'raw_material': self.flour.id,
            'movement_type': MovementType.ADJUSTMENT,
            'quantity': '25.0000',
            'source_document': 'AUDIT-ADJ-TEST',
            'notes': 'Physical audit surplus',
        }
        res = client.post(reverse('inventory:stock_adjust'), data)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(get_item_current_stock(self.flour), Decimal('25.0000'))

    def test_navigation_menu_links_for_all_roles(self):
        """
        Verify navigation links for each role:
        - production, admin, accountant, and owner have links to Stock Summary and Stock Ledger.
        - salesman role does NOT see links to Stock Summary or Stock Ledger anywhere in navigation.
        """
        client = Client()

        summary_url = reverse('inventory:stock_summary')
        ledger_url = reverse('inventory:stock_ledger')

        role_dashboards = [
            (self.admin, reverse('admin_dashboard'), 'Admin'),
            (self.production, reverse('production_dashboard'), 'Production'),
            (self.accountant, reverse('accountant_dashboard'), 'Accountant'),
            (self.owner, reverse('owner_dashboard'), 'Owner'),
        ]

        for user_obj, dashboard_url, role_label in role_dashboards:
            client.login(username=user_obj.username, password=self.password)
            res = client.get(dashboard_url)
            self.assertEqual(res.status_code, 200, f"Dashboard for {role_label} should return 200")
            # Must contain links to both summary and ledger
            self.assertContains(res, summary_url, msg_prefix=f"{role_label} must have link to Stock Summary")
            self.assertContains(res, ledger_url, msg_prefix=f"{role_label} must have link to Stock Ledger")
            client.logout()

        # Salesman role must NOT see links to inventory in navigation or on dashboard
        client.login(username=self.salesman.username, password=self.password)
        res_sales = client.get(reverse('salesman_dashboard'))
        self.assertEqual(res_sales.status_code, 200)
        self.assertNotContains(res_sales, summary_url, msg_prefix="Salesman must NOT see Stock Summary link")
        self.assertNotContains(res_sales, ledger_url, msg_prefix="Salesman must NOT see Stock Ledger link")
        client.logout()

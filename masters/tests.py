from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

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

User = get_user_model()


class UnitConversionTests(TestCase):
    def setUp(self):
        # Create standard test units
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT, to_base_factor=Decimal('1.000000'))
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT, to_base_factor=Decimal('0.001000'))
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME, to_base_factor=Decimal('1.000000'))
        self.ml = Unit.objects.create(name='Millilitre', symbol='ml', category=UnitCategory.VOLUME, to_base_factor=Decimal('0.001000'))
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))
        self.carton = Unit.objects.create(name='Carton', symbol='carton', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT, to_base_factor=Decimal('1.000000'))

        # Create explicit conversion: 1 carton = 20 packets
        self.carton_to_packet = UnitConversion.objects.create(
            from_unit=self.carton,
            to_unit=self.packet,
            factor=Decimal('20.0000')
        )

    def test_weight_conversions_kg_and_g(self):
        """Test standard weight conversions between kg and g."""
        # 1 kg = 1000 g
        self.assertEqual(Unit.convert(Decimal('1'), self.kg, self.g), Decimal('1000'))
        # 40 kg (benchmark batch) = 40,000 g
        self.assertEqual(Unit.convert(Decimal('40'), self.kg, self.g), Decimal('40000'))
        # 1200 g (spices) = 1.2 kg
        self.assertEqual(Unit.convert(Decimal('1200'), self.g, self.kg), Decimal('1.2'))
        # 200 g (murukku pack) = 0.2 kg
        self.assertEqual(Unit.convert(Decimal('200'), self.g, self.kg), Decimal('0.2'))

    def test_volume_conversions_litre_and_ml(self):
        """Test volume conversions between litre and ml."""
        # 1 L = 1000 ml
        self.assertEqual(Unit.convert(Decimal('1'), self.litre, self.ml), Decimal('1000'))
        # 10.5 L (benchmark oil used) = 10500 ml
        self.assertEqual(Unit.convert(Decimal('10.5'), self.litre, self.ml), Decimal('10500'))
        # 500 ml = 0.5 L
        self.assertEqual(Unit.convert(Decimal('500'), self.ml, self.litre), Decimal('0.5'))

    def test_carton_and_packet_explicit_conversions(self):
        """Test discrete package unit conversions using explicit conversion rules."""
        # 1 carton = 20 packets
        self.assertEqual(Unit.convert(Decimal('1'), self.carton, self.packet), Decimal('20'))
        # 9 cartons (benchmark scenario) = 180 packets
        self.assertEqual(Unit.convert(Decimal('9'), self.carton, self.packet), Decimal('180'))
        # 10 cartons (standard batch output) = 200 packets
        self.assertEqual(Unit.convert(Decimal('10'), self.carton, self.packet), Decimal('200'))

        # Reverse conversion: packets to cartons
        # 200 packets = 10 cartons
        self.assertEqual(Unit.convert(Decimal('200'), self.packet, self.carton), Decimal('10'))
        # 188 packets = 9.4 cartons
        self.assertEqual(Unit.convert(Decimal('188'), self.packet, self.carton), Decimal('9.4'))

    def test_same_unit_identity_conversion(self):
        """Converting a unit to itself should return the exact original quantity."""
        qty = Decimal('42.75')
        self.assertEqual(Unit.convert(qty, self.kg, self.kg), qty)
        self.assertEqual(Unit.convert(qty, self.packet, self.packet), qty)

    def test_convenience_instance_method(self):
        """Test unit.convert_to(quantity, target_unit)."""
        result = self.kg.convert_to(Decimal('2.5'), self.g)
        self.assertEqual(result, Decimal('2500'))

    def test_incompatible_unit_conversion_raises_error(self):
        """Attempting to convert between incompatible categories (e.g. kg to litre) must raise ValueError."""
        with self.assertRaises(ValueError):
            Unit.convert(Decimal('10'), self.kg, self.litre)

        with self.assertRaises(ValueError):
            Unit.convert(Decimal('5'), self.packet, self.kg)


class MasterModelsAndLogicTests(TestCase):
    def setUp(self):
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        self.product = Product.objects.create(
            name='Murukku 200 g',
            code='FG-MURUKKU-200G',
            hsn_code='19059040',
            pack_size=Decimal('200.00'),
            pack_size_unit=self.g,
            unit=self.packet,
            selling_price=Decimal('50.00'),
            gst_rate=Decimal('5.00'),
            carton_pack_qty=20,
        )

        self.retailer_tn = Customer.objects.create(
            name='Retailer A',
            customer_type=CustomerType.RETAILER,
            state='Tamil Nadu',
            state_code='33',
            gstin='33AABCT1234A1Z5',
            credit_limit=Decimal('20000.00'),
        )

        self.distributor_ka = Customer.objects.create(
            name='Distributor B',
            customer_type=CustomerType.DISTRIBUTOR,
            state='Karnataka',
            state_code='29',
            gstin='29AABCD5678B1Z2',
            credit_limit=Decimal('50000.00'),
        )

    def test_product_gst_and_pricing_properties(self):
        """Verify product tax calculations and GST rates using Decimal."""
        # 5% GST split: 2.5% CGST + 2.5% SGST
        self.assertEqual(self.product.cgst_rate, Decimal('2.50'))
        self.assertEqual(self.product.sgst_rate, Decimal('2.50'))
        self.assertEqual(self.product.igst_rate, Decimal('5.00'))

        # Selling price: ₹50.00 + (5% of ₹50 = ₹2.50) = ₹52.50
        self.assertEqual(self.product.selling_price_with_tax, Decimal('52.50'))

    def test_customer_place_of_supply_logic(self):
        """Intra-state customer (TN) must NOT be interstate; Inter-state (KA) must be interstate."""
        # Factory is in Tamil Nadu (state_code '33')
        self.assertFalse(self.retailer_tn.is_interstate('33'))
        self.assertTrue(self.distributor_ka.is_interstate('33'))


class MasterCRUDAndPermissionTests(TestCase):
    def setUp(self):
        self.password = 'Pass123!@#'
        self.admin = User.objects.create_user(username='admin_test', password=self.password, role=Role.ADMIN)
        self.production = User.objects.create_user(username='prod_test', password=self.password, role=Role.PRODUCTION)
        self.accountant = User.objects.create_user(username='acct_test', password=self.password, role=Role.ACCOUNTANT)
        self.salesman = User.objects.create_user(username='sales_test', password=self.password, role=Role.SALESMAN)

        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)

    def test_masters_hub_access_permissions(self):
        """Admin, Production, and Accountant can view Master Hub; Salesman is denied."""
        client = Client()

        # Salesman denied (403)
        client.login(username=self.salesman.username, password=self.password)
        res = client.get(reverse('masters:hub'))
        self.assertEqual(res.status_code, 403)

        # Admin allowed (200)
        client.login(username=self.admin.username, password=self.password)
        res = client.get(reverse('masters:hub'))
        self.assertEqual(res.status_code, 200)

        # Accountant allowed (read-only) (200)
        client.login(username=self.accountant.username, password=self.password)
        res = client.get(reverse('masters:hub'))
        self.assertEqual(res.status_code, 200)

    def test_accountant_read_only_restriction_on_writes(self):
        """Accountant cannot access Add/Edit forms (returns 403)."""
        client = Client()
        client.login(username=self.accountant.username, password=self.password)

        res = client.get(reverse('masters:rawmaterial_add'))
        self.assertEqual(res.status_code, 403)

        res = client.get(reverse('masters:product_add'))
        self.assertEqual(res.status_code, 403)

    def test_admin_can_create_raw_material(self):
        """Factory Admin can create a raw material via CRUD form."""
        client = Client()
        client.login(username=self.admin.username, password=self.password)

        data = {
            'name': 'Chilli Powder',
            'code': 'RM-CHILLI',
            'unit': self.kg.id,
            'standard_cost': '180.00',
            'reorder_level': '5.000',
            'description': 'Pure red chilli powder',
            'is_active': True,
        }
        res = client.post(reverse('masters:rawmaterial_add'), data)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(RawMaterial.objects.filter(code='RM-CHILLI').exists())
        rm = RawMaterial.objects.get(code='RM-CHILLI')
        self.assertEqual(rm.standard_cost, Decimal('180.00'))


class BenchmarkBOMSection5Tests(TestCase):
    """
    Tests loading and validating the exact Section 5 benchmark BOM for Murukku 200 g.
    Master Data Specification:
    - 1 batch = 200 packets expected yield
    - Flour: 40 kg @ ₹42/kg = ₹1,680.00
    - Cooking oil: 10 L @ ₹140/L = ₹1,400.00
    - Salt and spice mix: 1.2 kg @ ₹200/kg = ₹240.00
    - 200 g pouch: 200 pcs @ ₹2.50 = ₹500.00
    - Carton (holds 20 pkts): 10 pcs @ ₹15 = ₹150.00
    - Expected Batch Cost: ₹3,970.00
    - Expected Cost per Packet: ₹19.85
    """
    def setUp(self):
        # Units
        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT, to_base_factor=Decimal('0.001'))
        self.litre = Unit.objects.create(name='Litre', symbol='litre', category=UnitCategory.VOLUME)
        self.piece = Unit.objects.create(name='Piece', symbol='piece', category=UnitCategory.COUNT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)

        # Raw materials
        self.flour = RawMaterial.objects.create(name='Flour', code='RM-FLOUR', unit=self.kg, standard_cost=Decimal('42.00'))
        self.oil = RawMaterial.objects.create(name='Cooking oil', code='RM-OIL', unit=self.litre, standard_cost=Decimal('140.00'))
        self.spice = RawMaterial.objects.create(name='Salt and spice mix', code='RM-SPICE', unit=self.kg, standard_cost=Decimal('200.00'))

        # Packaging items
        self.pouch = PackagingItem.objects.create(name='200 g pouch', code='PM-POUCH-200G', unit=self.piece, standard_cost=Decimal('2.50'), capacity_packets=1)
        self.carton = PackagingItem.objects.create(name='Carton (holds 20 packets)', code='PM-CARTON-20', unit=self.piece, standard_cost=Decimal('15.00'), capacity_packets=20)

        # Finished Product
        self.product = Product.objects.create(
            name='Murukku 200 g',
            code='FG-MURUKKU-200G',
            hsn_code='19059040',
            pack_size=Decimal('200.00'),
            pack_size_unit=self.g,
            unit=self.packet,
            selling_price=Decimal('50.00'),
            gst_rate=Decimal('5.00'),
            carton_pack_qty=20,
        )

        # Build Section 5 Murukku 200 g BOM
        self.bom = BillOfMaterial.objects.create(
            product=self.product,
            name='Murukku 200 g Standard Recipe',
            batch_size=Decimal('1.00'),
            expected_yield_packets=200,
            notes='Section 5 Benchmark Recipe: 1 batch = 200 packets',
        )

        # Add 5 benchmark lines
        self.line_flour = BOMLine.objects.create(bom=self.bom, raw_material=self.flour, quantity=Decimal('40.0000'), unit=self.kg)
        self.line_oil = BOMLine.objects.create(bom=self.bom, raw_material=self.oil, quantity=Decimal('10.0000'), unit=self.litre)
        self.line_spice = BOMLine.objects.create(bom=self.bom, raw_material=self.spice, quantity=Decimal('1.2000'), unit=self.kg)
        self.line_pouch = BOMLine.objects.create(bom=self.bom, packaging_item=self.pouch, quantity=Decimal('200.0000'), unit=self.piece)
        self.line_carton = BOMLine.objects.create(bom=self.bom, packaging_item=self.carton, quantity=Decimal('10.0000'), unit=self.piece)

    def test_benchmark_bom_structure(self):
        """Verify the Murukku 200 g BOM line counts and expected yield."""
        self.assertEqual(self.bom.expected_yield_packets, 200)
        self.assertEqual(self.bom.lines.count(), 5)
        self.assertEqual(self.bom.raw_material_lines.count(), 3)
        self.assertEqual(self.bom.packaging_lines.count(), 2)

    def test_benchmark_line_quantities_and_costs(self):
        """Verify each benchmark line item quantity, unit, and computed line cost."""
        # Flour: 40 kg @ ₹42 = ₹1680.00
        self.assertEqual(self.line_flour.quantity, Decimal('40.0000'))
        self.assertEqual(self.line_flour.unit, self.kg)
        self.assertEqual(self.line_flour.line_cost, Decimal('1680.00'))

        # Cooking oil: 10 L @ ₹140 = ₹1400.00
        self.assertEqual(self.line_oil.quantity, Decimal('10.0000'))
        self.assertEqual(self.line_oil.unit, self.litre)
        self.assertEqual(self.line_oil.line_cost, Decimal('1400.00'))

        # Spice mix: 1.2 kg @ ₹200 = ₹240.00
        self.assertEqual(self.line_spice.quantity, Decimal('1.2000'))
        self.assertEqual(self.line_spice.unit, self.kg)
        self.assertEqual(self.line_spice.line_cost, Decimal('240.00'))

        # 200 g pouch: 200 pcs @ ₹2.50 = ₹500.00
        self.assertEqual(self.line_pouch.quantity, Decimal('200.0000'))
        self.assertEqual(self.line_pouch.unit, self.piece)
        self.assertEqual(self.line_pouch.line_cost, Decimal('500.00'))

        # Carton: 10 pcs @ ₹15 = ₹150.00
        self.assertEqual(self.line_carton.quantity, Decimal('10.0000'))
        self.assertEqual(self.line_carton.unit, self.piece)
        self.assertEqual(self.line_carton.line_cost, Decimal('150.00'))

    def test_benchmark_batch_cost_and_cost_per_packet(self):
        """Verify total batch cost and standard cost per packet calculation."""
        # Total Raw Materials: 1680 + 1400 + 240 = ₹3,320.00
        self.assertEqual(self.bom.total_raw_material_cost, Decimal('3320.00'))

        # Total Packaging: 500 + 150 = ₹650.00
        self.assertEqual(self.bom.total_packaging_cost, Decimal('650.00'))

        # Total Batch Cost: 3320 + 650 = ₹3,970.00
        self.assertEqual(self.bom.total_standard_cost, Decimal('3970.00'))

        # Cost per Packet (for 200 pkts): 3970 / 200 = ₹19.85
        self.assertEqual(self.bom.standard_cost_per_packet, Decimal('19.85'))

    def test_bom_line_validation_rules(self):
        """A line cannot specify both or neither item type, and quantity must be positive."""
        # Line with neither
        line_empty = BOMLine(bom=self.bom, quantity=Decimal('5'), unit=self.kg)
        with self.assertRaises(ValidationError):
            line_empty.clean()

        # Line with both
        line_both = BOMLine(bom=self.bom, raw_material=self.flour, packaging_item=self.pouch, quantity=Decimal('5'), unit=self.kg)
        with self.assertRaises(ValidationError):
            line_both.clean()

        # Line with zero or negative quantity
        line_zero = BOMLine(bom=self.bom, raw_material=self.flour, quantity=Decimal('0'), unit=self.kg)
        with self.assertRaises(ValidationError):
            line_zero.clean()


class BOMScreenTests(TestCase):
    def setUp(self):
        self.password = 'Pass123!@#'
        self.admin = User.objects.create_user(username='admin_bom', password=self.password, role=Role.ADMIN)
        self.accountant = User.objects.create_user(username='acct_bom', password=self.password, role=Role.ACCOUNTANT)
        self.salesman = User.objects.create_user(username='sales_bom', password=self.password, role=Role.SALESMAN)

        self.kg = Unit.objects.create(name='Kilogram', symbol='kg', category=UnitCategory.WEIGHT)
        self.packet = Unit.objects.create(name='Packet', symbol='packet', category=UnitCategory.COUNT)
        self.g = Unit.objects.create(name='Gram', symbol='g', category=UnitCategory.WEIGHT)

        self.product = Product.objects.create(
            name='Mixture 250 g',
            code='FG-MIXTURE-250G',
            hsn_code='19059040',
            pack_size=Decimal('250.00'),
            pack_size_unit=self.g,
            unit=self.packet,
            selling_price=Decimal('60.00'),
            gst_rate=Decimal('5.00'),
        )

        self.bom = BillOfMaterial.objects.create(
            product=self.product,
            expected_yield_packets=100,
        )

    def test_bom_screens_access_permissions(self):
        """Admin can view and access create/edit BOM; Salesman is denied; Accountant is read-only."""
        client = Client()

        # Salesman denied
        client.login(username=self.salesman.username, password=self.password)
        res = client.get(reverse('masters:bom_list'))
        self.assertEqual(res.status_code, 403)

        # Admin allowed to view list and detail
        client.login(username=self.admin.username, password=self.password)
        res = client.get(reverse('masters:bom_list'))
        self.assertEqual(res.status_code, 200)

        res = client.get(reverse('masters:bom_detail', kwargs={'pk': self.bom.pk}))
        self.assertEqual(res.status_code, 200)

        # Accountant can view list and detail (read-only)
        client.login(username=self.accountant.username, password=self.password)
        res = client.get(reverse('masters:bom_list'))
        self.assertEqual(res.status_code, 200)

        # Accountant denied on edit
        res = client.get(reverse('masters:bom_edit', kwargs={'pk': self.bom.pk}))
        self.assertEqual(res.status_code, 403)


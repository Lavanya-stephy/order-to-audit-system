from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

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
from inventory.models import StockMovement, MovementType
from inventory.services import record_movement, get_item_current_stock

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds all master data and opening stock from PROBLEM.md section 5 (Benchmark scenario).'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("==================================================")
        self.stdout.write("🌱 Seeding Benchmark Scenario Data (Section 5)...")
        self.stdout.write("==================================================")

        # ---------------------------------------------------------------------
        # 0. Factory / Seller Configuration Information
        # ---------------------------------------------------------------------
        self.stdout.write("🏭 Seller Configuration (Demo Snacks Pvt Ltd):")
        self.stdout.write("  Name: Demo Snacks Pvt Ltd")
        self.stdout.write("  Address: 12 Industrial Estate, Tiruchirappalli - 620001, Tamil Nadu")
        self.stdout.write("  State: Tamil Nadu (33) | GSTIN: 33AAAAA0000A1Z5")
        self.stdout.write("  Evaluation Note: All data in this system is dummy data for evaluation.")

        # ---------------------------------------------------------------------
        # 1. Users: Role-based benchmark users
        # ---------------------------------------------------------------------
        users_data = [
            ('salesman', 'salesman123', Role.SALESMAN, 'Field Salesman A', 'Salesman'),
            ('salesman_a', 'salesman123', Role.SALESMAN, 'Field Salesman A', 'Salesman'),
            ('salesman_b', 'salesman123', Role.SALESMAN, 'Field Salesman B', 'Salesman'),
            ('admin', 'admin123', Role.ADMIN, 'Factory Admin User', 'Admin'),
            ('production', 'production123', Role.PRODUCTION, 'Production Supervisor', 'Production'),
            ('accountant', 'accountant123', Role.ACCOUNTANT, 'Auditor & Accountant User', 'Accountant'),
            ('owner', 'owner123', Role.OWNER, 'Executive Business Owner', 'Owner'),
        ]

        for username, password, role, first_name, last_name in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'role': role,
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': f'{username}@ordertoaudit.local'
                }
            )
            user.role = role
            user.first_name = first_name
            user.last_name = last_name
            user.set_password(password)
            user.save()
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  User: {action} '{username}' ({user.get_role_display()})")

        # ---------------------------------------------------------------------
        # 2. Standard Units of Measure
        # ---------------------------------------------------------------------
        units_data = [
            ('Kilogram', 'kg', UnitCategory.WEIGHT, Decimal('1.000000')),
            ('Gram', 'g', UnitCategory.WEIGHT, Decimal('0.001000')),
            ('Litre', 'litre', UnitCategory.VOLUME, Decimal('1.000000')),
            ('Millilitre', 'ml', UnitCategory.VOLUME, Decimal('0.001000')),
            ('Piece', 'piece', UnitCategory.COUNT, Decimal('1.000000')),
            ('Packet', 'packet', UnitCategory.COUNT, Decimal('1.000000')),
            ('Carton', 'carton', UnitCategory.COUNT, Decimal('1.000000')),
        ]
        units = {}
        for name, symbol, category, factor in units_data:
            unit, created = Unit.objects.get_or_create(
                symbol=symbol,
                defaults={'name': name, 'category': category, 'to_base_factor': factor}
            )
            unit.name = name
            unit.category = category
            unit.to_base_factor = factor
            unit.save()
            units[symbol] = unit
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  Unit: {action} {unit}")

        # ---------------------------------------------------------------------
        # 3. Conversion Rules
        # ---------------------------------------------------------------------
        conversions_data = [
            (units['carton'], units['packet'], Decimal('20.0000'), "1 carton holds 20 packets"),
            (units['kg'], units['g'], Decimal('1000.0000'), "1 kg = 1000 g"),
            (units['litre'], units['ml'], Decimal('1000.0000'), "1 litre = 1000 ml"),
        ]
        for from_u, to_u, factor, desc in conversions_data:
            conv, created = UnitConversion.objects.get_or_create(
                from_unit=from_u,
                to_unit=to_u,
                defaults={'factor': factor, 'description': desc}
            )
            conv.factor = factor
            conv.description = desc
            conv.save()
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  Conversion: {action} {conv}")

        # ---------------------------------------------------------------------
        # 4. Raw Materials (Section 5 Benchmark)
        # ---------------------------------------------------------------------
        rm_data = [
            ('Flour', 'RM-FLOUR', units['kg'], Decimal('42.00'), Decimal('20.000'), 'Standard flour for snacks (₹42 opening rate, ₹45 purchase)'),
            ('Cooking oil', 'RM-OIL', units['litre'], Decimal('140.00'), Decimal('10.000'), 'Refined cooking oil (₹140/litre)'),
            ('Salt and spice mix', 'RM-SPICE', units['kg'], Decimal('200.00'), Decimal('2.000'), 'Signature seasoning blend (₹200/kg)'),
        ]
        raw_materials = {}
        for name, code, unit, cost, reorder, desc in rm_data:
            rm, created = RawMaterial.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'unit': unit,
                    'standard_cost': cost,
                    'reorder_level': reorder,
                    'description': desc,
                }
            )
            rm.name = name
            rm.unit = unit
            rm.standard_cost = cost
            rm.reorder_level = reorder
            rm.description = desc
            rm.save()
            raw_materials[code] = rm
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  Raw Material: {action} {rm}")

        # ---------------------------------------------------------------------
        # 5. Packaging Materials (Section 5 Benchmark)
        # ---------------------------------------------------------------------
        pm_data = [
            ('200 g pouch', 'PM-POUCH-200G', units['piece'], Decimal('2.50'), 1, 'Printed 200g food-grade pouch (₹2.50/piece)'),
            ('Carton (holds 20 packets)', 'PM-CARTON-20', units['piece'], Decimal('15.00'), 20, 'Corrugated outer box holding 20 pkts (₹15.00/carton)'),
        ]
        packaging_items = {}
        for name, code, unit, cost, cap, desc in pm_data:
            pm, created = PackagingItem.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'unit': unit,
                    'standard_cost': cost,
                    'capacity_packets': cap,
                    'description': desc,
                }
            )
            pm.name = name
            pm.unit = unit
            pm.standard_cost = cost
            pm.capacity_packets = cap
            pm.description = desc
            pm.save()
            packaging_items[code] = pm
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  Packaging Item: {action} {pm}")

        # ---------------------------------------------------------------------
        # 6. Finished Goods Product (Murukku 200 g)
        # ---------------------------------------------------------------------
        product, created = Product.objects.get_or_create(
            code='FG-MURUKKU-200G',
            defaults={
                'name': 'Murukku 200 g',
                'hsn_code': '19059040',
                'pack_size': Decimal('200.00'),
                'pack_size_unit': units['g'],
                'unit': units['packet'],
                'selling_price': Decimal('50.00'),
                'gst_rate': Decimal('5.00'),
                'carton_pack_qty': 20,
                'description': 'Crispy traditional South Indian snack 200g (Selling Price: ₹50.00, GST: 5%)',
            }
        )
        product.name = 'Murukku 200 g'
        product.hsn_code = '19059040'
        product.pack_size = Decimal('200.00')
        product.pack_size_unit = units['g']
        product.unit = units['packet']
        product.selling_price = Decimal('50.00')
        product.gst_rate = Decimal('5.00')
        product.carton_pack_qty = 20
        product.save()
        action = 'Created' if created else 'Verified'
        self.stdout.write(f"  Product: {action} {product}")

        # ---------------------------------------------------------------------
        # 7. Bill of Materials (BOM) for Murukku 200 g
        # ---------------------------------------------------------------------
        bom, created = BillOfMaterial.objects.get_or_create(
            product=product,
            defaults={
                'name': 'Murukku 200 g Standard Recipe',
                'batch_size': Decimal('1.00'),
                'expected_yield_packets': 200,
                'notes': 'Benchmark recipe: 1 batch = 200 expected packets (Murukku 200g).',
            }
        )
        bom.name = 'Murukku 200 g Standard Recipe'
        bom.batch_size = Decimal('1.00')
        bom.expected_yield_packets = 200
        bom.save()

        # Idempotently sync lines to prevent duplicate BOM rows
        bom_lines_specs = [
            (raw_materials['RM-FLOUR'], None, Decimal('40.0000'), units['kg'], 'Standard batch flour issue (40 kg)'),
            (raw_materials['RM-OIL'], None, Decimal('10.0000'), units['litre'], 'Standard batch cooking oil (10 L)'),
            (raw_materials['RM-SPICE'], None, Decimal('1.2000'), units['kg'], 'Standard batch spice mix (1.2 kg)'),
            (None, packaging_items['PM-POUCH-200G'], Decimal('200.0000'), units['piece'], '200 pouches per batch'),
            (None, packaging_items['PM-CARTON-20'], Decimal('10.0000'), units['piece'], '10 cartons holding 20 pkts each'),
        ]

        bom.lines.all().delete()
        for rm, pm, qty, u, note in bom_lines_specs:
            BOMLine.objects.create(
                bom=bom,
                raw_material=rm,
                packaging_item=pm,
                quantity=qty,
                unit=u,
                notes=note
            )
        self.stdout.write(f"  BOM: Standard Recipe for {product.name} (Yield: {bom.expected_yield_packets} pkts, Cost/pkt: ₹{bom.standard_cost_per_packet})")

        # ---------------------------------------------------------------------
        # 8. Customers (Retailer A in Tamil Nadu, Distributor B in Karnataka)
        # ---------------------------------------------------------------------
        customers_data = [
            (
                'Retailer A',
                CustomerType.RETAILER,
                'K. Raman',
                '9876543210',
                'Tamil Nadu',
                '33',
                '33AABCT1234A1Z5',
                Decimal('20000.00'),
                '12 Bazaar St, Madurai, Tamil Nadu'
            ),
            (
                'Distributor B',
                CustomerType.DISTRIBUTOR,
                'S. Suresh',
                '9845012345',
                'Karnataka',
                '29',
                '29AABCD5678B1Z2',
                Decimal('50000.00'),
                '45 Ring Road, Bengaluru, Karnataka'
            ),
        ]
        for name, c_type, contact, phone, state, state_code, gstin, credit, addr in customers_data:
            cust, created = Customer.objects.get_or_create(
                name=name,
                defaults={
                    'customer_type': c_type,
                    'contact_person': contact,
                    'phone': phone,
                    'state': state,
                    'state_code': state_code,
                    'gstin': gstin,
                    'credit_limit': credit,
                    'address': addr,
                }
            )
            cust.customer_type = c_type
            cust.contact_person = contact
            cust.phone = phone
            cust.state = state
            cust.state_code = state_code
            cust.gstin = gstin
            cust.credit_limit = credit
            cust.address = addr
            cust.save()
            action = 'Created' if created else 'Verified'
            interstate = "Inter-state (IGST)" if cust.is_interstate() else "Intra-state (CGST+SGST)"
            self.stdout.write(f"  Customer: {action} {cust.name} [{cust.state}] - {interstate}")

        # ---------------------------------------------------------------------
        # 9. Suppliers (Tamil Nadu raw material and packaging vendors)
        # ---------------------------------------------------------------------
        suppliers_data = [
            ('Sri Murugan Flour Mills', 'M. Velu', '9840123456', 'Trichy', 'Tamil Nadu', '33', '33AABCS1111A1Z1'),
            ('Coimbatore Packaging Industries', 'P. Natarajan', '9842123456', 'Coimbatore', 'Tamil Nadu', '33', '33AABCP2222A1Z2'),
        ]
        for name, contact, phone, city, state, state_code, gstin in suppliers_data:
            sup, created = Supplier.objects.get_or_create(
                name=name,
                defaults={
                    'contact_person': contact,
                    'phone': phone,
                    'city': city,
                    'state': state,
                    'state_code': state_code,
                    'gstin': gstin,
                }
            )
            sup.contact_person = contact
            sup.phone = phone
            sup.city = city
            sup.state = state
            sup.state_code = state_code
            sup.gstin = gstin
            sup.save()
            action = 'Created' if created else 'Verified'
            self.stdout.write(f"  Supplier: {action} {sup}")

        # ---------------------------------------------------------------------
        # 10. Opening Stock Movements (PROBLEM.md Section 5)
        # Opening stock entries:
        # - Flour: 100 kg
        # - Cooking oil: 30 litre
        # - Salt and spice mix: 5 kg
        # - 200 g pouch: 500 piece
        # - Carton (holds 20 packets): 30 piece
        # - Murukku 200 g: 50 packets
        # Must be safe to run more than once: DO NOT DUPLICATE EXISTING MOVEMENTS.
        # ---------------------------------------------------------------------
        admin_user = User.objects.filter(role=Role.ADMIN).first()
        source_doc = 'OPENING-BENCHMARK-2026'

        opening_stock_items = [
            (raw_materials['RM-FLOUR'], Decimal('100.0000'), units['kg']),
            (raw_materials['RM-OIL'], Decimal('30.0000'), units['litre']),
            (raw_materials['RM-SPICE'], Decimal('5.0000'), units['kg']),
            (packaging_items['PM-POUCH-200G'], Decimal('500.0000'), units['piece']),
            (packaging_items['PM-CARTON-20'], Decimal('30.0000'), units['piece']),
            (product, Decimal('50.0000'), units['packet']),
        ]

        self.stdout.write("\n📦 Checking / Initializing Opening Stock Movements:")
        for item, qty, unit in opening_stock_items:
            # Check for existing movement with same source_document to prevent duplicates
            filter_kwargs = {
                'movement_type': MovementType.OPENING,
                'source_document': source_doc,
            }
            if isinstance(item, RawMaterial):
                filter_kwargs['raw_material'] = item
            elif isinstance(item, PackagingItem):
                filter_kwargs['packaging_item'] = item
            elif isinstance(item, Product):
                filter_kwargs['product'] = item

            existing_movement = StockMovement.objects.filter(**filter_kwargs).first()

            if existing_movement:
                self.stdout.write(
                    f"  Already Exists: {item.name} opening stock ({existing_movement.quantity} {existing_movement.unit.symbol}) [Doc: {source_doc}] -> Skipped duplicate."
                )
            else:
                m = record_movement(
                    item=item,
                    quantity=qty,
                    movement_type=MovementType.OPENING,
                    source_document=source_doc,
                    user=admin_user,
                    unit=unit,
                    notes='Section 5 Benchmark Opening Stock'
                )
                self.stdout.write(
                    f"  Recorded: {m.get_movement_type_display()} +{m.quantity} {m.unit.symbol} for {item.name} [Doc: {source_doc}]"
                )

        self.stdout.write("\n==================================================")
        self.stdout.write(self.style.SUCCESS("✅ Benchmark Master Data and Opening Stock successfully loaded!"))
        self.stdout.write("==================================================")

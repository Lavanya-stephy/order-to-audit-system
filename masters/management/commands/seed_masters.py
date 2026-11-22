from decimal import Decimal
from django.core.management.base import BaseCommand
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
from inventory.services import record_movement


class Command(BaseCommand):
    help = 'Seeds initial standard units, conversions, and benchmark master data'

    def handle(self, *args, **options):
        # 1. Units
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
            unit, _ = Unit.objects.get_or_create(
                symbol=symbol,
                defaults={'name': name, 'category': category, 'to_base_factor': factor}
            )
            unit.name = name
            unit.category = category
            unit.to_base_factor = factor
            unit.save()
            units[symbol] = unit
            self.stdout.write(f"Unit: {unit}")

        # 2. Conversion Rules
        conversions_data = [
            (units['carton'], units['packet'], Decimal('20.0000'), "1 carton holds 20 packets"),
            (units['kg'], units['g'], Decimal('1000.0000'), "1 kg = 1000 g"),
            (units['litre'], units['ml'], Decimal('1000.0000'), "1 litre = 1000 ml"),
        ]
        for from_u, to_u, factor, desc in conversions_data:
            conv, _ = UnitConversion.objects.get_or_create(
                from_unit=from_u,
                to_unit=to_u,
                defaults={'factor': factor, 'description': desc}
            )
            conv.factor = factor
            conv.description = desc
            conv.save()
            self.stdout.write(f"Conversion: {conv}")

        # 3. Raw Materials
        rm_data = [
            ('Flour', 'RM-FLOUR', units['kg'], Decimal('42.00'), Decimal('20.000'), 'Standard flour for snacks'),
            ('Cooking oil', 'RM-OIL', units['litre'], Decimal('140.00'), Decimal('10.000'), 'Refined cooking oil'),
            ('Salt and spice mix', 'RM-SPICE', units['kg'], Decimal('200.00'), Decimal('2.000'), 'Signature seasoning blend'),
        ]
        for name, code, unit, cost, reorder, desc in rm_data:
            rm, _ = RawMaterial.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'unit': unit,
                    'standard_cost': cost,
                    'reorder_level': reorder,
                    'description': desc,
                }
            )
            rm.standard_cost = cost
            rm.save()
            self.stdout.write(f"Raw Material: {rm}")

        # 4. Packaging Materials
        pm_data = [
            ('200 g pouch', 'PM-POUCH-200G', units['piece'], Decimal('2.50'), 1, 'Printed 200g food-grade pouch'),
            ('Carton (holds 20 packets)', 'PM-CARTON-20', units['piece'], Decimal('15.00'), 20, 'Corrugated outer box'),
        ]
        for name, code, unit, cost, cap, desc in pm_data:
            pm, _ = PackagingItem.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'unit': unit,
                    'standard_cost': cost,
                    'capacity_packets': cap,
                    'description': desc,
                }
            )
            pm.standard_cost = cost
            pm.save()
            self.stdout.write(f"Packaging Item: {pm}")

        # 5. Product
        product, _ = Product.objects.get_or_create(
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
                'description': 'Crispy traditional South Indian snack 200g',
            }
        )
        self.stdout.write(f"Product: {product}")

        # 5.1 BOM for Murukku 200 g (Section 5 Benchmark)
        bom, _ = BillOfMaterial.objects.get_or_create(
            product=product,
            defaults={
                'name': 'Murukku 200 g Standard Recipe',
                'batch_size': Decimal('1.00'),
                'expected_yield_packets': 200,
                'notes': 'Benchmark recipe: 1 batch = 200 expected packets (Murukku 200g).',
            }
        )
        bom.expected_yield_packets = 200
        bom.save()

        # Seed the 5 standard lines from section 5
        raw_flour = RawMaterial.objects.get(code='RM-FLOUR')
        raw_oil = RawMaterial.objects.get(code='RM-OIL')
        raw_spice = RawMaterial.objects.get(code='RM-SPICE')
        pm_pouch = PackagingItem.objects.get(code='PM-POUCH-200G')
        pm_carton = PackagingItem.objects.get(code='PM-CARTON-20')

        bom_lines_data = [
            (raw_flour, None, Decimal('40.0000'), units['kg'], 'Standard batch flour issue'),
            (raw_oil, None, Decimal('10.0000'), units['litre'], 'Standard batch cooking oil'),
            (raw_spice, None, Decimal('1.2000'), units['kg'], 'Standard batch spice mix (1200g)'),
            (None, pm_pouch, Decimal('200.0000'), units['piece'], '1 pouch per packet'),
            (None, pm_carton, Decimal('10.0000'), units['piece'], '1 carton per 20 packets (10 cartons)'),
        ]
        # Clear existing lines to prevent duplicates during re-seeding
        bom.lines.all().delete()
        for rm, pm, qty, u, note in bom_lines_data:
            line = BOMLine.objects.create(
                bom=bom,
                raw_material=rm,
                packaging_item=pm,
                quantity=qty,
                unit=u,
                notes=note
            )
            self.stdout.write(f"  -> BOM Line: {line}")
        self.stdout.write(f"BOM Created: {bom} | Total Std Batch Cost: ₹{bom.total_standard_cost} | Per Packet: ₹{bom.standard_cost_per_packet}")

        # 6. Customers
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
            cust, _ = Customer.objects.get_or_create(
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
            self.stdout.write(f"Customer: {cust}")

        # 7. Suppliers
        suppliers_data = [
            ('Sri Murugan Flour Mills', 'M. Velu', '9840123456', 'Trichy', 'Tamil Nadu', '33', '33AABCS1111A1Z1'),
            ('Coimbatore Packaging Industries', 'P. Natarajan', '9842123456', 'Coimbatore', 'Tamil Nadu', '33', '33AABCP2222A1Z2'),
        ]
        for name, contact, phone, city, state, state_code, gstin in suppliers_data:
            sup, _ = Supplier.objects.get_or_create(
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
            sup.save()
            self.stdout.write(f"Supplier: {sup}")

        # 8. Benchmark Section 5 Opening Stock
        # Flour: 100 kg, Oil: 30 L, Spice: 5 kg, Pouches: 500, Cartons: 30, Murukku 200g: 50 packets
        opening_items = [
            (raw_flour, Decimal('100.0000'), units['kg']),
            (raw_oil, Decimal('30.0000'), units['litre']),
            (raw_spice, Decimal('5.0000'), units['kg']),
            (pm_pouch, Decimal('500.0000'), units['piece']),
            (pm_carton, Decimal('30.0000'), units['piece']),
            (product, Decimal('50.0000'), units['packet']),
        ]
        for itm, qty, u in opening_items:
            already_recorded = False
            if hasattr(itm, 'stock_movements'):
                already_recorded = itm.stock_movements.filter(
                    movement_type=MovementType.OPENING,
                    source_document='OPENING-BENCHMARK-2026'
                ).exists()

            if not already_recorded:
                m = record_movement(
                    item=itm,
                    quantity=qty,
                    movement_type=MovementType.OPENING,
                    source_document='OPENING-BENCHMARK-2026',
                    unit=u,
                    notes='Section 5 Benchmark Opening Stock'
                )
                self.stdout.write(f"Opening Stock Movement: {m}")

        self.stdout.write(self.style.SUCCESS("Successfully seeded master data and opening stock!"))

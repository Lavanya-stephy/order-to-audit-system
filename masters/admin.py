from django.contrib import admin
from .models import (
    Unit,
    UnitConversion,
    RawMaterial,
    PackagingItem,
    Product,
    Customer,
    Supplier,
    BillOfMaterial,
    BOMLine,
)


class UnitConversionInline(admin.TabularInline):
    model = UnitConversion
    fk_name = 'from_unit'
    extra = 1


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'category', 'to_base_factor')
    list_filter = ('category',)
    search_fields = ('name', 'symbol')
    inlines = [UnitConversionInline]


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ('from_unit', 'to_unit', 'factor', 'description')
    list_filter = ('from_unit__category',)
    search_fields = ('from_unit__name', 'to_unit__name', 'description')


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'unit', 'standard_cost', 'reorder_level', 'is_active')
    list_filter = ('unit', 'is_active')
    search_fields = ('name', 'code', 'description')


@admin.register(PackagingItem)
class PackagingItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'unit', 'standard_cost', 'capacity_packets', 'reorder_level', 'is_active')
    list_filter = ('unit', 'is_active')
    search_fields = ('name', 'code', 'description')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'hsn_code',
        'pack_size',
        'pack_size_unit',
        'unit',
        'selling_price',
        'gst_rate',
        'is_active',
    )
    list_filter = ('gst_rate', 'is_active')
    search_fields = ('name', 'code', 'hsn_code')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'customer_type',
        'city',
        'state',
        'state_code',
        'gstin',
        'credit_limit',
        'is_active',
    )
    list_filter = ('customer_type', 'state', 'is_active')
    search_fields = ('name', 'gstin', 'contact_person', 'phone', 'city')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'city', 'state', 'state_code', 'is_active')
    list_filter = ('state', 'is_active')
    search_fields = ('name', 'contact_person', 'phone', 'city', 'gstin')


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 2
    fields = ('raw_material', 'packaging_item', 'quantity', 'unit', 'notes')


@admin.register(BillOfMaterial)
class BillOfMaterialAdmin(admin.ModelAdmin):
    list_display = ('product', 'expected_yield_packets', 'total_standard_cost', 'standard_cost_per_packet', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('product__name', 'name')
    inlines = [BOMLineInline]

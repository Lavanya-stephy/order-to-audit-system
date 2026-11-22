from django.contrib import admin
from .models import ProductionRun, ProductionRunItem


class ProductionRunItemInline(admin.TabularInline):
    model = ProductionRunItem
    extra = 0
    fields = ['raw_material', 'packaging_item', 'unit', 'standard_quantity', 'actual_quantity', 'unit_cost', 'movement_recorded']
    readonly_fields = ['movement_recorded']


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = ['run_number', 'product', 'status', 'expected_yield', 'actual_yield', 'yield_variance_pct', 'start_date', 'completion_date']
    list_filter = ['status', 'product', 'start_date']
    search_fields = ['run_number', 'product__name', 'notes']
    inlines = [ProductionRunItemInline]

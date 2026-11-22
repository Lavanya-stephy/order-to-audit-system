from django.contrib import admin
from .models import ProductionRun, ProductionRunItem, ProductionRunLog


class ProductionRunItemInline(admin.TabularInline):
    model = ProductionRunItem
    extra = 0
    fields = ['raw_material', 'packaging_item', 'unit', 'standard_quantity', 'actual_quantity', 'unit_cost', 'movement_recorded']
    readonly_fields = ['movement_recorded']


class ProductionRunLogInline(admin.TabularInline):
    model = ProductionRunLog
    extra = 0
    fields = ['timestamp', 'action', 'user', 'details']
    readonly_fields = ['timestamp', 'action', 'user', 'details']
    can_delete = False


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = ['run_number', 'product', 'status', 'expected_yield', 'actual_yield', 'yield_variance_pct', 'variance_tolerance_pct', 'start_date', 'completion_date']
    list_filter = ['status', 'product', 'start_date']
    search_fields = ['run_number', 'product__name', 'notes']
    inlines = [ProductionRunItemInline, ProductionRunLogInline]


@admin.register(ProductionRunLog)
class ProductionRunLogAdmin(admin.ModelAdmin):
    list_display = ['run', 'action', 'user', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['run__run_number', 'details']

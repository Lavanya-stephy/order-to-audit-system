from django.contrib import admin
from .models import SalesOrder, SalesOrderLine, SalesOrderLog


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0
    fields = ('product', 'quantity', 'unit', 'unit_price', 'line_total')
    readonly_fields = ('line_total',)


class SalesOrderLogInline(admin.TabularInline):
    model = SalesOrderLog
    extra = 0
    readonly_fields = ('user', 'action', 'details', 'timestamp')
    can_delete = False


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'salesman', 'order_date', 'status', 'total_quantity', 'grand_total', 'created_at')
    list_filter = ('status', 'order_date', 'salesman')
    search_fields = ('order_number', 'customer__name', 'salesman__username')
    inlines = [SalesOrderLineInline, SalesOrderLogInline]
    readonly_fields = ('created_at', 'updated_at', 'approved_at')

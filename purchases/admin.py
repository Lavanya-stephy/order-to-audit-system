from django.contrib import admin
from .models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ['raw_material', 'packaging_item', 'quantity', 'unit', 'unit_price', 'movement_recorded']
    readonly_fields = ['movement_recorded']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'order_date', 'status', 'total_value', 'created_by']
    list_filter = ['status', 'supplier', 'order_date']
    search_fields = ['po_number', 'supplier__name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [PurchaseOrderLineInline]

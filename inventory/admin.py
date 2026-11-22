from django.contrib import admin
from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'item_name',
        'item_type',
        'movement_type',
        'quantity',
        'unit',
        'source_document',
        'batch_number',
        'user',
    )
    list_filter = ('movement_type', 'created_at')
    search_fields = (
        'source_document',
        'batch_number',
        'raw_material__name',
        'packaging_item__name',
        'product__name',
    )
    readonly_fields = ('created_at',)

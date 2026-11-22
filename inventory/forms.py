from decimal import Decimal
from django import forms
from masters.models import RawMaterial, PackagingItem, Product, Unit
from .models import StockMovement, MovementType


class StockAdjustmentForm(forms.Form):
    item_type = forms.ChoiceField(
        choices=[
            ('raw_material', 'Raw Material'),
            ('packaging', 'Packaging Item'),
            ('product', 'Finished Product'),
        ],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_item_type'}),
        label="Item Category"
    )
    raw_material = forms.ModelChoiceField(
        queryset=RawMaterial.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control item-select', 'id': 'id_raw_material'}),
        label="Raw Material"
    )
    packaging_item = forms.ModelChoiceField(
        queryset=PackagingItem.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control item-select', 'id': 'id_packaging_item'}),
        label="Packaging Item"
    )
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control item-select', 'id': 'id_product'}),
        label="Finished Product"
    )
    movement_type = forms.ChoiceField(
        choices=[
            (MovementType.OPENING, 'Opening Balance'),
            (MovementType.ADJUSTMENT, 'Stock Adjustment (Physical Audit)'),
            (MovementType.PURCHASE, 'Purchase Receipt'),
            (MovementType.RETURN, 'Stock Return'),
        ],
        initial=MovementType.ADJUSTMENT,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Movement Type"
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'Positive for addition (+), negative for deduction (-)'}),
        help_text="Signed quantity: e.g. +100 for inward addition, -10 for damage/deduction."
    )
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Leave blank to use default item unit."
    )
    source_document = forms.CharField(
        max_length=100,
        initial='AUDIT-ADJ-001',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. AUDIT-2026-01, OPENING-2026'}),
        label="Source Document Reference"
    )
    batch_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional batch/lot number'})
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason for adjustment or opening record...'}),
        required=False
    )

    def clean(self):
        cleaned_data = super().clean()
        i_type = cleaned_data.get('item_type')
        rm = cleaned_data.get('raw_material')
        pm = cleaned_data.get('packaging_item')
        prod = cleaned_data.get('product')

        if i_type == 'raw_material' and not rm:
            self.add_error('raw_material', 'Please select a Raw Material.')
        elif i_type == 'packaging' and not pm:
            self.add_error('packaging_item', 'Please select a Packaging Item.')
        elif i_type == 'product' and not prod:
            self.add_error('product', 'Please select a Finished Product.')

        qty = cleaned_data.get('quantity')
        if qty == Decimal('0'):
            self.add_error('quantity', 'Quantity cannot be zero.')

        return cleaned_data

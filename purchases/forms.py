from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet, ValidationError
from masters.models import RawMaterial, PackagingItem, Unit, Supplier
from .models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['po_number', 'supplier', 'order_date', 'received_date', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'po_number': forms.TextInput(attrs={'placeholder': 'e.g. PO-2026-001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')
        self.fields['received_date'].required = False
        self.fields['notes'].required = False
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)


class PurchaseOrderLineForm(forms.ModelForm):
    ITEM_TYPE_CHOICES = [
        ('raw_material', 'Raw Material'),
        ('packaging', 'Packaging Item'),
    ]
    item_type = forms.ChoiceField(choices=ITEM_TYPE_CHOICES, required=False)
    raw_material = forms.ModelChoiceField(
        queryset=RawMaterial.objects.filter(is_active=True),
        required=False,
        empty_label="— Select Raw Material —",
    )
    packaging_item = forms.ModelChoiceField(
        queryset=PackagingItem.objects.filter(is_active=True),
        required=False,
        empty_label="— Select Packaging Item —",
    )

    class Meta:
        model = PurchaseOrderLine
        fields = ['item_type', 'raw_material', 'packaging_item', 'quantity', 'unit', 'unit_price']
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '0.0001', 'min': '0.0001', 'placeholder': 'e.g. 60.0'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': 'e.g. 45.00'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')

        # Determine item_type initial from existing instance
        if self.instance and self.instance.pk:
            if self.instance.raw_material:
                self.fields['item_type'].initial = 'raw_material'
            elif self.instance.packaging_item:
                self.fields['item_type'].initial = 'packaging'

    def has_changed(self):
        """
        An extra / new form is only considered changed if at least one meaningful
        field (raw_material, packaging_item, quantity, unit, unit_price) has data entered.
        If none of these have been filled, ignore the row (even if item_type has a value).
        """
        if self.instance and self.instance.pk:
            return super().has_changed()

        has_data = any(
            bool(self.data.get(self.add_prefix(f)))
            for f in ['raw_material', 'packaging_item', 'quantity', 'unit', 'unit_price']
        )
        if not has_data:
            return False

        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        rm = cleaned.get('raw_material')
        pm = cleaned.get('packaging_item')
        qty = cleaned.get('quantity')
        unit = cleaned.get('unit')
        price = cleaned.get('unit_price')

        # If completely empty, ignore without raising validation errors
        if not any([rm, pm, qty, unit, price]):
            return cleaned

        item_type = cleaned.get('item_type') or ('raw_material' if rm else 'packaging' if pm else 'raw_material')
        if item_type == 'raw_material':
            if not rm:
                self.add_error('raw_material', 'Please select a raw material.')
            cleaned['packaging_item'] = None
        elif item_type == 'packaging':
            if not pm:
                self.add_error('packaging_item', 'Please select a packaging item.')
            cleaned['raw_material'] = None

        if qty is not None and qty <= Decimal('0'):
            self.add_error('quantity', 'Quantity must be positive.')

        if price is not None and price <= Decimal('0'):
            self.add_error('unit_price', 'Unit price must be positive.')

        return cleaned


class BasePurchaseLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        # Count non-empty, non-deleted forms
        valid_lines = 0
        for form in self.forms:
            if not self._should_delete_form(form) and form.has_changed():
                valid_lines += 1
        if valid_lines < 1:
            raise ValidationError("Please add at least one line item to the purchase order.")


PurchaseLineFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderLine,
    form=PurchaseOrderLineForm,
    formset=BasePurchaseLineFormSet,
    extra=1,
    min_num=0,
    can_delete=True,
)

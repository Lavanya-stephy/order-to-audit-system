from django import forms
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
from django.forms import inlineformset_factory

FORM_CONTROL_ATTRS = {'class': 'form-control'}


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'symbol', 'category', 'to_base_factor']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kilogram'}),
            'symbol': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. kg'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'to_base_factor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
        }


class UnitConversionForm(forms.ModelForm):
    class Meta:
        model = UnitConversion
        fields = ['from_unit', 'to_unit', 'factor', 'description']
        widgets = {
            'from_unit': forms.Select(attrs={'class': 'form-control'}),
            'to_unit': forms.Select(attrs={'class': 'form-control'}),
            'factor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g. 20.0000'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1 carton holds 20 packets'}),
        }


class RawMaterialForm(forms.ModelForm):
    class Meta:
        model = RawMaterial
        fields = ['name', 'code', 'unit', 'standard_cost', 'reorder_level', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Flour'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. RM-FLOUR'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'standard_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PackagingItemForm(forms.ModelForm):
    class Meta:
        model = PackagingItem
        fields = ['name', 'code', 'unit', 'standard_cost', 'capacity_packets', 'reorder_level', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 200 g pouch'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. PM-POUCH-200G'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'standard_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'capacity_packets': forms.NumberInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name',
            'code',
            'hsn_code',
            'pack_size',
            'pack_size_unit',
            'unit',
            'selling_price',
            'gst_rate',
            'carton_pack_qty',
            'description',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Murukku 200 g'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. FG-MURUKKU-200G'}),
            'hsn_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 19059040'}),
            'pack_size': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'pack_size_unit': forms.Select(attrs={'class': 'form-control'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'gst_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'carton_pack_qty': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'name',
            'customer_type',
            'contact_person',
            'phone',
            'email',
            'address',
            'city',
            'state',
            'state_code',
            'gstin',
            'credit_limit',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Retailer A'}),
            'customer_type': forms.Select(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Tamil Nadu'}),
            'state_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 33'}),
            'gstin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '15-digit GSTIN'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'name',
            'contact_person',
            'phone',
            'email',
            'address',
            'city',
            'state',
            'state_code',
            'gstin',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sri Murugan Flour Mills'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'state_code': forms.TextInput(attrs={'class': 'form-control'}),
            'gstin': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BillOfMaterialForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterial
        fields = ['product', 'expected_yield_packets', 'notes', 'is_active']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'expected_yield_packets': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 200'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Recipe notes, batch instructions...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class BOMLineForm(forms.ModelForm):
    class Meta:
        model = BOMLine
        fields = ['raw_material', 'packaging_item', 'quantity', 'unit', 'notes']
        widgets = {
            'raw_material': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'packaging_item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'}),
        }


BOMLineFormSet = inlineformset_factory(
    BillOfMaterial,
    BOMLine,
    form=BOMLineForm,
    extra=4,
    can_delete=True
)

from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet, ValidationError
from django.utils import timezone

from masters.models import Customer, Product, Unit
from .models import SalesOrder, SalesOrderLine


class SalesOrderCreateForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ['customer', 'order_date', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Optional instructions or delivery notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True).order_by('name')
        self.fields['customer'].empty_label = "— Select Customer (Retailer / Distributor) —"
        self.fields['customer'].widget.attrs.update({'class': 'form-control select-customer'})
        self.fields['notes'].required = False
        if not self.initial.get('order_date'):
            self.initial['order_date'] = timezone.now().date()


class BaseSalesOrderLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        valid_lines = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            product = form.cleaned_data.get('product')
            quantity = form.cleaned_data.get('quantity')
            if product and quantity:
                valid_lines += 1

        if valid_lines == 0:
            raise ValidationError("Please add at least one product with quantity to the order.")


class SalesOrderLineForm(forms.ModelForm):
    class Meta:
        model = SalesOrderLine
        fields = ['product', 'quantity', 'unit', 'unit_price']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': '1', 'step': '1', 'placeholder': 'Qty', 'class': 'form-control line-qty'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Rate ₹', 'class': 'form-control line-price'}),
            'unit': forms.Select(attrs={'class': 'form-control line-unit'}),
            'product': forms.Select(attrs={'class': 'form-control line-product'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('name')
        self.fields['product'].empty_label = "— Select Product —"
        self.fields['unit'].queryset = Unit.objects.filter(name__iexact='packet') or Unit.objects.all()
        self.fields['unit_price'].required = False

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        unit = cleaned_data.get('unit')
        unit_price = cleaned_data.get('unit_price')

        if product:
            if not unit:
                cleaned_data['unit'] = product.unit
            if unit_price is None or unit_price == '':
                cleaned_data['unit_price'] = product.selling_price

        return cleaned_data

    def has_changed(self):
        # Ignore empty rows
        has_product = bool(self.data.get(self.add_prefix('product')))
        has_qty = bool(self.data.get(self.add_prefix('quantity')))
        if not has_product and not has_qty:
            return False
        return super().has_changed()


SalesOrderLineFormSet = inlineformset_factory(
    SalesOrder,
    SalesOrderLine,
    form=SalesOrderLineForm,
    formset=BaseSalesOrderLineFormSet,
    extra=1,
    can_delete=True,
)


class AdminOrderEditForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ['customer', 'order_date', 'notes']
        widgets = {
            'order_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True)
        self.fields['notes'].required = False


class AdminOrderLineForm(forms.ModelForm):
    class Meta:
        model = SalesOrderLine
        fields = ['product', 'quantity', 'unit', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'step': '1', 'min': '1', 'class': 'form-control'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
        }


AdminOrderLineFormSet = inlineformset_factory(
    SalesOrder,
    SalesOrderLine,
    form=AdminOrderLineForm,
    formset=BaseSalesOrderLineFormSet,
    extra=0,
    can_delete=True,
)

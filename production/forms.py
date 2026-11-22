from decimal import Decimal
from django import forms
from django.utils import timezone

from masters.models import Product, BillOfMaterial
from .models import ProductionRun, ProductionRunItem, DEFAULT_VARIANCE_TOLERANCE_PCT


class ProductionRunCreateForm(forms.ModelForm):
    class Meta:
        model = ProductionRun
        fields = ['product', 'bom', 'batch_multiplier', 'variance_tolerance_pct', 'start_date', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'id': 'id_product'}),
            'bom': forms.Select(attrs={'class': 'form-select', 'id': 'id_bom'}),
            'batch_multiplier': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'variance_tolerance_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0.0', 'placeholder': '3.00'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional run notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('name')
        self.fields['bom'].queryset = BillOfMaterial.objects.filter(is_active=True).select_related('product').order_by('name')
        self.fields['variance_tolerance_pct'].required = False
        self.fields['notes'].required = False

        if not self.initial.get('start_date'):
            self.initial['start_date'] = timezone.now().date()
        if not self.initial.get('batch_multiplier'):
            self.initial['batch_multiplier'] = Decimal('1.00')
        if not self.initial.get('variance_tolerance_pct'):
            self.initial['variance_tolerance_pct'] = DEFAULT_VARIANCE_TOLERANCE_PCT

    def clean_variance_tolerance_pct(self):
        val = self.cleaned_data.get('variance_tolerance_pct')
        if val is None or val == '':
            return DEFAULT_VARIANCE_TOLERANCE_PCT
        return val

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        bom = cleaned_data.get('bom')
        if product and bom and bom.product_id != product.id:
            self.add_error('bom', f"Selected BOM '{bom.name}' does not match product '{product.name}'.")
        return cleaned_data


class ProductionRunEditForm(forms.ModelForm):
    edit_reason = forms.CharField(
        max_length=255,
        required=True,
        label="Reason for Edit (Audit Log)",
        help_text="Provide a brief explanation of the modifications for the audit trail",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Corrected actual good packet count'})
    )

    class Meta:
        model = ProductionRun
        fields = ['variance_tolerance_pct', 'start_date', 'completion_date', 'notes']
        widgets = {
            'variance_tolerance_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0.0'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'completion_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['completion_date'].required = False
        self.fields['notes'].required = False


class ProductionIssueItemForm(forms.Form):
    item_id = forms.IntegerField(widget=forms.HiddenInput())
    actual_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=4,
        min_value=Decimal('0.0001'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'})
    )
    unit_cost = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )

    def clean_actual_quantity(self):
        val = self.cleaned_data.get('actual_quantity')
        if val is not None:
            return Decimal(str(val)).quantize(Decimal('0.0001'))
        return val

    def clean_unit_cost(self):
        val = self.cleaned_data.get('unit_cost')
        if val is not None:
            return Decimal(str(val)).quantize(Decimal('0.01'))
        return val


class ProductionOutputForm(forms.Form):
    actual_yield = forms.IntegerField(
        min_value=0,
        label="Good Output Packets",
        help_text="Actual number of good finished packets produced",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'e.g. 188'})
    )
    damaged_pouches = forms.IntegerField(
        min_value=0,
        initial=0,
        label="Damaged / Scrap Pouches",
        help_text="Number of empty pouches torn, misprinted, or discarded",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'e.g. 6'})
    )
    cartons_used = forms.IntegerField(
        min_value=0,
        initial=0,
        label="Cartons Used",
        help_text="Number of outer shipping boxes packed",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'e.g. 9'})
    )
    labour_cost = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        initial=Decimal('0.00'),
        label="Direct Labour Cost (₹)",
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    overhead_cost = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        initial=Decimal('0.00'),
        label="Overheads / Gas / Power (₹)",
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    completion_date = forms.DateField(
        label="Completion Date",
        initial=timezone.now,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

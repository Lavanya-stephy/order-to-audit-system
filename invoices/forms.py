from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import Payment, PaymentMode, Invoice, InvoiceStatus


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'payment_mode', 'reference_number', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'class': 'form-control'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'UTR / Cheque No / Txn ID'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional payment notes'}),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        if self.invoice and 'amount' in self.fields:
            self.fields['amount'].initial = self.invoice.outstanding_balance
            self.fields['amount'].help_text = f"Current outstanding balance: ₹{self.invoice.outstanding_balance}"
        if 'payment_date' in self.fields and not self.initial.get('payment_date'):
            self.initial['payment_date'] = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= Decimal('0.00'):
            raise forms.ValidationError("Payment amount must be greater than zero.")
        if self.invoice:
            remaining = self.invoice.outstanding_balance
            if amount is not None and amount > remaining:
                raise forms.ValidationError(
                    f"Payment amount (₹{amount}) cannot exceed the remaining balance (₹{remaining})."
                )
        return amount

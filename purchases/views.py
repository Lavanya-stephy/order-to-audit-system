from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from accounts.models import Role
from accounts.permissions import role_required
from .models import PurchaseOrder
from .forms import PurchaseOrderForm, PurchaseLineFormSet
from .services import receive_purchase_order

# Admin and Production can create/receive purchases; Accountant and Owner view only
PURCHASE_MANAGERS = [Role.ADMIN, Role.PRODUCTION]
PURCHASE_VIEWERS = [Role.ADMIN, Role.PRODUCTION, Role.ACCOUNTANT, Role.OWNER]


@login_required
@role_required(PURCHASE_VIEWERS)
def purchase_list_view(request):
    pos = PurchaseOrder.objects.select_related('supplier').prefetch_related('lines')
    return render(request, 'purchases/purchase_list.html', {'purchase_orders': pos})


@login_required
@role_required(PURCHASE_MANAGERS)
def purchase_create_view(request):
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            formset.instance = po
            formset.save()
            messages.success(request, f"Purchase Order '{po.po_number}' created as Draft.")
            return redirect('purchases:purchase_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm()
        formset = PurchaseLineFormSet()

    return render(request, 'purchases/purchase_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Purchase Order',
        'submit_label': 'Save as Draft',
    })


@login_required
@role_required(PURCHASE_VIEWERS)
def purchase_detail_view(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.select_related('supplier', 'created_by')
                           .prefetch_related('lines__raw_material', 'lines__packaging_item', 'lines__unit'), pk=pk)
    can_receive = (request.user.role in PURCHASE_MANAGERS or request.user.is_superuser) and po.status == PurchaseOrder.Status.DRAFT
    return render(request, 'purchases/purchase_detail.html', {
        'po': po,
        'can_receive': can_receive,
    })


@login_required
@role_required(PURCHASE_MANAGERS)
def purchase_receive_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        try:
            movements = receive_purchase_order(po, user=request.user)
            total_items = len(movements)
            messages.success(
                request,
                f"PO '{po.po_number}' received — {total_items} stock movement(s) recorded in ledger."
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('purchases:purchase_detail', pk=po.pk)
    # GET: show confirmation page
    return render(request, 'purchases/purchase_receive_confirm.html', {'po': po})

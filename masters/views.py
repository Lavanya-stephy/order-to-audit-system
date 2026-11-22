from decimal import Decimal
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from accounts.models import Role
from accounts.permissions import role_required, RoleRequiredMixin
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
from .forms import (
    UnitForm,
    UnitConversionForm,
    RawMaterialForm,
    PackagingItemForm,
    ProductForm,
    CustomerForm,
    SupplierForm,
    BillOfMaterialForm,
    BOMLineFormSet,
)

MASTER_MANAGERS = [Role.ADMIN, Role.PRODUCTION, Role.OWNER]
MASTER_VIEWERS = [Role.ADMIN, Role.PRODUCTION, Role.OWNER, Role.ACCOUNTANT]


@login_required
@role_required(MASTER_VIEWERS)
def masters_hub(request):
    """Central master data hub with summary statistics and quick navigation."""
    context = {
        'units_count': Unit.objects.count(),
        'conversions_count': UnitConversion.objects.count(),
        'raw_materials_count': RawMaterial.objects.count(),
        'packaging_items_count': PackagingItem.objects.count(),
        'products_count': Product.objects.count(),
        'customers_count': Customer.objects.count(),
        'suppliers_count': Supplier.objects.count(),
        'boms_count': BillOfMaterial.objects.count(),
        'can_edit': request.user.role in MASTER_MANAGERS or request.user.is_superuser,
    }
    return render(request, 'masters/hub.html', context)


# ==========================================
# Unit & Conversion Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class UnitListView(ListView):
    model = Unit
    template_name = 'masters/unit_list.html'
    context_object_name = 'units'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['conversions'] = UnitConversion.objects.select_related('from_unit', 'to_unit').all()
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class UnitCreateView(CreateView):
    model = Unit
    form_class = UnitForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:unit_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add New Unit'
        context['back_url'] = reverse('masters:unit_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Unit '{form.instance.name}' created.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class UnitUpdateView(UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:unit_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Unit: {self.object.name}"
        context['back_url'] = reverse('masters:unit_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Unit '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class UnitDeleteView(DeleteView):
    model = Unit
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:unit_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:unit_list')
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class UnitConversionCreateView(CreateView):
    model = UnitConversion
    form_class = UnitConversionForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:unit_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Unit Conversion Rule'
        context['back_url'] = reverse('masters:unit_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Conversion rule created: {form.instance}")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class UnitConversionDeleteView(DeleteView):
    model = UnitConversion
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:unit_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:unit_list')
        return context


# ==========================================
# Raw Material Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class RawMaterialListView(ListView):
    model = RawMaterial
    template_name = 'masters/rawmaterial_list.html'
    context_object_name = 'raw_materials'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class RawMaterialCreateView(CreateView):
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:rawmaterial_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Raw Material'
        context['back_url'] = reverse('masters:rawmaterial_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Raw Material '{form.instance.name}' added.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class RawMaterialUpdateView(UpdateView):
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:rawmaterial_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Raw Material: {self.object.name}"
        context['back_url'] = reverse('masters:rawmaterial_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Raw Material '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class RawMaterialDeleteView(DeleteView):
    model = RawMaterial
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:rawmaterial_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:rawmaterial_list')
        return context


# ==========================================
# Packaging Item Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class PackagingItemListView(ListView):
    model = PackagingItem
    template_name = 'masters/packagingitem_list.html'
    context_object_name = 'packaging_items'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class PackagingItemCreateView(CreateView):
    model = PackagingItem
    form_class = PackagingItemForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:packagingitem_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Packaging Item'
        context['back_url'] = reverse('masters:packagingitem_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Packaging Item '{form.instance.name}' added.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class PackagingItemUpdateView(UpdateView):
    model = PackagingItem
    form_class = PackagingItemForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:packagingitem_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Packaging Item: {self.object.name}"
        context['back_url'] = reverse('masters:packagingitem_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Packaging Item '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class PackagingItemDeleteView(DeleteView):
    model = PackagingItem
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:packagingitem_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:packagingitem_list')
        return context


# ==========================================
# Product Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class ProductListView(ListView):
    model = Product
    template_name = 'masters/product_list.html'
    context_object_name = 'products'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class ProductCreateView(CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Finished Product'
        context['back_url'] = reverse('masters:product_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Product '{form.instance.name}' added.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class ProductUpdateView(UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Product: {self.object.name}"
        context['back_url'] = reverse('masters:product_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Product '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class ProductDeleteView(DeleteView):
    model = Product
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:product_list')
        return context


# ==========================================
# Customer Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class CustomerListView(ListView):
    model = Customer
    template_name = 'masters/customer_list.html'
    context_object_name = 'customers'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class CustomerCreateView(CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Customer (Retailer / Distributor)'
        context['back_url'] = reverse('masters:customer_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Customer '{form.instance.name}' added.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class CustomerUpdateView(UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Customer: {self.object.name}"
        context['back_url'] = reverse('masters:customer_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Customer '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class CustomerDeleteView(DeleteView):
    model = Customer
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:customer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:customer_list')
        return context


# ==========================================
# Supplier Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class SupplierListView(ListView):
    model = Supplier
    template_name = 'masters/supplier_list.html'
    context_object_name = 'suppliers'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class SupplierCreateView(CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Supplier'
        context['back_url'] = reverse('masters:supplier_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Supplier '{form.instance.name}' added.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class SupplierUpdateView(UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'masters/form.html'
    success_url = reverse_lazy('masters:supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Supplier: {self.object.name}"
        context['back_url'] = reverse('masters:supplier_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Supplier '{form.instance.name}' updated.")
        return super().form_valid(form)


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:supplier_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:supplier_list')
        return context


# ==========================================
# Bill of Materials (BOM) Views
# ==========================================
@method_decorator(role_required(MASTER_VIEWERS), name='dispatch')
class BOMListView(ListView):
    model = BillOfMaterial
    template_name = 'masters/bom_list.html'
    context_object_name = 'boms'

    def get_queryset(self):
        return BillOfMaterial.objects.select_related('product', 'product__unit').prefetch_related('lines').all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_edit'] = self.request.user.role in MASTER_MANAGERS or self.request.user.is_superuser
        return context


@login_required
@role_required(MASTER_VIEWERS)
def bom_detail_view(request, pk):
    """Detailed recipe view with line item costs and standard margin breakdown."""
    bom = get_object_or_404(
        BillOfMaterial.objects.select_related('product', 'product__pack_size_unit', 'product__unit'),
        pk=pk
    )
    raw_lines = bom.raw_material_lines
    pkg_lines = bom.packaging_lines
    can_edit = request.user.role in MASTER_MANAGERS or request.user.is_superuser

    # Calculate estimated margin
    selling_price = bom.product.selling_price
    cost_per_pkt = bom.standard_cost_per_packet
    gross_margin_per_pkt = selling_price - cost_per_pkt
    margin_percent = ((gross_margin_per_pkt / selling_price) * Decimal('100')).quantize(Decimal('0.1')) if selling_price > 0 else Decimal('0.0')

    context = {
        'bom': bom,
        'raw_lines': raw_lines,
        'pkg_lines': pkg_lines,
        'can_edit': can_edit,
        'selling_price': selling_price,
        'cost_per_pkt': cost_per_pkt,
        'gross_margin_per_pkt': gross_margin_per_pkt,
        'margin_percent': margin_percent,
    }
    return render(request, 'masters/bom_detail.html', context)


@login_required
@role_required(MASTER_MANAGERS)
def bom_create_view(request):
    """Create a new BOM with multiple line items."""
    if request.method == 'POST':
        form = BillOfMaterialForm(request.POST)
        formset = BOMLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                bom = form.save()
                formset.instance = bom
                formset.save()
            messages.success(request, f"BOM for '{bom.product.name}' created successfully.")
            return redirect('masters:bom_detail', pk=bom.pk)
    else:
        form = BillOfMaterialForm()
        formset = BOMLineFormSet()

    return render(request, 'masters/bom_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Bill of Materials (BOM)',
        'back_url': reverse('masters:bom_list'),
    })


@login_required
@role_required(MASTER_MANAGERS)
def bom_update_view(request, pk):
    """Edit an existing BOM and its recipe line items."""
    bom = get_object_or_404(BillOfMaterial, pk=pk)
    if request.method == 'POST':
        form = BillOfMaterialForm(request.POST, instance=bom)
        formset = BOMLineFormSet(request.POST, instance=bom)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                bom = form.save()
                formset.save()
            messages.success(request, f"BOM for '{bom.product.name}' updated successfully.")
            return redirect('masters:bom_detail', pk=bom.pk)
    else:
        form = BillOfMaterialForm(instance=bom)
        formset = BOMLineFormSet(instance=bom)

    return render(request, 'masters/bom_form.html', {
        'form': form,
        'formset': formset,
        'bom': bom,
        'title': f"Edit BOM: {bom.product.name}",
        'back_url': reverse('masters:bom_detail', pk=bom.pk),
    })


@method_decorator(role_required(MASTER_MANAGERS), name='dispatch')
class BOMDeleteView(DeleteView):
    model = BillOfMaterial
    template_name = 'masters/confirm_delete.html'
    success_url = reverse_lazy('masters:bom_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['back_url'] = reverse('masters:bom_list')
        return context

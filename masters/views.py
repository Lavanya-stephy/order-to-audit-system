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
)
from .forms import (
    UnitForm,
    UnitConversionForm,
    RawMaterialForm,
    PackagingItemForm,
    ProductForm,
    CustomerForm,
    SupplierForm,
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

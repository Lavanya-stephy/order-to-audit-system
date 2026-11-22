from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role
from accounts.permissions import role_required
from masters.models import Product, Customer
from inventory.services import get_item_current_stock
from .models import SalesOrder, SalesOrderLine, SalesOrderLog, OrderStatus
from .forms import (
    SalesOrderCreateForm,
    SalesOrderLineFormSet,
    AdminOrderEditForm,
    AdminOrderLineFormSet,
)
from .services import (
    create_sales_order,
    admin_update_order,
    approve_sales_order,
    reject_sales_order,
    generate_order_number,
)


@login_required
def order_home_redirect(request):
    """Redirects user to the appropriate order view based on their role."""
    if request.user.role == Role.SALESMAN:
        return redirect('orders:salesman_order_list')
    return redirect('orders:admin_order_list')


# -------------------------------------------------------------------------
# Salesman Views
# -------------------------------------------------------------------------

@login_required
@role_required([Role.SALESMAN, Role.ADMIN])
def order_create_view(request):
    """
    Mobile-friendly order entry screen for salesmen (and admin).
    Pick customer, select products, quantities, price from price list.
    """
    products = Product.objects.filter(is_active=True).select_related('unit')
    customers = Customer.objects.filter(is_active=True)

    if request.method == 'POST':
        form = SalesOrderCreateForm(request.POST)
        formset = SalesOrderLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.salesman = request.user
            order.order_number = generate_order_number()
            order.status = OrderStatus.SUBMITTED
            order.save()

            formset.instance = order
            # Ensure price and unit are filled from product if missing
            lines = formset.save(commit=False)
            for line in lines:
                if not line.unit_id:
                    line.unit = line.product.unit
                if line.unit_price is None or line.unit_price == '':
                    line.unit_price = line.product.selling_price
                line.save()
            for obj in formset.deleted_objects:
                obj.delete()

            SalesOrderLog.objects.create(
                order=order,
                user=request.user,
                action='Submitted',
                details=f"Order submitted by {request.user.username} for {order.customer.name} with {order.lines.count()} line(s).",
            )

            messages.success(request, f"Order '{order.order_number}' submitted successfully!")
            return redirect('orders:order_detail', pk=order.pk)
    else:
        form = SalesOrderCreateForm()
        formset = SalesOrderLineFormSet()

    # Pass products with their selling price and unit symbol for dynamic JS pricing
    products_json = [
        {
            'id': p.id,
            'name': p.name,
            'code': p.code,
            'selling_price': str(p.selling_price),
            'unit_id': p.unit.id,
            'unit_symbol': p.unit.symbol,
            'available_stock': str(get_item_current_stock(p)),
        }
        for p in products
    ]

    return render(request, 'orders/order_form.html', {
        'form': form,
        'formset': formset,
        'products': products,
        'customers': customers,
        'products_json': products_json,
        'title': 'New Sales Order',
    })


@login_required
@role_required([Role.SALESMAN])
def salesman_order_list_view(request):
    """
    Mobile-optimized view for salesmen. Salesmen see ONLY their own orders.
    """
    orders = (
        SalesOrder.objects.filter(salesman=request.user)
        .select_related('customer')
        .prefetch_related('lines', 'lines__product')
    )

    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        orders = orders.filter(status=status_filter)

    return render(request, 'orders/salesman_order_list.html', {
        'orders': orders,
        'current_status': status_filter or 'all',
        'status_choices': OrderStatus.choices,
    })


# -------------------------------------------------------------------------
# Admin Views
# -------------------------------------------------------------------------

@login_required
@role_required([Role.ADMIN, Role.OWNER, Role.ACCOUNTANT])
def admin_order_list_view(request):
    """
    Admin incoming orders screen.
    Admin sees incoming orders from all salesmen, with stock coverage indicators.
    """
    orders_qs = (
        SalesOrder.objects.all()
        .select_related('customer', 'salesman')
        .prefetch_related('lines', 'lines__product')
    )

    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        orders_qs = orders_qs.filter(status=status_filter)

    orders_with_coverage = []
    for order in orders_qs:
        coverage = order.check_stock_coverage()
        orders_with_coverage.append({
            'order': order,
            'coverage': coverage,
        })

    return render(request, 'orders/admin_order_list.html', {
        'orders_with_coverage': orders_with_coverage,
        'current_status': status_filter or 'all',
        'status_choices': OrderStatus.choices,
    })


@login_required
def order_detail_view(request, pk):
    """
    Order detail screen.
    Salesman sees ONLY their own orders; other salesmen get 403 Forbidden.
    Admin, Owner, and Accountant can view all orders.
    """
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'salesman', 'approved_by')
        .prefetch_related('lines', 'lines__product', 'lines__unit', 'audit_logs', 'audit_logs__user'),
        pk=pk
    )

    # Salesman isolation check
    if request.user.role == Role.SALESMAN and order.salesman != request.user and not request.user.is_superuser:
        raise PermissionDenied("You can only view your own orders.")

    coverage = order.check_stock_coverage()

    return render(request, 'orders/order_detail.html', {
        'order': order,
        'coverage': coverage,
        'can_edit': (request.user.role == Role.ADMIN or request.user.is_superuser) and order.status in [OrderStatus.SUBMITTED, OrderStatus.APPROVED],
        'can_approve_reject': (request.user.role == Role.ADMIN or request.user.is_superuser) and order.status == OrderStatus.SUBMITTED,
        'can_generate_invoice': (request.user.role == Role.ADMIN or request.user.is_superuser) and order.status == OrderStatus.APPROVED,
    })


@login_required
@role_required([Role.ADMIN])
def admin_order_edit_view(request, pk):
    """
    Admin can edit quantities or prices of line items and update notes.
    Shows current finished-goods stock coverage right on the editing screen.
    """
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'salesman'),
        pk=pk
    )

    if order.status not in [OrderStatus.SUBMITTED, OrderStatus.APPROVED]:
        messages.error(request, f"Cannot edit an order with status '{order.get_status_display()}'.")
        return redirect('orders:order_detail', pk=order.pk)

    if request.method == 'POST':
        form = AdminOrderEditForm(request.POST, instance=order)
        formset = AdminOrderLineFormSet(request.POST, instance=order)
        if form.is_valid() and formset.is_valid():
            # Track changes for audit log
            old_notes = order.notes
            form.save()

            lines_to_save = formset.save(commit=False)
            changes = []
            for line in lines_to_save:
                line.save()
                changes.append(f"{line.product.name}: qty={line.quantity}, price=₹{line.unit_price}")
            for obj in formset.deleted_objects:
                changes.append(f"Removed item {obj.product.name}")
                obj.delete()

            details_str = "; ".join(changes) if changes else "Saved without line changes"
            SalesOrderLog.objects.create(
                order=order,
                user=request.user,
                action='Edited',
                details=f"Admin {request.user.username} edited line items: {details_str}",
            )

            messages.success(request, f"Order '{order.order_number}' updated successfully.")
            return redirect('orders:order_detail', pk=order.pk)
    else:
        form = AdminOrderEditForm(instance=order)
        formset = AdminOrderLineFormSet(instance=order)

    # Attach available stock to form lines for convenient display
    for line_form in formset:
        if line_form.instance.pk and line_form.instance.product:
            line_form.available_stock = get_item_current_stock(line_form.instance.product)
        else:
            line_form.available_stock = Decimal('0.00')

    coverage = order.check_stock_coverage()

    return render(request, 'orders/admin_order_edit.html', {
        'order': order,
        'form': form,
        'formset': formset,
        'coverage': coverage,
    })


@login_required
@role_required([Role.ADMIN])
@require_POST
def admin_order_approve_view(request, pk):
    """
    Admin approves incoming order.
    """
    order = get_object_or_404(SalesOrder, pk=pk)
    try:
        notes = request.POST.get('approval_notes', '').strip()
        approve_sales_order(order, admin_user=request.user, notes=notes)
        messages.success(request, f"Order '{order.order_number}' has been APPROVED.")
    except Exception as e:
        messages.error(request, f"Error approving order: {str(e)}")

    return redirect('orders:order_detail', pk=order.pk)


@login_required
@role_required([Role.ADMIN])
@require_POST
def admin_order_reject_view(request, pk):
    """
    Admin rejects incoming order.
    """
    order = get_object_or_404(SalesOrder, pk=pk)
    reason = request.POST.get('rejection_reason', '').strip()
    try:
        reject_sales_order(order, admin_user=request.user, reason=reason)
        messages.warning(request, f"Order '{order.order_number}' has been REJECTED.")
    except Exception as e:
        messages.error(request, f"Error rejecting order: {str(e)}")

    return redirect('orders:order_detail', pk=order.pk)


# -------------------------------------------------------------------------
# JSON API for dynamic UI
# -------------------------------------------------------------------------

@login_required
def api_product_info(request, pk):
    """Returns price and stock info for a product."""
    product = get_object_or_404(Product, pk=pk)
    stock = get_item_current_stock(product)
    return JsonResponse({
        'id': product.id,
        'name': product.name,
        'code': product.code,
        'selling_price': str(product.selling_price),
        'unit_id': product.unit.id,
        'unit_symbol': product.unit.symbol,
        'available_stock': str(stock),
    })

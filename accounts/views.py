from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Role
from .permissions import role_required, get_dashboard_url_name_for_user


class CustomLoginView(auth_views.LoginView):
    """
    Login view that automatically routes authenticated users to their
    designated role dashboard unless an explicit and safe 'next' param is provided.
    """
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure()
        ):
            return next_url
        return reverse(get_dashboard_url_name_for_user(self.request.user))


@login_required
def role_redirect_view(request):
    """Entrypoint redirecting users to their role-specific dashboard."""
    return redirect(get_dashboard_url_name_for_user(request.user))


@role_required([Role.SALESMAN])
def salesman_dashboard(request):
    """Salesman interface: mobile order entry, customer-wise order tracking."""
    context = {
        'page_title': 'Salesman Mobile Portal',
        'role_name': 'Salesman',
    }
    return render(request, 'accounts/salesman_dashboard.html', context)


@role_required([Role.ADMIN])
def admin_dashboard(request):
    """Factory Admin interface: incoming orders, stock verification, GST invoices, dispatch."""
    context = {
        'page_title': 'Factory Admin Desk',
        'role_name': 'Factory Admin',
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@role_required([Role.PRODUCTION])
def production_dashboard(request):
    """Production Supervisor interface: recipe BOM, issue logs, daily runs, yield/wastage."""
    from production.models import ProductionRun
    recent_runs = ProductionRun.objects.select_related('product', 'bom').order_by('-created_at')[:5]
    in_progress_count = ProductionRun.objects.filter(status=ProductionRun.Status.IN_PROGRESS).count()
    completed_count = ProductionRun.objects.filter(status=ProductionRun.Status.COMPLETED).count()

    context = {
        'page_title': 'Production Floor Portal',
        'role_name': 'Production Supervisor',
        'recent_runs': recent_runs,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
    }
    return render(request, 'accounts/production_dashboard.html', context)


@role_required([Role.ACCOUNTANT])
def accountant_dashboard(request):
    """Accountant / Auditor interface: read-only monthly packs, registers, stock ledgers."""
    context = {
        'page_title': 'Auditor & Accounts Portal (Read-Only)',
        'role_name': 'Accountant / Auditor',
    }
    return render(request, 'accounts/accountant_dashboard.html', context)


@role_required([Role.OWNER])
def owner_dashboard(request):
    """
    Owner interface: high-level business pulse.
    Includes:
      1. Today's orders & pipeline
      2. Current stock levels across finished goods, raw materials, and packaging
      3. Production variance alerts (flagged runs beyond tolerance)
      4. Latest cost per packet and margins for products
      5. Outstanding receivables and customer dues
    """
    from decimal import Decimal
    from django.utils import timezone
    from orders.models import SalesOrder, OrderStatus
    from inventory.services import get_stock_summary
    from reports.services import get_production_variance_report_data
    from invoices.services import get_ageing_report
    from masters.models import Product
    from production.models import ProductionRun

    today = timezone.localdate()

    # 1. Today's orders
    todays_orders_qs = (
        SalesOrder.objects
        .filter(created_at__date=today)
        .select_related('customer', 'salesman')
        .prefetch_related('lines', 'lines__product')
        .order_by('-created_at')
    )
    todays_orders = list(todays_orders_qs)
    todays_orders_count = len(todays_orders)
    todays_orders_total_val = sum((o.grand_total for o in todays_orders), Decimal('0.00'))

    # If no orders placed today, also provide recent orders for context
    recent_orders = list(
        SalesOrder.objects
        .select_related('customer', 'salesman')
        .prefetch_related('lines', 'lines__product')
        .order_by('-created_at')[:8]
    )

    pending_approval_count = SalesOrder.objects.filter(status=OrderStatus.SUBMITTED).count()
    approved_count = SalesOrder.objects.filter(status=OrderStatus.APPROVED).count()
    dispatched_today_count = SalesOrder.objects.filter(
        status=OrderStatus.DISPATCHED,
        updated_at__date=today
    ).count()

    # 2. Stock levels
    all_stock = get_stock_summary()
    fg_stock = [s for s in all_stock if s['type_code'] == 'product']
    rm_stock = [s for s in all_stock if s['type_code'] == 'raw_material']
    pkg_stock = [s for s in all_stock if s['type_code'] == 'packaging']

    total_stock_valuation = sum((s['valuation'] for s in all_stock), Decimal('0.00'))
    fg_valuation = sum((s['valuation'] for s in fg_stock), Decimal('0.00'))
    rm_valuation = sum((s['valuation'] for s in rm_stock), Decimal('0.00'))
    pkg_valuation = sum((s['valuation'] for s in pkg_stock), Decimal('0.00'))
    low_stock_items = [s for s in all_stock if s['is_low_stock']]

    # 3. Variance alerts
    variance_report = get_production_variance_report_data()
    all_runs_data = variance_report.get('runs_data', [])
    flagged_runs = [rd for rd in all_runs_data if rd['has_variance_flag']]
    flagged_runs_count = len(flagged_runs)

    # 4. Cost per packet & product margins
    products = Product.objects.filter(is_active=True).select_related('unit').order_by('name')
    product_costing_list = []
    for prod in products:
        latest_run = (
            prod.production_runs
            .filter(status=ProductionRun.Status.COMPLETED)
            .order_by('-completion_date', '-id')
            .first()
        )
        product_costing_list.append({
            'product': prod,
            'latest_run': latest_run,
            'cost_per_packet': latest_run.actual_cost_per_packet if latest_run else None,
            'selling_price': prod.selling_price,
            'margin_per_packet': latest_run.margin_per_packet if latest_run else None,
            'margin_pct': latest_run.margin_pct if latest_run else None,
            'raw_material_cost': latest_run.total_raw_material_cost if latest_run else None,
            'packaging_cost': latest_run.total_packaging_cost if latest_run else None,
            'labour_cost': latest_run.labour_cost if latest_run else None,
            'overhead_cost': latest_run.overhead_cost if latest_run else None,
            'total_production_cost': latest_run.total_production_cost if latest_run else None,
        })

    # 5. Outstanding dues & receivables ageing
    ageing_data = get_ageing_report(as_of_date=today)
    total_receivables = ageing_data['summary']['total_receivables']
    top_debtors = ageing_data['customers'][:6]  # top 6 customers by outstanding

    context = {
        'page_title': 'Owner Executive Dashboard',
        'role_name': 'Owner',
        'today': today,

        # Today's orders
        'todays_orders': todays_orders,
        'todays_orders_count': todays_orders_count,
        'todays_orders_total_val': todays_orders_total_val,
        'recent_orders': recent_orders,
        'pending_approval_count': pending_approval_count,
        'approved_count': approved_count,
        'dispatched_today_count': dispatched_today_count,

        # Stock levels
        'fg_stock': fg_stock,
        'rm_stock': rm_stock,
        'pkg_stock': pkg_stock,
        'total_stock_valuation': total_stock_valuation,
        'fg_valuation': fg_valuation,
        'rm_valuation': rm_valuation,
        'pkg_valuation': pkg_valuation,
        'low_stock_items': low_stock_items,

        # Variance alerts
        'flagged_runs': flagged_runs,
        'flagged_runs_count': flagged_runs_count,
        'recent_runs_data': all_runs_data[:5],

        # Cost per packet
        'product_costing_list': product_costing_list,

        # Outstanding dues
        'total_receivables': total_receivables,
        'ageing_summary': ageing_data['summary'],
        'top_debtors': top_debtors,
    }
    return render(request, 'accounts/owner_dashboard.html', context)


def custom_permission_denied_view(request, exception=None):
    """Custom 403 page displayed when a user attempts to access an unauthorized role page."""
    context = {
        'exception_message': str(exception) if exception else 'Access restricted to authorized roles only.',
    }
    return render(request, '403.html', context, status=403)

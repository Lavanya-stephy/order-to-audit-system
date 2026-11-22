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
    context = {
        'page_title': 'Production Floor Portal',
        'role_name': 'Production Supervisor',
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
    """Owner interface: high-level business pulse, variance alerts, cost per packet."""
    context = {
        'page_title': 'Owner Executive Summary',
        'role_name': 'Owner',
    }
    return render(request, 'accounts/owner_dashboard.html', context)


def custom_permission_denied_view(request, exception=None):
    """Custom 403 page displayed when a user attempts to access an unauthorized role page."""
    context = {
        'exception_message': str(exception) if exception else 'Access restricted to authorized roles only.',
    }
    return render(request, '403.html', context, status=403)

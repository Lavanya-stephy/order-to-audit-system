from functools import wraps
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import Role

ROLE_DASHBOARD_URLS = {
    Role.SALESMAN: 'salesman_dashboard',
    Role.ADMIN: 'admin_dashboard',
    Role.PRODUCTION: 'production_dashboard',
    Role.ACCOUNTANT: 'accountant_dashboard',
    Role.OWNER: 'owner_dashboard',
}


def get_dashboard_url_name_for_user(user):
    """Returns the URL pattern name corresponding to the user's role."""
    if not user.is_authenticated:
        return 'login'
    return ROLE_DASHBOARD_URLS.get(user.role, 'login')


def role_required(allowed_roles):
    """
    Decorator for views that checks whether a user has one of the allowed roles.
    Raises PermissionDenied (403) if the user does not have permission.
    Superusers bypass this check.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied(
                f"Access denied: '{request.user.get_role_display()}' cannot access this resource."
            )

        return _wrapped_view

    return decorator


class RoleRequiredMixin(AccessMixin):
    """CBV mixin that verifies the current user has the required role."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or request.user.role in self.allowed_roles):
            raise PermissionDenied(
                f"Access denied: '{request.user.get_role_display()}' cannot access this resource."
            )
        return super().dispatch(request, *args, **kwargs)

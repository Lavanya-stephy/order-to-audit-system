from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.role_redirect_view, name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.role_redirect_view, name='role_redirect'),

    # Role-specific dashboard endpoints
    path('salesman/', views.salesman_dashboard, name='salesman_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('production/', views.production_dashboard, name='production_dashboard'),
    path('audit/', views.accountant_dashboard, name='accountant_dashboard'),
    path('owner/', views.owner_dashboard, name='owner_dashboard'),
]

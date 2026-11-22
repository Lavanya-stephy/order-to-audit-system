from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('', views.order_home_redirect, name='order_home'),
    path('new/', views.order_create_view, name='order_create'),
    path('my-orders/', views.salesman_order_list_view, name='salesman_order_list'),
    path('incoming/', views.admin_order_list_view, name='admin_order_list'),
    path('<int:pk>/', views.order_detail_view, name='order_detail'),
    path('<int:pk>/edit/', views.admin_order_edit_view, name='admin_order_edit'),
    path('<int:pk>/approve/', views.admin_order_approve_view, name='admin_order_approve'),
    path('<int:pk>/reject/', views.admin_order_reject_view, name='admin_order_reject'),
    path('api/product/<int:pk>/', views.api_product_info, name='api_product_info'),
]

from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.stock_summary_view, name='stock_summary'),
    path('summary/', views.stock_summary_view, name='stock_summary'),
    path('ledger/', views.stock_ledger_view, name='stock_ledger'),
    path('adjust/', views.stock_adjustment_view, name='stock_adjust'),
]

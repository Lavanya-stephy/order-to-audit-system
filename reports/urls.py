from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_hub_view, name='hub'),
    path('sales-register/', views.sales_register_view, name='sales_register'),
    path('gst-summary/', views.gst_summary_view, name='gst_summary'),
    path('purchases/', views.purchase_register_view, name='purchase_register'),
    path('stock/', views.stock_report_view, name='stock_report'),
    path('production/', views.production_variance_report_view, name='production_variance'),
    path('receivables/', views.receivables_ageing_view, name='receivables_ageing'),
]

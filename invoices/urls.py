from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('',                           views.invoice_list_view,     name='invoice_list'),
    path('<int:pk>/',                  views.invoice_detail_view,   name='invoice_detail'),
    path('<int:pk>/pdf/',              views.invoice_pdf_view,      name='invoice_pdf'),
    path('<int:pk>/dispatch/',         views.invoice_dispatch_view, name='invoice_dispatch'),
    path('<int:pk>/cancel/',           views.invoice_cancel_view,   name='invoice_cancel'),
    path('generate/<int:order_pk>/',   views.invoice_generate_view, name='invoice_generate'),
]

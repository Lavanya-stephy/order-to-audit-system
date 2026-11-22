from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('', views.purchase_list_view, name='purchase_list'),
    path('create/', views.purchase_create_view, name='purchase_create'),
    path('<int:pk>/', views.purchase_detail_view, name='purchase_detail'),
    path('<int:pk>/receive/', views.purchase_receive_view, name='purchase_receive'),
]

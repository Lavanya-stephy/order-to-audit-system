from django.urls import path
from . import views

app_name = 'production'

urlpatterns = [
    path('', views.production_run_list_view, name='production_run_list'),
    path('costing/', views.product_costing_view, name='product_costing'),
    path('create/', views.production_run_create_view, name='production_run_create'),
    path('<int:pk>/', views.production_run_detail_view, name='production_run_detail'),
    path('<int:pk>/edit/', views.production_run_edit_view, name='production_run_edit'),
    path('<int:pk>/issue/', views.production_run_issue_view, name='production_run_issue'),
    path('<int:pk>/output/', views.production_run_output_view, name='production_run_output'),
]

from django.urls import path
from . import views

app_name = 'masters'

urlpatterns = [
    path('', views.masters_hub, name='hub'),

    # Units
    path('units/', views.UnitListView.as_view(), name='unit_list'),
    path('units/add/', views.UnitCreateView.as_view(), name='unit_add'),
    path('units/<int:pk>/edit/', views.UnitUpdateView.as_view(), name='unit_edit'),
    path('units/<int:pk>/delete/', views.UnitDeleteView.as_view(), name='unit_delete'),

    # Conversions
    path('conversions/add/', views.UnitConversionCreateView.as_view(), name='conversion_add'),
    path('conversions/<int:pk>/delete/', views.UnitConversionDeleteView.as_view(), name='conversion_delete'),

    # Raw Materials
    path('raw-materials/', views.RawMaterialListView.as_view(), name='rawmaterial_list'),
    path('raw-materials/add/', views.RawMaterialCreateView.as_view(), name='rawmaterial_add'),
    path('raw-materials/<int:pk>/edit/', views.RawMaterialUpdateView.as_view(), name='rawmaterial_edit'),
    path('raw-materials/<int:pk>/delete/', views.RawMaterialDeleteView.as_view(), name='rawmaterial_delete'),

    # Packaging Items
    path('packaging/', views.PackagingItemListView.as_view(), name='packagingitem_list'),
    path('packaging/add/', views.PackagingItemCreateView.as_view(), name='packagingitem_add'),
    path('packaging/<int:pk>/edit/', views.PackagingItemUpdateView.as_view(), name='packagingitem_edit'),
    path('packaging/<int:pk>/delete/', views.PackagingItemDeleteView.as_view(), name='packagingitem_delete'),

    # Products
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),

    # Customers
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/add/', views.CustomerCreateView.as_view(), name='customer_add'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer_edit'),
    path('customers/<int:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer_delete'),

    # Suppliers
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', views.SupplierCreateView.as_view(), name='supplier_add'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),

    # Bills of Materials (BOM)
    path('boms/', views.BOMListView.as_view(), name='bom_list'),
    path('boms/add/', views.bom_create_view, name='bom_add'),
    path('boms/<int:pk>/', views.bom_detail_view, name='bom_detail'),
    path('boms/<int:pk>/edit/', views.bom_update_view, name='bom_edit'),
    path('boms/<int:pk>/delete/', views.BOMDeleteView.as_view(), name='bom_delete'),
]

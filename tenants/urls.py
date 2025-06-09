from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    # HTML Templates
    path('', views.tenant_list, name='tenant_list'),
    path('register/', views.register_tenant, name='register_tenant'),
    path('not-found/', views.tenant_not_found, name='tenant_not_found'),
    path('signup/', views.public_signup, name='public_signup'),
    
    # REST API endpoints - these match the frontend expected patterns
    path('', views.tenant_api_list, name='tenant_api_list'),  # /api/tenants/ - GET list of tenants
    path('create/', views.create_tenant_api, name='create_tenant_api'),  # /api/tenants/create/ - POST create tenant
]


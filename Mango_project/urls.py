"""
URL configuration for Mango_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include 
from django.shortcuts import redirect
from django.conf.urls.static import static
from Accounts.views import generate_sales_invoice_pdf, dashboard, admin_dashboard
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from Accounts import views 
# Import the credit dashboard views
from Accounts.admin import credit_dashboard_view, credit_report_view
# Analytics and forecasting dashboard views (disabled)
# from analytics.admin import analytics_dashboard_view
# from forecasting.admin import forecasting_dashboard_view

def homepage(request):
    """Simple homepage with a redirect to admin"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Star Mango</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 0;
                background-color: #f7f9fc;
                color: #333;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                padding: 30px;
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                text-align: center;
            }
            h1 {
                color: #4CAF50;
                margin-bottom: 20px;
            }
            p {
                margin-bottom: 25px;
                color: #555;
            }
            .btn {
                display: inline-block;
                background: #4CAF50;
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 5px;
                text-decoration: none;
                font-size: 16px;
                transition: background 0.3s ease;
            }
            .btn:hover {
                background: #3e8e41;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to Star Mango</h1>
            <p>Mango Management System</p>
            <a href="/admin/" class="btn">Go to Admin Dashboard</a>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)

# Redirect to admin page
def redirect_to_admin(request):
    return redirect('/admin/')

urlpatterns = [
    path('', homepage, name='home'),  # Root URL shows homepage
    path('admin-redirect/', redirect_to_admin, name='admin-redirect'),  # Redirect to admin
    path('admin/dashboard/', admin_dashboard, name='admin-dashboard'),
    
    # Add credit dashboard URLs before the main admin site
    path('admin/credit-dashboard/', admin.site.admin_view(credit_dashboard_view), name='credit_dashboard'),
    path('admin/credit-report/', admin.site.admin_view(credit_report_view), name='credit_report'),
    # Analytics and forecasting dashboards (disabled)
    # path('admin/analytics-dashboard/', admin.site.admin_view(analytics_dashboard_view), name='analytics_dashboard'),
    # path('admin/forecasting-dashboard/', admin.site.admin_view(forecasting_dashboard_view), name='forecasting_dashboard'),
    
    path('admin/', admin.site.urls),
    path('accounts/', include('Accounts.urls')),
    # path('api/tenants/', include('tenants.urls', namespace='api_tenants')),  # Removed - single tenant
    path('api/', include('Mango_project.api_urls')),  # Include API URLs with Swagger docs
    path('api/accounts/', include('Accounts.urls')),  # Include all Accounts URLs under /api/ as well
    # path('tenants/', include('tenants.urls')),  # Removed - single tenant
    path('sales_invoice/<int:invoice_id>/pdf/', generate_sales_invoice_pdf, name='generate_sales_invoice_pdf'),
]

# Serve media files in production
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve static files in production
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
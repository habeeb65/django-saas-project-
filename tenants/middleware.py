from django.utils.deprecation import MiddlewareMixin
from django_multitenant.utils import set_current_tenant
from django.shortcuts import redirect
from .models import Tenant

class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Skip tenant identification for admin URLs and API endpoints
        if request.path.startswith('/admin/') or request.path.startswith('/api/'):
            return None
            
        tenant = None
        
        # Get tenant from URL path (e.g., /tenant-slug/dashboard/)
        path = request.path.split('/')
        EXEMPT_PATHS = ['accounts', 'static', 'media', 'api', '', 'tenants', 'not-found']
        if len(path) > 1 and path[1]:
            try:
                tenant = Tenant.objects.get(slug=path[1])
                request.tenant = tenant
                set_current_tenant(tenant)
            except Tenant.DoesNotExist:
                # Skip for public URLs and not-found page to prevent redirect loops
                if path[1] not in EXEMPT_PATHS:
                    return redirect('tenants:tenant_not_found')
        
        # Alternative: Get from header (useful for API)
        if not tenant and 'X-Tenant' in request.headers:
            try:
                tenant = Tenant.objects.get(slug=request.headers['X-Tenant'])
                request.tenant = tenant
                set_current_tenant(tenant)
            except Tenant.DoesNotExist:
                pass

        return None
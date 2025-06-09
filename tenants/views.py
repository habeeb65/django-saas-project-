from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import login
from django_multitenant.utils import set_current_tenant
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.text import slugify
import random
import string
import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Tenant, UserProfile, TenantSettings
from .forms import TenantRegistrationForm
from Accounts.models import Product, Customer, PurchaseVendor
from django_tenants.utils import get_tenant_domain_model
from django.core.management import call_command
from django.db import connection

def tenant_not_found(request):
    """View for when a tenant is not found"""
    return render(request, 'tenants/tenant_not_found.html')

def tenant_list(request):
    """Display a list of available tenants"""
    tenants = Tenant.objects.all()
    return render(request, 'tenants/tenant_list.html', {
        'tenants': tenants
    })

def register_tenant(request):
    """Register a new tenant with admin user"""
    if request.method == 'POST':
        form = TenantRegistrationForm(request.POST)
        if form.is_valid():
            # Create tenant
            tenant = Tenant.objects.create(
                name=form.cleaned_data['business_name'],
                slug=form.cleaned_data['slug'],
                business_type=form.cleaned_data['business_type']
            )

            # Create admin user for tenant
            admin_user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
                is_staff=True
            )

            # Create tenant profile to link user to tenant
            UserProfile.objects.create(
                user=admin_user,
                tenant=tenant,
                is_tenant_admin=True
            )

            # Create tenant settings
            TenantSettings.objects.create(tenant=tenant)

            # Create default data based on business type
            setup_default_data(tenant)

            # Log the user in
            login(request, admin_user)

            # Redirect to the new tenant's dashboard
            messages.success(request, f"Your business '{tenant.name}' has been successfully created!")
            return redirect(reverse('dashboard', kwargs={'tenant_slug': tenant.slug}))
    else:
        form = TenantRegistrationForm()

    return render(request, 'tenants/register.html', {'form': form})

def setup_default_data(tenant):
    """Create default data for new tenant based on business type"""
    from django_multitenant.utils import set_current_tenant
    set_current_tenant(tenant)

    # Create default products based on business type
    if tenant.business_type == 'mango':
        products = ['Alphonso', 'Banganapalli', 'Totapuri', 'Kesar']
    elif tenant.business_type == 'vegetable':
        products = ['Tomato', 'Potato', 'Onion', 'Carrot']
    else:  # fruit
        products = ['Apple', 'Banana', 'Orange', 'Grapes']

    for product in products:
        Product.objects.create(tenant=tenant, name=product)

    # Create default customer and vendor
    Customer.objects.create(
        tenant=tenant,
        name="Sample Customer",
        contact_number="1234567890",
        address="Sample Address"
    )

    PurchaseVendor.objects.create(
        tenant=tenant,
        name="Sample Vendor",
        contact_number="9876543210",
        area="Sample Area"
    )

# REST API Endpoints for tenant management
@csrf_exempt
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def tenant_api_list(request):
    """API endpoint to list all tenants and create new tenants"""
    if request.method == 'GET':
        # List all tenants
        tenants = Tenant.objects.all()

        # Convert tenants to a list of dictionaries
        tenant_list = [{
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'business_type': tenant.business_type,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
        } for tenant in tenants]

        # Return list response for GET
        return Response({'results': tenant_list})

    elif request.method == 'POST':
        # Create a new tenant from POST data
        import logging
        import json
        logger = logging.getLogger(__name__)

        # Log the incoming request for debugging
        logger.info(f"Headers: {request.headers}")
        logger.info(f"Body: {request.body}")

        # Parse data from request, supporting different formats
        try:
            if isinstance(request.data, dict):
                data = request.data
            elif hasattr(request, 'body') and request.body:
                data = json.loads(request.body)
            else:
                data = {}

            logger.info(f"Processed data: {data}")

            # Extract name from various possible formats
            tenant_name = data.get('name', '')
            if not tenant_name and 'organizationName' in data:
                tenant_name = data.get('organizationName', '')

            if not tenant_name:
                logger.error("No tenant name provided in request")
                return Response({'error': 'Tenant name is required'}, status=400)

            logger.info(f"Creating tenant with name: {tenant_name}")

            # Create tenant with minimal required fields
            tenant = Tenant.objects.create(
                name=tenant_name,
                slug=tenant_name.lower().replace(' ', '-'),  # Generate slug from name
                business_type='mango'  # Default business type
            )

            # Return tenant data with success status
            response_data = {
                'id': tenant.id,
                'name': tenant.name,
                'slug': tenant.slug,
                'business_type': tenant.business_type,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            }

            logger.info(f"Successfully created tenant: {response_data}")
            return Response(response_data, status=201)

        except json.JSONDecodeError as je:
            logger.error(f"JSON decode error: {str(je)}")
            return Response({'error': 'Invalid JSON format'}, status=400)
        except Exception as e:
            logger.error(f"Error creating tenant: {str(e)}")
            return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([AllowAny])
def create_tenant_api(request):
    """API endpoint to create a new tenant with settings and default data"""
    data = request.data

    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Creating tenant with data: {data}")

        # Generate slug if not provided
        name = data.get('name')
        if not name:
            return Response({'error': 'Tenant name is required'}, status=400)

        slug = data.get('slug')
        if not slug:
            # Generate slug from name - replace spaces with hyphens and make lowercase
            base_slug = slugify(name)
            slug = base_slug
            
            # Check for duplicate slug and generate a unique one if needed
            if Tenant.objects.filter(slug=slug).exists():
                # Add a random 5-character alphanumeric suffix
                suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                slug = f"{base_slug}-{suffix}"
                
                # In the very unlikely case this still exists, keep trying
                while Tenant.objects.filter(slug=slug).exists():
                    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    slug = f"{base_slug}-{suffix}"
                    
                logging.info(f"Generated unique slug: {slug} for tenant: {name}")

        # Create tenant with provided data
        tenant = Tenant.objects.create(
            name=name,
            slug=slug,
            business_type=data.get('business_type', 'mango')
        )

        # Get tenant settings (automatically created by Tenant.save())
        settings_data = data.get('settings', {})
        tenant_settings = tenant.settings
        
        # Update settings with provided data
        if settings_data:
            tenant_settings.enable_purchase_management = settings_data.get('enable_purchase_management', tenant_settings.enable_purchase_management)
            tenant_settings.enable_sales_management = settings_data.get('enable_sales_management', tenant_settings.enable_sales_management)
            tenant_settings.enable_credit_dashboard = settings_data.get('enable_credit_dashboard', tenant_settings.enable_credit_dashboard)
            tenant_settings.enable_analytics = settings_data.get('enable_analytics', tenant_settings.enable_analytics)
            tenant_settings.enable_forecasting = settings_data.get('enable_forecasting', tenant_settings.enable_forecasting)
            tenant_settings.enable_notifications = settings_data.get('enable_notifications', tenant_settings.enable_notifications)
            tenant_settings.enable_mobile_app = settings_data.get('enable_mobile_app', tenant_settings.enable_mobile_app)
            
            # Handle UI customization settings
            if 'primaryColor' in settings_data:
                tenant.primary_color = settings_data['primaryColor']
                tenant.save()
            
            tenant_settings.save()

        # Create default data for the tenant
        setup_default_data(tenant)

        # Handle user creation with the tenant
        # First check if email is directly provided in the request
        email = data.get('email')
        password = data.get('password')
        
        # If not, check in the user data object
        if not email:
            user_data = data.get('user', {})
            email = user_data.get('email')
            password = user_data.get('password')
        
        # If we have email (either direct or in user data), create or link the user
        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Create a username from email if not provided
                username = data.get('username', email.split('@')[0])
                
                # Handle username conflicts
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Create the user with superuser permissions
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password or 'changeme',  # Use provided password or default
                    first_name=data.get('first_name', ''),
                    last_name=data.get('last_name', ''),
                    is_staff=True,     # Allow access to Django admin
                    is_superuser=True  # Grant full superuser permissions
                )

            # Link user to tenant
            UserProfile.objects.create(
                user=user,
                tenant=tenant,
                is_tenant_admin=True
            )

        # Return tenant data with settings
        return Response({
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'business_type': tenant.business_type,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            'primary_color': tenant.primary_color,
            'primaryColor': tenant.primary_color,  # Add this for frontend compatibility
            'settings': {
                'enable_purchase_management': tenant_settings.enable_purchase_management,
                'enable_sales_management': tenant_settings.enable_sales_management,
                'enable_credit_dashboard': tenant_settings.enable_credit_dashboard,
                'enable_analytics': tenant_settings.enable_analytics,
                'enable_forecasting': tenant_settings.enable_forecasting,
                'enable_notifications': tenant_settings.enable_notifications,
                'enable_mobile_app': tenant_settings.enable_mobile_app,
            }
        }, status=201)
    except Exception as e:
        import traceback
        logging.error(f"Error creating tenant: {str(e)}")
        logging.error(traceback.format_exc())
        return Response({'error': str(e)}, status=400)

def public_signup(request):
    """Public-facing signup for new tenants (multi-tenant SaaS)"""
    if request.method == 'POST':
        form = TenantRegistrationForm(request.POST)
        if form.is_valid():
            # 1. Create the tenant
            tenant = Tenant.objects.create(
                name=form.cleaned_data['business_name'],
                slug=form.cleaned_data['slug'],
                business_type=form.cleaned_data['business_type'],
                contact_email=form.cleaned_data['email'],
            )

            # 2. Create the domain
            Domain = get_tenant_domain_model()
            domain = Domain.objects.create(
                domain=form.cleaned_data['domain'],
                tenant=tenant,
                is_primary=True
            )

            # 3. Run migrations for the new tenant schema
            # (Assumes schema_name == slug)
            try:
                call_command('migrate_schemas', schema_name=tenant.slug, interactive=False, verbosity=0)
            except Exception as e:
                tenant.delete()
                form.add_error(None, f"Error running migrations for new tenant: {e}")
                return render(request, 'tenants/signup.html', {'form': form})

            # 4. Create a superuser in the new tenant schema
            # Switch to tenant context
            connection.set_schema(tenant.slug)
            admin_user = User.objects.create_superuser(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            UserProfile.objects.create(
                user=admin_user,
                tenant=tenant,
                is_tenant_admin=True
            )
            TenantSettings.objects.create(tenant=tenant)
            # Optionally, create default data
            setup_default_data(tenant)
            # Switch back to public schema
            connection.set_schema_to_public()

            # 5. Redirect to the new domain's admin
            admin_url = f"http://{domain.domain}:8000/admin/"
            messages.success(request, f"Your business '{tenant.name}' has been created! You can now log in as admin.")
            return redirect(admin_url)
    else:
        form = TenantRegistrationForm()
    return render(request, 'tenants/signup.html', {'form': form})
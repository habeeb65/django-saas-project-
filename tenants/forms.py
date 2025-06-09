from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from .models import Tenant

class TenantRegistrationForm(forms.Form):
    business_name = forms.CharField(max_length=100, required=True,
                                   help_text="Name of your business")
    
    slug = forms.SlugField(max_length=50, required=True,
                          help_text="Used in your URL: yourdomain.com/slug/",
                          validators=[RegexValidator(r'^[a-z0-9-]+$', 
                                     'Only lowercase letters, numbers, and hyphens are allowed.')])
    
    business_type = forms.ChoiceField(choices=[
        ('mango', 'Mango Wholesaler'),
        ('vegetable', 'Vegetable Wholesaler'),
        ('fruit', 'Mixed Fruit Wholesaler'),
    ], required=True)
    
    # Admin user details
    username = forms.CharField(max_length=30, required=True,
                              help_text="Username for the admin account")
    
    email = forms.EmailField(required=True,
                            help_text="Email address for the admin account")
    
    password = forms.CharField(widget=forms.PasswordInput(), required=True,
                              help_text="Password for the admin account")
    
    confirm_password = forms.CharField(widget=forms.PasswordInput(), required=True,
                                     help_text="Confirm your password")
    
    domain = forms.CharField(
        max_length=255,
        required=True,
        help_text="Domain for your business (e.g. mango1.localhost or 127.0.0.1)",
    )
    
    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("This URL slug is already in use. Please choose another.")
        return slug
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered. Please use another.")
        return email
    
    def clean_domain(self):
        domain = self.cleaned_data.get('domain')
        try:
            from django_tenants.utils import get_tenant_domain_model
            Domain = get_tenant_domain_model()
        except ImportError:
            raise forms.ValidationError("Domain model not found. Is django-tenants installed?")
        if Domain.objects.filter(domain=domain).exists():
            raise forms.ValidationError("This domain is already in use. Please choose another.")
        return domain
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords don't match")
            
        return cleaned_data 
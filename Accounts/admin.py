from django.contrib import admin
from .models import Purchase, PurchaseVendor, PurchaseInvoice, Product, PurchaseProduct, Payment
from .models import SalesInvoice, SalesProduct, SalesPayment, Customer, Product, Expense, Damages, SalesLot, Packaging_Invoice
from django.shortcuts import redirect, render  # Add render
from django.urls import reverse
from django.urls import path, re_path
from django.utils.html import format_html
from django.http import JsonResponse
from django.db import models
from django.http import HttpResponse
from django.contrib.admin import SimpleListFilter
from django.db.models import Sum, Count, F, DecimalField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django import forms
from django.contrib.admin.views.main import ChangeList
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models import Q
from django.db.models.functions import ExtractMonth
import requests
from django.contrib import messages
import csv
from django.utils.encoding import smart_str
import io
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, DateWidget
from import_export.admin import ImportExportModelAdmin
from import_export.results import RowResult

# Import our CSV import/export functionality
from .admin_csv import SalesInvoiceCSVMixin, PurchaseInvoiceCSVMixin

admin.site.site_header = "Star Mango Supplies Korutla"   # Header displayed at the top of the admin
admin.site.site_title = "Star Mango Supplies Korutla"     # Title tag for the admin pages
admin.site.index_title = "Welcome to Star Mango Supplies Korutla Admin Panel"  # Title on the admin index page
# Inline for PurchaseProduct within an Invoice
class PurchaseProductInline(admin.TabularInline):
    model = PurchaseProduct
    extra = 1  # Number of empty forms to show initially
    readonly_fields = ('total', 'loading_unloading', 'serial_number')  # Make calculated fields read-only
    fields = ('serial_number', 'product', 'quantity', 'price', 'damage', 'discount', 'rotten', 'loading_unloading', 'total')
    ordering = ('serial_number',)  # Order products by serial number

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset

    def serial_number(self, obj):
        if obj.pk:
            return obj.serial_number
        else:
            # Predict the next serial number for new items
            if hasattr(obj, 'invoice') and obj.invoice and obj.invoice.pk:
                existing_products = PurchaseProduct.objects.filter(invoice=obj.invoice)
                if existing_products.exists():
                    max_serial = existing_products.aggregate(models.Max('serial_number'))['serial_number__max'] or 0
                    return max_serial + 1
                return 1  # First product for this invoice
        return "-"  # Fallback if we can't predict
    serial_number.short_description = "Serial Number"

# Inline for Payments within an Invoice
class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1  # Number of empty forms to show
    fields = ('amount','payment_mode','attachment', 'date')
    readonly_fields = ('date',)  # Optionally make date read-only

class PurchaseInvoiceResource(resources.ModelResource):
    # Define fields with explicit column mappings matching the actual CSV headers
    id = fields.Field(column_name='id', attribute='id')
    invoice_number = fields.Field(column_name='invoice_number', attribute='invoice_number')
    lot_number = fields.Field(column_name='lot_number', attribute='lot_number')
    date = fields.Field(
        column_name='date',
        attribute='date',
        widget=DateWidget(format='%Y-%m-%d')
    )
    net_total = fields.Field(column_name='net_total', attribute='net_total')
    
    # Handle vendor mapping - the CSV uses vendor_id as integer
    vendor = fields.Field(column_name='vendor_id', attribute='vendor', widget=ForeignKeyWidget(PurchaseVendor, 'id'))
    
    class Meta:
        model = PurchaseInvoice
        import_id_fields = ('id',)
        skip_unchanged = True
        report_skipped = True
        fields = ('id', 'invoice_number', 'lot_number', 'date', 'net_total', 'vendor')
        export_order = fields
    
    def before_import_row(self, row, **kwargs):
        """Process each row before import"""
        # Print the row for debugging
        print(f"IMPORT ROW: {row}")
        
        # If vendor_id is not found or is empty, try using payment_issuer_name to find a vendor
        if ('vendor_id' not in row or not row['vendor_id']) and 'payment_issuer_name' in row and row['payment_issuer_name']:
            vendor_name = row['payment_issuer_name']
            # Try to find vendor by name
            vendor = PurchaseVendor.objects.filter(name=vendor_name).first()
            if vendor:
                row['vendor_id'] = vendor.id
                print(f"Found vendor by name: {vendor_name}, ID: {vendor.id}")
            else:
                # Create a new vendor with this name
                try:
                    new_vendor = PurchaseVendor.objects.create(name=vendor_name)
                    row['vendor_id'] = new_vendor.id
                    print(f"Created new vendor: {vendor_name}, ID: {new_vendor.id}")
                except Exception as e:
                    print(f"Error creating vendor: {e}")
        
        # Check if vendor_id exists but vendor doesn't
        if 'vendor_id' in row and row['vendor_id']:
            vendor_id = row['vendor_id']
            try:
                # Try to get the vendor by ID
                PurchaseVendor.objects.get(id=vendor_id)
                print(f"Found vendor with ID: {vendor_id}")
            except PurchaseVendor.DoesNotExist:
                # Vendor doesn't exist, create a new one with the ID and payment_issuer_name
                payment_issuer_name = row.get('payment_issuer_name', f"Vendor {vendor_id}")
                try:
                    # Use a raw SQL query to create a vendor with a specific ID
                    from django.db import connection
                    cursor = connection.cursor()
                    cursor.execute(
                        "INSERT INTO Accounts_purchasevendor (id, name, contact_number, area) VALUES (%s, %s, %s, %s)",
                        [vendor_id, payment_issuer_name, "", ""]
                    )
                    print(f"Created new vendor with ID {vendor_id} and name '{payment_issuer_name}'")
                except Exception as e:
                    print(f"Error creating vendor with ID {vendor_id}: {e}")
        
        # Add default values for required fields if missing
        if 'date' not in row or not row['date']:
            row['date'] = timezone.now().strftime('%Y-%m-%d')
            
        if 'lot_number' not in row or not row['lot_number']:
            # Generate a lot number based on invoice number if missing
            if 'invoice_number' in row and row['invoice_number']:
                invoice_num = row['invoice_number']
                if invoice_num.startswith('MS') and len(invoice_num) >= 8:
                    row['lot_number'] = f"LOT-{invoice_num[6:8]}" 
                else:
                    row['lot_number'] = f"LOT-{invoice_num[-2:]}"
        
        print(f"PROCESSED ROW: {row}")
        return row
    
    def skip_row(self, instance, original, row, import_validation_errors=None):
        """Skip rows with critical missing data"""
        # Skip if no invoice number
        if not instance.invoice_number:
            return True
            
        # Skip if no vendor and can't find/create one
        if not hasattr(instance, 'vendor') or not instance.vendor:
            return True
            
        return super().skip_row(instance, original, row, import_validation_errors)

# Admin for PurchaseInvoice
class PurchaseInvoiceAdmin(PurchaseInvoiceCSVMixin, ImportExportModelAdmin):
    resource_class = PurchaseInvoiceResource
    model = PurchaseInvoice
    list_display = ('invoice_number','lot_number', 'vendor_name', 'net_total_after_cash_cutting', 'paid_amount', 'due_amount_display', 'payment_status', 'date', 'print_invoice')
    readonly_fields = ('invoice_number', 'lot_number','net_total', 'net_total_after_cash_cutting', 'paid_amount_display', 'due_amount_display', 'payment_status')
    search_fields = ('invoice_number','lot_number', 'vendor__name')
    list_filter = ('date', 'vendor')
    autocomplete_fields = ['vendor']
    actions = ['export_as_csv']

    # Removing Media class to stop loading JavaScript
    # class Media:
    #     js = ('admin/js/purchase_calculation.js',)

    # Remove the static inlines list and replace with get_inlines method
    def get_inlines(self, request, obj=None):
        # Always show both product and payment inlines
        return [PurchaseProductInline, PaymentInline]

    def vendor_name(self, obj):
        return obj.vendor.name if obj.vendor else "-"
    vendor_name.short_description = "Vendor"

    def net_total_display(self, obj):
        return f"₹{obj.net_total:.2f}"
    net_total_display.short_description = "Net Total"

    def paid_amount_display(self, obj):
        payments = obj.payments.all()
        details = "<br/>".join([f"₹{payment.amount} on {payment.date}" for payment in payments])
        total_paid = f"<b>Total Paid:</b> ₹{obj.paid_amount:.2f}"
        return format_html(f"{details}<br/>{total_paid}")
    paid_amount_display.short_description = "Paid Amount"

    def due_amount_display(self, obj):
        return format_html(f"<b style='color: #dc3545;'>₹{obj.due_amount:.2f}</b>")
    due_amount_display.short_description = "Due Amount"

    def payment_status(self, obj):
        if obj.due_amount == 0:
            status = "Paid"
        elif obj.paid_amount == 0:
            status = "Unpaid"
        else:
            status = "Partial"

        colors = {
            'Paid': '#28a745',
            'Unpaid': '#dc3545',
            'Partial': '#ffc107'
        }
        return format_html(f"<b style='color: {colors.get(status, '#000')};'>{status}</b>")
    payment_status.short_description = "Payment Status"

    def print_invoice(self, obj):
        url = reverse('generate_invoice_pdf', args=[obj.id])
        return format_html('<a class="button" href="{}" target="_blank">Print Invoice</a>', url)
    print_invoice.short_description = "Print Invoice"

    def save_model(self, request, obj, form, change):
        """Override save_model to ensure calculations are performed properly"""
        super().save_model(request, obj, form, change)
        # After saving, update the net_total once more to ensure it's correct
        if obj.pk:
            calculated_total = sum(product.total for product in obj.purchase_products.all())
            if obj.net_total != calculated_total:
                # Use update to avoid triggering another full save
                PurchaseInvoice.objects.filter(pk=obj.pk).update(net_total=calculated_total)

    def save_formset(self, request, form, formset, change):
        """Override save_formset to ensure all formsets are saved"""
        # Always save all formsets, whether creating new or editing
        super().save_formset(request, form, formset, change)
        # After saving formsets, make sure the parent object's calculations are updated
        obj = form.instance
        if obj.pk:
            calculated_total = sum(product.total for product in obj.purchase_products.all())
            if obj.net_total != calculated_total:
                # Use update to avoid triggering another full save
                PurchaseInvoice.objects.filter(pk=obj.pk).update(net_total=calculated_total)

    def response_change(self, request, obj):
        if "_print_without_payments" in request.POST:
            url = reverse('generate_invoice_pdf', args=[obj.id]) + "?hide_payments=1"
            return redirect(url)
        return super().response_change(request, obj)

    def get_urls(self):
        from django.urls import path, re_path
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            re_path(r'^import-csv/$', self.admin_site.admin_view(self.import_csv), name='%s_%s_import_csv' % info),
            path('autocomplete/', self.admin_site.admin_view(self.autocomplete)),
        ]
        return custom_urls + urls

    def autocomplete(self, request):
        query = request.GET.get('q', '')
        lots = PurchaseInvoice.objects.filter(lot_number__icontains=query)[:10]
        results = []
        for lot in lots:
            products = lot.get_product_quantities()
            product_info = ", ".join([f"{k}: {v}" for k, v in products.items()])
            results.append({
                'id': lot.id,
                'text': f"{lot.lot_number} - Available: {product_info}",
            })
        return JsonResponse({'results': results})

    def export_as_csv(self, request, queryset):
        """Export selected invoices as CSV"""
        if not queryset:
            self.message_user(request, "No invoices selected for export", level=messages.WARNING)
            return None
            
        response = HttpResponse(content_type='text/csv')
        filename = f"purchase_invoices_{timezone.now().strftime('%Y-%m-%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        # Write header row
        writer.writerow([
            'Invoice Number', 
            'Lot Number',
            'Vendor',
            'Date',
            'Net Total',
            'Paid Amount',
            'Due Amount'
        ])
        
        # Write data rows
        for invoice in queryset:
            writer.writerow([
                invoice.invoice_number,
                invoice.lot_number,
                invoice.vendor.name,
                invoice.date.strftime('%Y-%m-%d'),
                invoice.net_total,
                invoice.paid_amount,
                invoice.due_amount
            ])
        
        self.message_user(request, f"Successfully exported {queryset.count()} invoices")
        return response
    export_as_csv.short_description = "Export selected invoices as CSV"
    
    def import_csv(self, request):
        """Import invoices from CSV file"""
        if request.method == 'POST' and request.FILES.get('csv_file'):
            csv_file = request.FILES['csv_file']
            
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File is not a CSV')
                return redirect('..')
                
            # Process CSV file
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string)
            
            # Skip header row
            next(reader, None)
            
            success_count = 0
            error_count = 0
            error_messages = []
            
            for row in reader:
                try:
                    if len(row) < 5:  # Check minimum number of required fields
                        raise ValidationError("Row has insufficient data")
                        
                    invoice_number = row[0]
                    lot_number = row[1]
                    vendor_name = row[2]
                    date_str = row[3]
                    net_total = float(row[4])
                    
                    # Get or create vendor
                    vendor, created = PurchaseVendor.objects.get_or_create(name=vendor_name)
                    
                    # Check if invoice already exists
                    if PurchaseInvoice.objects.filter(invoice_number=invoice_number).exists():
                        # Update existing invoice
                        invoice = PurchaseInvoice.objects.get(invoice_number=invoice_number)
                        invoice.lot_number = lot_number
                        invoice.vendor = vendor
                        invoice.date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                        invoice.net_total = net_total
                        invoice.save()
                    else:
                        # Create new invoice
                        invoice = PurchaseInvoice.objects.create(
                            invoice_number=invoice_number,
                            lot_number=lot_number,
                            vendor=vendor,
                            date=timezone.datetime.strptime(date_str, '%Y-%m-%d').date(),
                            net_total=net_total
                        )
                    
                    # Process payments if provided
                    if len(row) > 5 and row[5]:
                        paid_amount = float(row[5])
                        if paid_amount > 0:
                            Payment.objects.create(
                                invoice=invoice,
                                amount=paid_amount,
                                date=timezone.now()
                            )
                            
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    error_messages.append(f"Error in row {error_count + success_count}: {str(e)}")
            
            # Show results
            if success_count:
                messages.success(request, f"Successfully imported {success_count} invoices.")
            if error_count:
                messages.error(request, f"Failed to import {error_count} invoices. See details below.")
                for msg in error_messages[:10]:  # Show first 10 errors
                    messages.error(request, msg)
                if len(error_messages) > 10:
                    messages.error(request, f"... and {len(error_messages) - 10} more errors.")
                    
            return redirect('..')
            
        # If GET request, show upload form
        return render(request, 'admin/import_csv.html', {
            'title': 'Import Purchase Invoices from CSV',
            'site_title': 'Star Mango Admin',
            'site_header': 'Star Mango Admin',
            'opts': PurchaseInvoice._meta,
            'has_permission': True,
        })

    change_list_template = 'admin/custom_change_list.html'
    
    def changelist_view(self, request, extra_context=None):
        """Add import button to changelist view"""
        extra_context = extra_context or {}
        info = self.model._meta.app_label, self.model._meta.model_name
        extra_context['import_url'] = reverse('admin:%s_%s_import_csv' % info)
        extra_context['title'] = 'Purchase Invoices'
        extra_context['has_import_permission'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def has_import_permission(self, request):
        """Ensure the Import CSV button is visible"""
        return True

    class Meta:
        verbose_name = "Purchase Invoice"
        verbose_name_plural = "Purchase Invoices"
# Admin for PurchaseProduct
class PurchaseProductAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'invoice', 'product', 'quantity', 'price_display', 'total', 'damage', 'discount', 'rotten')
    readonly_fields = ('total', 'serial_number')  # Make calculated fields read-only
    ordering = ('invoice', 'serial_number')  # Order by invoice then serial number

    def price_display(self, obj):
        return f"₹{obj.price:.2f}"
    price_display.short_description = "Price"

# Admin for Payment
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount_display', 'date')

    def amount_display(self, obj):
        return f"₹{obj.amount:.2f}"
    amount_display.short_description = "Amount"

class SalesProductInline(admin.TabularInline):
    model = SalesProduct
    extra = 1  # Number of empty forms to show initially
    readonly_fields = ('total', 'net_weight', 'serial_number')
    fields = ('serial_number', 'product', 'gross_weight', 'discount', 'rotten', 'net_weight', 'price', 'total')
    ordering = ('serial_number',)  # Order products by serial number

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset

    def serial_number(self, obj):
        if obj.pk:
            return obj.serial_number
        else:
            # Predict the next serial number for new items
            if hasattr(obj, 'invoice') and obj.invoice and obj.invoice.pk:
                existing_products = SalesProduct.objects.filter(invoice=obj.invoice)
                if existing_products.exists():
                    max_serial = existing_products.aggregate(models.Max('serial_number'))['serial_number__max'] or 0
                    return max_serial + 1
                return 1  # First product for this invoice
        return "-"  # Fallback if we can't predict
    serial_number.short_description = "S/No"

# Inline for SalesPayment within a Sales Invoice
class SalesPaymentInline(admin.TabularInline):
    model = SalesPayment
    extra = 1  # Number of empty forms to show
    fields = ('amount', 'payment_mode', 'attachment', 'date')
    readonly_fields = ('date',)
class SalesLotInline(admin.TabularInline):
    model = SalesLot
    extra = 1
    autocomplete_fields = ['purchase_invoice']

# Custom filter for Customer credit status
class CreditStatusFilter(SimpleListFilter):
    title = 'Credit Status'
    parameter_name = 'credit_status_filter'

    def lookups(self, request, model_admin):
        return (
            ('over_limit', 'Over Limit'),
            ('near_limit', 'Near Limit'),
            ('within_limit', 'Within Limit'),
            ('no_limit', 'No Limit Set'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'over_limit':
            # Find customers where their total_due > credit_limit (and credit_limit > 0)
            over_limit_customers = []
            for customer in queryset.filter(credit_limit__gt=0):
                if customer.total_due > customer.credit_limit:
                    over_limit_customers.append(customer.id)
            return queryset.filter(id__in=over_limit_customers)
            
        elif self.value() == 'near_limit':
            # Find customers where total_due is 80-100% of credit_limit
            near_limit_customers = []
            for customer in queryset.filter(credit_limit__gt=0):
                if customer.total_due >= (customer.credit_limit * 0.8) and customer.total_due <= customer.credit_limit:
                    near_limit_customers.append(customer.id)
            return queryset.filter(id__in=near_limit_customers)
            
        elif self.value() == 'within_limit':
            # Find customers where total_due < 80% of credit_limit
            within_limit_customers = []
            for customer in queryset.filter(credit_limit__gt=0):
                if customer.total_due < (customer.credit_limit * 0.8):
                    within_limit_customers.append(customer.id)
            return queryset.filter(id__in=within_limit_customers)
            
        elif self.value() == 'no_limit':
            # Customers with no specific credit limit (0 or null)
            return queryset.filter(credit_limit=0)
            
        return queryset

class SalesInvoiceResource(resources.ModelResource):
    # Define fields with explicit column mappings matching the actual CSV headers
    invoice_number = fields.Field(column_name='invoice_number', attribute='invoice_number')
    invoice_date = fields.Field(
        column_name='invoice_date', 
        attribute='invoice_date',
        widget=DateWidget(format='%Y-%m-%d')
    )
    # Lookup Customer by ID
    customer = fields.Field(
        column_name='customer_id', 
        attribute='customer',
        widget=ForeignKeyWidget(Customer, 'id')
    )
    vehicle_number = fields.Field(column_name='vehicle_number', attribute='vehicle_number')
    gross_vehicle_weight = fields.Field(column_name='gross_vehicle_weight', attribute='gross_vehicle_weight')
    reference = fields.Field(column_name='reference', attribute='reference')
    
    class Meta:
        model = SalesInvoice
        import_id_fields = ('invoice_number',)
        skip_unchanged = True
        report_skipped = True
        fields = ('invoice_number', 'invoice_date', 'customer', 'vehicle_number', 
                 'gross_vehicle_weight', 'reference')
        export_order = fields
    
    def before_import_row(self, row, **kwargs):
        """Process each row before import"""
        # Print the row for debugging
        print(f"IMPORT ROW (Sales): {row}")
        
        # Set default date if missing
        if 'invoice_date' not in row or not row['invoice_date']:
            row['invoice_date'] = timezone.now().strftime('%Y-%m-%d')
            
        # Handle customer lookup/creation
        if 'customer_name' in row and row['customer_name'] and ('customer_id' not in row or not row['customer_id']):
            # Try to find customer by name
            customer = Customer.objects.filter(name__iexact=row['customer_name']).first()
            if customer:
                row['customer_id'] = customer.id
                print(f"Found customer by name: {row['customer_name']}, ID: {customer.id}")
            else:
                try:
                    # Create a new customer with basic info
                    new_customer = Customer.objects.create(
                        name=row['customer_name'],
                        business_name=row.get('business_name', row['customer_name']),
                        phone=row.get('phone', ''),
                        email=row.get('email', '')
                    )
                    row['customer_id'] = new_customer.id
                    print(f"Created new customer: {row['customer_name']}, ID: {new_customer.id}")
                except Exception as e:
                    print(f"Error creating customer: {e}")
        
        # Create default reference if missing
        if 'reference' not in row or not row['reference']:
            if 'invoice_number' in row and row['invoice_number']:
                row['reference'] = f"Ref-{row['invoice_number']}"
                
        print(f"PROCESSED ROW (Sales): {row}")
        return row
        
    def skip_row(self, instance, original, row, import_validation_errors=None):
        """Skip rows with critical missing data"""
        # Skip if no invoice number
        if not instance.invoice_number:
            return True
            
        # Skip if no customer and can't find/create one
        if not hasattr(instance, 'customer') or not instance.customer:
            return True
            
        return super().skip_row(instance, original, row, import_validation_errors)
        
    def after_import_row(self, row, row_result, **kwargs):
        """Process sales products after the invoice is created"""
        if not row_result.import_type == RowResult.IMPORT_TYPE_NEW:
            return
            
        try:
            # Get the newly created invoice
            invoice = SalesInvoice.objects.get(invoice_number=row['invoice_number'])
            
            # Check if the CSV contains product information
            if all(key in row for key in ['product_id', 'quantity', 'unit_price']):
                # Create a SalesProduct entry
                product = Product.objects.get(id=row['product_id'])
                SalesProduct.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=row['quantity'],
                    unit_price=row['unit_price'],
                    discount=row.get('discount', 0)
                )
                print(f"Added product {product.name} to invoice {invoice.invoice_number}")
        except Exception as e:
            print(f"Error processing products for invoice: {e}")
            # Don't fail the import for product errors

# Admin for SalesInvoice
class SalesInvoiceAdmin(SalesInvoiceCSVMixin, ImportExportModelAdmin):
    resource_class = SalesInvoiceResource
    list_display = (
        'invoice_number',
        'vendor_name',
        'net_total_after_commission',
        'packaging_total_display',
        'purchased_crates_total_display',
        'net_total_after_packaging',
        'paid_amount_display',
        'due_amount_display',
        'payment_status',
        'invoice_date',
        'print_invoice'
    )
    readonly_fields = (
        'invoice_number',
        'net_total',
        'net_total_after_commission',
        'packaging_total',
        'purchased_crates_total',
        'net_total_after_packaging',
        'paid_amount',
        'due_amount',
        'payment_status'
    )
    actions = ['export_as_csv']

    # Simple procedural fields layout rearranged
    fields = [
        # Basic information
        'vendor', 'invoice_date', 'vehicle_number', 'gross_vehicle_weight', 'reference',

        # Outgoing Crates
        'no_of_crates', 'cost_per_crate',

        # Incoming Crates
        'purchased_crates_quantity', 'purchased_crates_unit_price',
        'purchased_crates_total', # Read-only calculated field

        # Sales, Commission & Packaging Cost
        'invoice_number', # Read-only
        'net_total', # Read-only
        'net_total_after_commission', # Read-only
        'packaging_total', # Read-only (Total packaging cost)

        # Final Totals & Payments
        'net_total_after_packaging', # Read-only
        'paid_amount', # Read-only
        'due_amount', # Read-only
        'payment_status' # Read-only
    ]

    def get_inlines(self, request, obj=None):        
        return [SalesLotInline, SalesProductInline, SalesPaymentInline]  # Show all inlines for new

    search_fields = ('invoice_number', 'vendor__name', )
    list_filter = ('invoice_date',)

    def vendor_name(self, obj):
        return obj.vendor.name if obj.vendor else "-"
    vendor_name.short_description = "Customer"

    def paid_amount_display(self, obj):
        payments = obj.payments.all()
        details = "<br/>".join([f"₹{payment.amount} on {payment.date}" for payment in payments])
        total_paid = f"<b>Total Paid:</b> ₹{obj.paid_amount:.2f}"
        return format_html(f"{details}<br/>{total_paid}")
    paid_amount_display.short_description = "Paid Amount"

    def due_amount_display(self, obj):
        return format_html(f"<b style='color: #dc3545;'>₹{obj.due_amount:.2f}</b>")
    due_amount_display.short_description = "Due Amount"

    def payment_status(self, obj):
        status = obj.payment_status()
        colors = {
            'Paid': '#28a745',
            'Unpaid': '#dc3545',
            'Partial': '#ffc107'
        }
        return format_html(f"<b style='color: {colors.get(status, '#000')};'>{status}</b>")
    payment_status.short_description = "Payment Status"

    def print_invoice(self, obj):
        url = reverse('generate_sales_invoice_pdf', args=[obj.id])
        return format_html('<a class="button" href="{}" target="_blank">Print Invoice</a>', url)
    print_invoice.short_description = "Print Invoice"

    def save_formset(self, request, form, formset, change):
        if change and not getattr(formset.instance, 'pk', None):
            if hasattr(formset.instance, 'sales_invoice'):
                # If this is a nested inline (formset inside another formset)
                # and we are *editing*, do nothing. This prevents validation.
                pass
        else:
            # If creating a new invoice (change=False), save all formsets as usual.
            super().save_formset(request, form, formset, change)

    def response_change(self, request, obj):
        if "_print_without_payments" in request.POST:
            url = reverse('generate_sales_invoice_pdf', args=[obj.id]) + "?hide_payments=1"
            return redirect(url)
        return super().response_change(request, obj)

    def change_form(self, request, obj=None, **kwargs):
        if obj:
            self.fieldsets = list(self.fieldsets)
            self.fieldsets.append((
                'Print Options',
                {'fields': [], 'description': '''
                    <a class="button" href="{}" target="_blank">Print With Payments</a>&nbsp;
                    <a class="button" href="{}?hide_payments=1" target="_blank">Print Without Payments</a>
                '''.format(
                    reverse('generate_sales_invoice_pdf', args=[obj.id]),
                    reverse('generate_sales_invoice_pdf', args=[obj.id])
                )}
            ))
        return super().change_form(request, obj, **kwargs)

    def packaging_total_display(self, obj):
        return f"₹{obj.packaging_total:.2f}"
    packaging_total_display.short_description = "Total packaging cost"

    def purchased_crates_total_display(self, obj):
        return f"₹{obj.purchased_crates_total:.2f}"
    purchased_crates_total_display.short_description = "Purchased crates total"

    def export_as_csv(self, request, queryset):
        """Export selected invoices as CSV"""
        if not queryset:
            self.message_user(request, "No invoices selected for export", level=messages.WARNING)
            return None
            
        response = HttpResponse(content_type='text/csv')
        filename = f"sales_invoices_{timezone.now().strftime('%Y-%m-%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        # Write header row
        writer.writerow([
            'Invoice Number', 
            'Customer',
            'Date',
            'Net Total',
            'Packaging Total',
            'Purchased Crates Total',
            'Net Total After Packaging',
            'Paid Amount',
            'Due Amount'
        ])
        
        # Write data rows
        for invoice in queryset:
            writer.writerow([
                invoice.invoice_number,
                invoice.vendor.name,
                invoice.invoice_date.strftime('%Y-%m-%d'),
                invoice.net_total_after_commission,
                invoice.packaging_total,
                invoice.purchased_crates_total,
                invoice.net_total_after_packaging,
                invoice.paid_amount,
                invoice.due_amount
            ])
            
        self.message_user(request, f"Successfully exported {queryset.count()} invoices")
        return response
    export_as_csv.short_description = "Export selected invoices as CSV"
    
    def get_urls(self):
        from django.urls import path, re_path
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            re_path(r'^import-csv/$', self.admin_site.admin_view(self.import_csv), name='%s_%s_import_csv' % info),
        ]
        return custom_urls + urls

    def import_csv(self, request):
        """Import invoices from CSV file"""
        if request.method == 'POST' and request.FILES.get('csv_file'):
            csv_file = request.FILES['csv_file']
            
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'File is not a CSV')
                return redirect('..')
                
            # Process CSV file
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string)
            
            # Skip header row
            next(reader, None)
            
            success_count = 0
            error_count = 0
            error_messages = []
            
            for row in reader:
                try:
                    if len(row) < 5:  # Check minimum number of required fields
                        raise ValidationError("Row has insufficient data")
                        
                    invoice_number = row[0]
                    customer_name = row[1]
                    date_str = row[2]
                    net_total = float(row[3])
                    
                    # Get or create customer
                    customer, created = Customer.objects.get_or_create(name=customer_name)
                    
                    # Check if invoice already exists
                    if SalesInvoice.objects.filter(invoice_number=invoice_number).exists():
                        # Update existing invoice
                        invoice = SalesInvoice.objects.get(invoice_number=invoice_number)
                        invoice.vendor = customer
                        invoice.invoice_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                        invoice.save()
                    else:
                        # Create new invoice with minimal data
                        invoice = SalesInvoice.objects.create(
                            invoice_number=invoice_number,
                            vendor=customer,
                            invoice_date=timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                        )
                    
                    # Process payments if provided
                    if len(row) > 7 and row[7]:
                        paid_amount = float(row[7])
                        if paid_amount > 0:
                            SalesPayment.objects.create(
                                invoice=invoice,
                                amount=paid_amount,
                                date=timezone.now()
                            )
                            
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    error_messages.append(f"Error in row {error_count + success_count}: {str(e)}")
            
            # Show results
            if success_count:
                messages.success(request, f"Successfully imported {success_count} invoices.")
            if error_count:
                messages.error(request, f"Failed to import {error_count} invoices. See details below.")
                for msg in error_messages[:10]:  # Show first 10 errors
                    messages.error(request, msg)
                if len(error_messages) > 10:
                    messages.error(request, f"... and {len(error_messages) - 10} more errors.")
                    
            return redirect('..')
            
        # If GET request, show upload form
        return render(request, 'admin/import_csv.html', {
            'title': 'Import Sales Invoices from CSV',
            'site_title': 'Star Mango Admin',
            'site_header': 'Star Mango Admin',
            'opts': SalesInvoice._meta,
            'has_permission': True,
        })

    change_list_template = 'admin/custom_change_list.html'
    
    def changelist_view(self, request, extra_context=None):
        """Add import button to changelist view"""
        extra_context = extra_context or {}
        info = self.model._meta.app_label, self.model._meta.model_name
        extra_context['import_url'] = reverse('admin:%s_%s_import_csv' % info)
        extra_context['title'] = 'Sales Invoices'
        extra_context['has_import_permission'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def has_import_permission(self, request):
        """Ensure the Import CSV button is visible"""
        return True

# Admin for SalesProduct
class SalesProductAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'invoice', 'product', 'gross_weight', 'discount', 'rotten', 'net_weight', 'price', 'total')
    readonly_fields = ('total', 'net_weight', 'serial_number')
    ordering = ('invoice', 'serial_number')  # Order by invoice then serial number

    def serial_number(self, obj):
        return obj.serial_number
    serial_number.short_description = "S/No"

# Admin for SalesPayment
class SalesPaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'date', 'payment_mode')
    list_filter = ('date', 'payment_mode')

# Form for bulk updating credit limits
class BulkCreditLimitForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.HiddenInput)
    credit_limit = forms.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="New credit limit to apply to all selected customers"
    )

class CustomerResource(resources.ModelResource):
    class Meta:
        model = Customer
        fields = ('id', 'name', 'contact_number', 'address', 'credit_limit')
        import_id_fields = ('name',)
        skip_unchanged = True
        report_skipped = True

# Optionally, register Customer and Product if not already registered
class CustomerAdmin(ImportExportModelAdmin):
    resource_class = CustomerResource
    list_display = ('name', 'contact_number', 'address', 'credit_limit', 'total_due', 'credit_status', 'view_invoices')
    search_fields = ('name', 'contact_number')
    list_filter = (CreditStatusFilter,)
    list_editable = ('credit_limit',)
    actions = ['update_credit_limit', 'send_credit_status_notification']
    list_per_page = 50
    
    def get_ordering(self, request):
        if request.GET.get('sort_by_due'):
            # This is a UI-triggered sort by total_due
            customers = Customer.objects.all()
            # Sort the queryset by total_due in memory
            sorted_customers = sorted(customers, key=lambda x: x.total_due, reverse=True)
            # Extract the IDs in order
            customer_ids = [customer.id for customer in sorted_customers]
            # Build case when ordering
            when_list = []
            for pos, id in enumerate(customer_ids):
                when_list.append(f"WHEN id={id} THEN {pos}")
            
            if when_list:
                ordering = [models.expressions.RawSQL(
                    f"CASE {' '.join(when_list)} ELSE 9999 END", 
                    []
                )]
                return ordering
        return ['name']  # Default ordering by name
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['sort_options'] = [
            {'label': 'Sort by Name (Default)', 'url': '.'},
            {'label': 'Sort by Total Due', 'url': f"{request.path}?sort_by_due=1"}
        ]
        return super().changelist_view(request, extra_context=extra_context)
    
    def credit_status(self, obj):
        status = obj.credit_status
        if status == "Over Limit":
            return format_html('<span style="color: red; font-weight: bold;">⚠️ {}</span>', status)
        elif status == "Near Limit":
            return format_html('<span style="color: orange; font-weight: bold;">⚠️ {}</span>', status)
        else:
            return format_html('<span style="color: green;">{}</span>', status)
    credit_status.short_description = "Credit Status"
    
    def total_due(self, obj):
        # Fix the formatting issue - stringify the value first
        return format_html('₹{}', '{:.2f}'.format(float(obj.total_due)))
    total_due.short_description = "Total Due"
    
    def view_invoices(self, obj):
        url = reverse('admin:Accounts_salesinvoice_changelist') + f'?vendor__id__exact={obj.id}'
        return format_html('<a href="{}">View Invoices</a>', url)
    view_invoices.short_description = "Invoices"
    
    def update_credit_limit(self, request, queryset):
        """Admin action to bulk update credit limits"""
        if 'apply' in request.POST:
            # Process the form
            form = BulkCreditLimitForm(request.POST)
            if form.is_valid():
                credit_limit = form.cleaned_data['credit_limit']
                count = 0
                for customer in queryset:
                    customer.credit_limit = credit_limit
                    customer.save()
                    count += 1
                self.message_user(request, f'Updated credit limit for {count} customers to ₹{credit_limit}')
                return
        else:
            # Display the form
            form = BulkCreditLimitForm(initial={'_selected_action': request.POST.getlist(admin.ACTION_CHECKBOX_NAME)})
        
        context = {
            'customers': queryset,
            'form': form,
            'title': 'Update Credit Limit',
            'action': 'update_credit_limit'
        }
        return render(request, 'admin/update_credit_limit.html', context)
    update_credit_limit.short_description = "Update credit limit for selected customers"

    def send_credit_status_notification(self, request, queryset):
        """Send WhatsApp notifications to customers about their credit status"""
        success_count = 0
        error_count = 0
        
        for customer in queryset:
            if not customer.contact_number:
                error_count += 1
                continue
                
            # Format phone number (remove spaces, ensure it starts with country code)
            phone = customer.contact_number.replace(" ", "")
            if not phone.startswith("+"):
                phone = "+91" + phone  # Add India country code if not present
                
            # Determine message based on credit status
            status = customer.credit_status
            if status == "Over Limit":
                message = f"Dear {customer.name}, your credit balance of ₹{customer.total_due:.2f} has exceeded your limit of ₹{customer.credit_limit:.2f}. Please make a payment to continue purchases."
            elif status == "Near Limit":
                message = f"Dear {customer.name}, your credit balance of ₹{customer.total_due:.2f} is approaching your limit of ₹{customer.credit_limit:.2f}. Please consider making a payment soon."
            else:
                message = f"Dear {customer.name}, your current credit balance is ₹{customer.total_due:.2f} out of your limit of ₹{customer.credit_limit:.2f}."
            
            try:
                # This is a placeholder for actual WhatsApp API integration
                # In production, replace with actual API calls to WhatsApp Business API or Twilio
                """
                response = requests.post(
                    "https://api.whatsapp.com/send",
                    json={
                        "phone": phone,
                        "message": message
                    }
                )
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                """
                # For now, just simulate success
                success_count += 1
                
            except Exception as e:
                error_count += 1
        
        # Provide feedback to admin
        if success_count:
            messages.success(request, f"Successfully sent notifications to {success_count} customers.")
        if error_count:
            messages.error(request, f"Failed to send notifications to {error_count} customers.")
    
    send_credit_status_notification.short_description = "Send credit status notification via WhatsApp"

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'paid_by', 'paid_to', 'amount', 'description', 'print_expense')
    search_fields = ('paid_to', 'description')
    list_filter = ('date', 'paid_by')
    ordering = ('-date',)

    def print_expense(self, obj):
        url = reverse('generate_expense_pdf', args=[obj.id])
        return format_html('<a class="button" href="{}" target="_blank">Print Expense</a>', url)
    print_expense.short_description = "Print"

class DamagesAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'due_to', 'amount_loss', 'description', 'print_damage')
    search_fields = ('due_to', 'description')
    list_filter = ('date', 'name')
    ordering = ('-date',)

    def print_damage(self, obj):
        url = reverse('generate_damage_pdf', args=[obj.id])
        return format_html('<a class="button" href="{}" target="_blank">Print Damage</a>', url)
    print_damage.short_description = "Print"
class packagingsAdmin(admin.ModelAdmin):

    list_display = (
        'no_of_crates',
        'cost_per_crate',
        'packaging_total_display',
        'print_packaging_invoice'
    )
    list_display_links = None
    list_editable = ('no_of_crates', 'cost_per_crate')
    readonly_fields = ('packaging_total_display',)
    list_filter = ('no_of_crates',)
    search_fields = ('no_of_crates', 'cost_per_crate')

    def packaging_total_display(self, obj):
        return f"₹{obj.packaging_total:.2f}"
    packaging_total_display.short_description = "Total packaging cost"

    def print_packaging_invoice(self, obj):
        url = reverse('generate_packaging_pdf', args=[obj.id])
        return format_html('<a class="button" href="{}" target="_blank">Print Invoice</a>', url)
    print_packaging_invoice.short_description = "Print"

class PurchaseVendorResource(resources.ModelResource):
    class Meta:
        model = PurchaseVendor
        fields = ('id', 'name', 'contact_number', 'area')
        import_id_fields = ('name',)
        skip_unchanged = True
        report_skipped = True

# Admin for PurchaseVendor
class PurchaseVendorAdmin(ImportExportModelAdmin):
    resource_class = PurchaseVendorResource
    list_display = ('name', 'contact_number', 'area')
    search_fields = ('name', 'contact_number', 'area')

# Registering Vendor models
admin.site.register(PurchaseVendor, PurchaseVendorAdmin)
# Registering Purchase models
admin.site.register(PurchaseInvoice, PurchaseInvoiceAdmin)
admin.site.register(PurchaseProduct, PurchaseProductAdmin)
admin.site.register(Payment, PaymentAdmin)
# Registering Sales models
admin.site.register(SalesInvoice, SalesInvoiceAdmin)
admin.site.register(SalesProduct, SalesProductAdmin)
admin.site.register(SalesPayment, SalesPaymentAdmin)

# Make sure we're not registering Customer multiple times
try:
    admin.site.unregister(Customer)
except:
    pass
admin.site.register(Customer, CustomerAdmin)

admin.site.register(Product, ProductAdmin)
admin.site.register(Expense, ExpenseAdmin)
admin.site.register(Damages, DamagesAdmin)
admin.site.register(SalesLot) # Simple registration for now
admin.site.register(Packaging_Invoice, packagingsAdmin)

# Instead of trying to register a view directly, create separate URL patterns 
# that will be included in the admin site
def get_credit_dashboard_urls():
    return [
        path('credit-dashboard/', 
             admin.site.admin_view(credit_dashboard_view), 
             name='credit_dashboard'),
        path('credit-report/', 
             admin.site.admin_view(credit_report_view), 
             name='credit_report'),
    ]

# Define the views separately
def credit_dashboard_view(request):
    if not request.user.is_staff:
        return redirect('admin:login')
    
    # Calculate summary statistics
    customers = Customer.objects.all()
    
    # Total customers and credit limits
    total_customers = customers.count()
    total_credit_limit = customers.aggregate(Sum('credit_limit'))['credit_limit__sum'] or 0
    
    # Calculate customers over limit
    over_limit_customers = []
    near_limit_customers = []
    for customer in customers:
        if customer.credit_limit > 0:  # Only check customers with credit limits
            try:
                if customer.total_due > customer.credit_limit:
                    over_limit_customers.append(customer.id)
                elif customer.total_due >= (customer.credit_limit * 0.8) and customer.total_due <= customer.credit_limit:
                    near_limit_customers.append(customer.id)
            except Exception:
                # Skip if there's an error calculating
                pass
    
    over_limit_count = len(over_limit_customers)
    near_limit_count = len(near_limit_customers)
    
    # Total sales, purchases, and outstanding amounts - handle errors gracefully
    try:
        total_sales = SalesProduct.objects.aggregate(Sum('total'))['total__sum'] or 0
    except:
        total_sales = 0
        
    try:
        total_purchases = PurchaseProduct.objects.aggregate(Sum('total'))['total__sum'] or 0
    except:
        total_purchases = 0
        
    # Calculate total due safely
    total_due = 0
    for customer in customers:
        try:
            total_due += float(customer.total_due)
        except:
            pass
    
    # Get top customers by outstanding amount
    try:
        top_customers = sorted(customers, key=lambda x: float(x.total_due if x.total_due else 0), reverse=True)[:10]
    except:
        top_customers = []
    
    context = {
        'total_customers': total_customers,
        'total_credit_limit': total_credit_limit,
        'over_limit_count': over_limit_count,
        'near_limit_count': near_limit_count,
        'total_sales': total_sales,
        'total_purchases': total_purchases,
        'total_due': total_due,
        'top_customers': top_customers,
        'title': 'Credit Limit Dashboard',
        'app_label': 'Accounts',
        'opts': Customer._meta,
        'has_change_permission': request.user.has_perm('Accounts.change_customer')
    }
    
    return render(request, 'admin/credit_dashboard.html', context)

def credit_report_view(request):
    """Generate a comprehensive credit report for all customers"""
    if not request.user.is_staff:
        return redirect('admin:login')
        
    # Get all customers sorted by total due amount
    customers = Customer.objects.all()
    sorted_customers = sorted(customers, key=lambda x: x.total_due, reverse=True)
    
    # Group customers by credit status
    over_limit = []
    near_limit = []
    within_limit = []
    no_limit = []
    
    for customer in sorted_customers:
        status = customer.credit_status
        if status == "Over Limit":
            over_limit.append(customer)
        elif status == "Near Limit":
            near_limit.append(customer)
        elif status == "Within Limit":
            within_limit.append(customer)
        else:
            no_limit.append(customer)
    
    # Calculate statistics
    total_over_limit = sum(float(customer.total_due) for customer in over_limit)
    total_near_limit = sum(float(customer.total_due) for customer in near_limit)
    total_within_limit = sum(float(customer.total_due) for customer in within_limit)
    total_no_limit = sum(float(customer.total_due) for customer in no_limit)
    grand_total = total_over_limit + total_near_limit + total_within_limit + total_no_limit
    
    # Calculate percentages
    if grand_total > 0:
        over_limit_percent = (total_over_limit / grand_total) * 100
        near_limit_percent = (total_near_limit / grand_total) * 100
        within_limit_percent = (total_within_limit / grand_total) * 100
        no_limit_percent = (total_no_limit / grand_total) * 100
    else:
        over_limit_percent = near_limit_percent = within_limit_percent = no_limit_percent = 0
    
    context = {
        'over_limit': over_limit,
        'near_limit': near_limit,
        'within_limit': within_limit,
        'no_limit': no_limit,
        'total_over_limit': total_over_limit,
        'total_near_limit': total_near_limit,
        'total_within_limit': total_within_limit,
        'total_no_limit': total_no_limit,
        'grand_total': grand_total,
        'over_limit_percent': over_limit_percent,
        'near_limit_percent': near_limit_percent,
        'within_limit_percent': within_limit_percent,
        'no_limit_percent': no_limit_percent,
        'title': 'Credit Report',
        'app_label': 'Accounts',
        'opts': Customer._meta,
        'has_change_permission': request.user.has_perm('Accounts.change_customer')
    }
    
    return render(request, 'admin/credit_report.html', context)

class AdminSite(admin.AdminSite):
    site_header = "Star Mango Supplies Korutla"
    site_title = "Star Mango Supplies Korutla"
    index_title = "Star Mango Supplies Korutla Admin Panel"

    def index(self, request, extra_context=None):
        if not extra_context:
            extra_context = {}
            
        # Get current month and previous month
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        
        # Get monthly data for past 6 months
        months = []
        monthly_sales = []
        monthly_purchases = []
        
        for i in range(5, -1, -1):
            month_date = today.replace(day=1) - timedelta(days=i*30)
            month_name = month_date.strftime('%b')
            months.append(month_name)
            
            # Monthly sales - use SalesProduct instead of SalesInvoice
            month_sales = SalesProduct.objects.filter(
                invoice__invoice_date__year=month_date.year, 
                invoice__invoice_date__month=month_date.month
            ).aggregate(total=Sum('total'))
            
            # Monthly purchases
            month_purchases = PurchaseProduct.objects.filter(
                invoice__date__year=month_date.year, 
                invoice__date__month=month_date.month
            ).aggregate(total=Sum('total'))
            
            monthly_sales.append(float(month_sales['total'] or 0))
            monthly_purchases.append(float(month_purchases['total'] or 0))
        
        # Get sales data
        current_month_sales = SalesProduct.objects.filter(
            invoice__invoice_date__gte=current_month_start
        ).aggregate(total=Sum('total'))
        
        prev_month_sales = SalesProduct.objects.filter(
            invoice__invoice_date__gte=prev_month_start,
            invoice__invoice_date__lt=current_month_start
        ).aggregate(total=Sum('total'))
        
        # Get purchase data
        current_month_purchases = PurchaseProduct.objects.filter(
            invoice__date__gte=current_month_start
        ).aggregate(total=Sum('total'))
        
        prev_month_purchases = PurchaseProduct.objects.filter(
            invoice__date__gte=prev_month_start,
            invoice__date__lt=current_month_start
        ).aggregate(total=Sum('total'))
        
        # Calculate profit/loss
        total_sales = float(current_month_sales['total'] or 0)
        total_purchase = float(current_month_purchases['total'] or 0)
        profit_loss = total_sales - total_purchase
        
        prev_month_profit = float(prev_month_sales['total'] or 0) - float(prev_month_purchases['total'] or 0)
        
        # Calculate percent changes
        sales_percent_change = 0
        purchase_percent_change = 0
        profit_percent_change = 0
        
        if prev_month_sales['total']:
            sales_percent_change = ((total_sales - float(prev_month_sales['total'] or 0)) / (float(prev_month_sales['total'] or 1))) * 100
            
        if prev_month_purchases['total']:
            purchase_percent_change = ((total_purchase - float(prev_month_purchases['total'] or 0)) / (float(prev_month_purchases['total'] or 1))) * 100
            
        if prev_month_profit:
            profit_percent_change = ((profit_loss - prev_month_profit) / abs(prev_month_profit or 1)) * 100
        
        # Get customer data and credit status
        customers = Customer.objects.all()
        
        # Calculate total due
        total_due = sum(float(customer.total_due) for customer in customers)
        
        # Get credit status distribution
        over_limit = 0
        near_limit = 0
        within_limit = 0
        no_limit = 0
        
        for customer in customers:
            status = customer.credit_status
            if status == "Over Limit":
                over_limit += 1
            elif status == "Near Limit":
                near_limit += 1
            elif status == "Within Limit":
                within_limit += 1
            else:
                no_limit += 1
        
        credit_status_data = [over_limit, near_limit, within_limit, no_limit]
        
        # Top customers by outstanding amount
        top_customers = sorted(customers, key=lambda x: float(x.total_due), reverse=True)[:5]
        top_customer_names = [customer.name for customer in top_customers]
        top_customer_dues = [float(customer.total_due) for customer in top_customers]
        
        # Product sales distribution - get total sales by product
        sales_products = SalesProduct.objects.values('product__name').annotate(
            total_sales=Sum('total')
        ).order_by('-total_sales')[:5]
        
        product_names = [item['product__name'] for item in sales_products]
        product_sales_data = [float(item['total_sales'] or 0) for item in sales_products]
        
        # Custom JSON encoder to handle Decimal values
        class DecimalEncoder(json.JSONEncoder):
            def default(self, obj):
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)
                return super().default(obj)
        
        # Add data to context
        extra_context.update({
            'total_sales': total_sales,
            'total_purchase': total_purchase,
            'profit_loss': profit_loss,
            'total_due': total_due,
            'sales_percent_change': sales_percent_change,
            'purchase_percent_change': purchase_percent_change,
            'profit_percent_change': profit_percent_change,
            'due_percent_change': 0,  # No historical data for dues comparison
            'monthly_labels': json.dumps(months),
            'monthly_sales': json.dumps(monthly_sales),
            'monthly_purchases': json.dumps(monthly_purchases),
            'credit_status_data': json.dumps(credit_status_data),
            'top_customer_names': json.dumps(top_customer_names),
            'top_customer_dues': json.dumps(top_customer_dues),
            'product_names': json.dumps(product_names),
            'product_sales_data': json.dumps(product_sales_data),
        })
        
        return super().index(request, extra_context)

# Register our custom AdminSite
admin.site = AdminSite()

# Re-register models with the custom site
admin.site.register(PurchaseVendor, PurchaseVendorAdmin)
admin.site.register(PurchaseInvoice, PurchaseInvoiceAdmin)
admin.site.register(PurchaseProduct, PurchaseProductAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(SalesInvoice, SalesInvoiceAdmin)
admin.site.register(SalesProduct, SalesProductAdmin)
admin.site.register(SalesPayment, SalesPaymentAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(Expense, ExpenseAdmin)
admin.site.register(Damages, DamagesAdmin)
admin.site.register(SalesLot)
admin.site.register(Packaging_Invoice, packagingsAdmin)

# Re-register auth models
admin.site.register(User, UserAdmin)
admin.site.register(Group, GroupAdmin)

# Delete unnecessary registrations
# admin_site.register(models.Product, ProductAdmin)
# admin_site.register(models.Customer, CustomerAdmin)
# admin_site.register(models.Supplier, SupplierAdmin)
# admin_site.register(models.StockIn, StockInAdmin)
# admin_site.register(models.StockOut, StockOutAdmin)
# admin_site.register(models.Settings, SettingsAdmin)


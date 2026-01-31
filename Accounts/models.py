from django.db import models
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.contrib.auth.models import User


class PurchaseVendor(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact_number = models.CharField(max_length=15)
    area = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('account_pay', 'Account Pay'),
        ('upi', 'UPI GPay / PhonePay'),
        ('cash', 'Cash'),
    ]
    invoice = models.ForeignKey('PurchaseInvoice', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date = models.DateField(default=date.today)
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash',
        verbose_name="Payment Method"
    )
    attachment = models.FileField(
        upload_to='payment_attachments/', 
        blank=True, 
        null=True,
        verbose_name="Payment Attachment"
    )

    def clean(self):
        invoice = self.invoice
        if self.pk:
            current_total = invoice.payments.exclude(pk=self.pk).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        else:
            current_total = Decimal('0')
            
        new_total = current_total + self.amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        net_total_after_cash_cutting = invoice.net_total_after_cash_cutting

        if net_total_after_cash_cutting > Decimal('0.01') and new_total > net_total_after_cash_cutting:
            raise ValidationError(
                f"Total payment cannot exceed the net total after 2% cash cutting: ₹{net_total_after_cash_cutting}."
            )
                
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment of ₹{self.amount} for Invoice {self.invoice.invoice_number}"


class PurchaseInvoice(models.Model):
    invoice_number = models.CharField(max_length=20, editable=False, unique=True)
    lot_number = models.CharField(max_length=10, editable=False, unique=True)
    date = models.DateField(default=date.today)
    vendor = models.ForeignKey('PurchaseVendor', on_delete=models.CASCADE, related_name='invoices')
    net_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_issuer_name = models.CharField(
        max_length=100,
        choices=[('Abdul Rafi', 'Abdul Rafi'), ('Sadiq', 'Sadiq')],
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = "Purchase Invoice"
        verbose_name_plural = "Purchase Invoices"

    def save(self, *args, **kwargs):
        if not self.invoice_number and self.pk is None:
            last_invoice = PurchaseInvoice.objects.order_by("-id").first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_number = int(last_invoice.invoice_number[-2:])
                except ValueError:
                    last_number = 0
                self.invoice_number = f"MS2025R{last_number + 1:02d}"
            else:
                self.invoice_number = "MS2025R01"

        if not self.lot_number and self.pk is None:
            last_lot = PurchaseInvoice.objects.order_by("-id").first()
            if last_lot and last_lot.lot_number:
                try:
                    last_lot_number = int(last_lot.lot_number.split("-")[-1])
                except ValueError:
                    last_lot_number = 0
                self.lot_number = f"LOT-{last_lot_number + 1:02d}"
            else:
                self.lot_number = "LOT-01"

        update_total = True
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            update_total = 'net_total' not in kwargs['update_fields']

        super().save(*args, **kwargs)

        if update_total and self.pk:
            calculated_total = sum(product.total for product in self.purchase_products.all())
            if self.net_total != calculated_total:
                self.net_total = calculated_total
                type(self).objects.filter(pk=self.pk).update(net_total=calculated_total)

    @property
    def available_quantity(self):
        total_purchased = sum(product.quantity for product in self.purchase_products.all())
        total_used = self.sales_lots.aggregate(total=Sum('quantity'))['total'] or Decimal('0.00')
        return total_purchased - total_used      

    @property
    def net_total_after_cash_cutting(self):
        return round(self.net_total - (self.net_total * Decimal('0.02')), 2)

    @property
    def paid_amount(self):
        return round(sum(payment.amount for payment in self.payments.all()), 2)

    @property
    def due_amount(self):
        return round(self.net_total_after_cash_cutting - self.paid_amount, 2)

    def __str__(self):
        return f" {self.lot_number} (Invoice {self.invoice_number})"

    def get_product_quantities(self):
        products = {}
        for purchase_product in self.purchase_products.all():
            sold = SalesProduct.objects.filter(
                invoice__lot=self,
                product=purchase_product.product
            ).aggregate(total=Sum('quantity'))['total'] or 0
            available = purchase_product.quantity - sold
            products[purchase_product.product.name] = available
        return products


class Purchase(models.Model):
    invoice = models.OneToOneField(PurchaseInvoice, on_delete=models.CASCADE, related_name='purchase_invoice')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_amount = sum(product.total for product in self.invoice.purchase_products.all())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Purchase for Invoice {self.invoice.invoice_number}"


class Product(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class PurchaseProduct(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='purchase_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    serial_number = models.IntegerField(default=0, editable=False)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    damage = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Damage (Kg)")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Discount (%)")
    rotten = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Rotten (Kg)")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    loading_unloading = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if not self.serial_number or self.serial_number == 0:
            existing_products = PurchaseProduct.objects.filter(invoice=self.invoice).order_by('id')
            if existing_products.exists():
                max_serial = existing_products.aggregate(models.Max('serial_number'))['serial_number__max'] or 0
                self.serial_number = max_serial + 1
            else:
                self.serial_number = 1

        physical_quantity = self.quantity - self.damage - self.rotten
        physical_quantity = max(physical_quantity, Decimal('0.00'))
        base_price_total = physical_quantity * self.price
        discount_amount = (base_price_total * self.discount) / 100
        price_after_discount = base_price_total - discount_amount

        try:
            product_name = self.product.name
        except Product.DoesNotExist:
            product_name = ""

        if product_name == "Rotten":
            self.loading_unloading = Decimal('0.00')
        else:
            self.loading_unloading = Decimal(self.quantity) * Decimal('0.40')

        self.total = price_after_discount - self.loading_unloading
        if self.total <= 0:
            self.total = Decimal('0.01')

        super().save(*args, **kwargs)

        if self.invoice and self.invoice.pk:
            calculated_total = sum(product.total for product in self.invoice.purchase_products.all())
            if self.invoice.net_total != calculated_total:
                PurchaseInvoice.objects.filter(pk=self.invoice.pk).update(net_total=calculated_total)

        self.resequence_serial_numbers()

    def resequence_serial_numbers(self):
        products = PurchaseProduct.objects.filter(invoice=self.invoice).order_by('id')
        for i, product in enumerate(products, start=1):
            if product.serial_number != i:
                PurchaseProduct.objects.filter(pk=product.pk).update(serial_number=i)

    def __str__(self):
        return f"{self.serial_number}. {self.product.name} in Invoice {self.invoice.invoice_number}"


class SalesInvoice(models.Model):
    invoice_number = models.CharField(max_length=20, editable=False, unique=True)
    invoice_date = models.DateField(default=date.today)
    vendor = models.ForeignKey('Customer', on_delete=models.PROTECT, related_name='sales_invoices')
    lots = models.ManyToManyField(
        'PurchaseInvoice',
        through='SalesLot',
        verbose_name="Lots Used",
        help_text="Select multiple lots and specify quantities used"
    )
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)
    gross_vehicle_weight = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,
                                               help_text="In Kilograms")
    reference = models.CharField(max_length=200, blank=True, null=True)
    no_of_crates = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,
                                      verbose_name="No of Crates")
    cost_per_crate = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,
                                        verbose_name="Packaging cost per crate (₹)")
    purchased_crates_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,
                                                  verbose_name="No of Purchased Crates")
    purchased_crates_unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True,
                                                    verbose_name="Purchased price per crate (₹)")
    
    def save(self, *args, **kwargs):
        if not self.invoice_number and self.pk is None:
            last_invoice = SalesInvoice.objects.order_by("-id").first()
            if last_invoice and last_invoice.invoice_number:
                try:
                    last_number = int(last_invoice.invoice_number[-2:])
                except ValueError:
                    last_number = 0
                self.invoice_number = f"SA2025S{last_number + 1:02d}"
            else:
                self.invoice_number = "SA2025S01"
        super().save(*args, **kwargs)
    
    @property
    def total_gross_weight(self):
        total = self.sales_products.aggregate(total=models.Sum('gross_weight'))['total'] or Decimal('0.00')
        return total
    
    @property
    def net_total(self):
        total = self.sales_products.aggregate(total=models.Sum('total'))['total'] or Decimal('0.00')
        return total
    
    @property
    def net_total_after_commission(self):
        return self.net_total + self.total_gross_weight
    
    @property
    def packaging_total(self):
        if self.no_of_crates is not None and self.cost_per_crate is not None:
            return Decimal(self.no_of_crates) * self.cost_per_crate
        return Decimal('0.00')
    
    @property
    def purchased_crates_total(self):
        if self.purchased_crates_quantity is not None and self.purchased_crates_unit_price is not None:
            return (Decimal(self.purchased_crates_quantity) * self.purchased_crates_unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')

    @property
    def net_total_after_packaging(self):
        return self.net_total_after_commission + self.packaging_total + self.purchased_crates_total
    
    @property
    def paid_amount(self):
        return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def due_amount(self):
        return self.net_total_after_packaging - self.paid_amount

    def payment_status(self):
        if self.due_amount == 0:
            return "Paid"
        elif self.paid_amount == 0:
            return "Unpaid"
        return "Partial"

    def __str__(self):
        return f"Sales Invoice {self.invoice_number} for {self.vendor}"


class SalesProduct(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='sales_products')
    serial_number = models.IntegerField(editable=False)
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    gross_weight = models.DecimalField(max_digits=12, decimal_places=2, help_text="Gross Weight in Kgs")
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Discount as percentage")
    rotten = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Rotten weight in Kgs")
    net_weight = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,
                                     help_text="Net Weight in Kgs after discount & rotten deduction")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,
                                help_text="Total = Net Weight * Price")
    lot = models.ForeignKey(
        'SalesLot',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Link to specific lot usage"
    )
    
    def save(self, *args, **kwargs):
        if not self.serial_number:
            last_item = SalesProduct.objects.filter(invoice=self.invoice).order_by('-serial_number').first()
            self.serial_number = last_item.serial_number + 1 if last_item else 1
        
        self.net_weight = self.gross_weight - ((self.gross_weight * self.discount) / Decimal('100.00')) - self.rotten
        self.total = (self.net_weight * self.price)
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.serial_number}. {self.product.name} in Invoice {self.invoice.invoice_number}"


class SalesPayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('account_pay', 'Account Pay'),
        ('upi', 'UPI GPay / PhonePay'),
        ('cash', 'Cash'),
    ]
    
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date = models.DateField(default=date.today)
    payment_mode = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        default='cash', 
        verbose_name="Payment Method"
    )
    attachment = models.FileField(
        upload_to='sales_payment_attachments/', 
        blank=True, 
        null=True,
        verbose_name="Payment Attachment"
    )
    
    def __str__(self):
        return f"Payment of ₹{self.amount} for Sales Invoice {self.invoice.invoice_number}"
    

class Customer(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    credit_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        default=0,
        help_text="Maximum credit limit allowed (0 means no specific limit)"
    )
    
    def __str__(self):
        return self.name
    
    @property
    def total_due(self):
        return sum(invoice.due_amount for invoice in self.sales_invoices.all())
        
    @property
    def is_over_credit_limit(self):
        if self.credit_limit <= 0:
            return False
        return self.total_due > self.credit_limit
    
    @property
    def credit_status(self):
        if not self.credit_limit or self.credit_limit <= 0:
            return "No Limit Set"
        
        utilization = (self.total_due / self.credit_limit) * 100
        
        if utilization >= 100:
            return "Over Limit"
        elif utilization >= 80:
            return "Near Limit"
        else:
            return "Within Limit"


class Expense(models.Model):
    date = models.DateField()
    paid_by = models.CharField(max_length=100)
    paid_to = models.CharField(max_length=100)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.date} - {self.paid_to} - ₹{self.amount}"


class Damages(models.Model):
    date = models.DateField()
    name = models.CharField(max_length=100)
    due_to = models.CharField(max_length=100)
    description = models.TextField()
    amount_loss = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.date} - {self.due_to} - ₹{self.amount_loss}"

    class Meta:
        verbose_name = "Damage"
        verbose_name_plural = "Damages"


class SalesLot(models.Model):
    """Tracks which lots (from purchase invoices) are used in a sales invoice"""
    sales_invoice = models.ForeignKey(
        'SalesInvoice', 
        on_delete=models.CASCADE,
        related_name='sales_lots'
    )
    purchase_invoice = models.ForeignKey(
        'PurchaseInvoice',
        on_delete=models.CASCADE,
        related_name='sales_lots',
        verbose_name="Lot"
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Quantity used from this lot (in kgs)"
    )

    class Meta:
        unique_together = ('sales_invoice', 'purchase_invoice')

    def __str__(self):
        return f"{self.quantity}kg from {self.purchase_invoice.lot_number}"
    
    def clean(self):
        super().clean()
        
        if self.pk and hasattr(self, '_loaded_quantity') and self.quantity == self._loaded_quantity:
            return
        
        if not self.purchase_invoice:
            return
            
        if self.quantity is None:
            return

        if self.purchase_invoice.available_quantity is not None:
            if self.pk:
                from django.db.models import F
                original = type(self).objects.get(pk=self.pk)
                if self.quantity > original.quantity + self.purchase_invoice.available_quantity:
                    raise ValidationError(
                        f"Only {original.quantity + self.purchase_invoice.available_quantity}kg available in {self.purchase_invoice.lot_number}"
                    )
            elif self.quantity > self.purchase_invoice.available_quantity:
                raise ValidationError(
                    f"Only {self.purchase_invoice.available_quantity}kg available in {self.purchase_invoice.lot_number}"
                )

        if not hasattr(self, 'sales_invoice') or not self.sales_invoice or not self.sales_invoice.pk:
            return

        sales_products = self.sales_invoice.sales_products.all()
        if sales_products.exists():
            sales_product = sales_products.first().product
            if not self.purchase_invoice.purchase_products.filter(product=sales_product).exists():
                raise ValidationError(
                    f"Lot {self.purchase_invoice.lot_number} doesn't contain {sales_product.name}"
                )
                
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.pk and hasattr(self, 'quantity'):
            self._loaded_quantity = self.quantity


class Packaging_Invoice(models.Model):
    no_of_crates = models.IntegerField(blank=True, null=True, verbose_name="No of Crates")
    cost_per_crate = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True,
                                        verbose_name="Packaging cost per crate (₹)")

    @property
    def packaging_total(self):
        if self.no_of_crates is not None and self.cost_per_crate is not None:
            return Decimal(self.no_of_crates) * self.cost_per_crate
        return Decimal('0.00')

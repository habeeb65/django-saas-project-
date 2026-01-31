from rest_framework import serializers
from Accounts.models import (
    PurchaseVendor, 
    PurchaseInvoice, 
    PurchaseProduct, 
    Product,
    Payment
)

# Removed tenant serializers - single tenant mode

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name']

class PurchaseVendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseVendor
        fields = ['id', 'name', 'contact_number', 'area']

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'amount', 'date', 'payment_mode', 'attachment']

class PurchaseProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = PurchaseProduct
        fields = [
            'id', 'invoice', 'product', 'product_name', 'serial_number', 
            'quantity', 'price', 'damage', 'discount', 'rotten', 
            'total', 'loading_unloading'
        ]

class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    purchase_products = PurchaseProductSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    available_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    net_total_after_cash_cutting = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'lot_number', 'date', 'vendor', 'vendor_name',
            'net_total', 'payment_issuer_name', 'purchase_products', 'payments',
            'available_quantity', 'net_total_after_cash_cutting', 'paid_amount', 'due_amount'
        ]
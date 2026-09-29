from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Product, Warehouse
from .models import (
    SalesInvoice, SalesInvoiceLine, CustomerPayment, SalesReturn, SalesReturnLine,
    Quotation, QuotationLine, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine,
    POSShift, POSCart, POSReceipt,
    PriceList, PriceListItem, Promotion, CommercialSettings, ExchangeRate, TaxScheme, TaxCode,
)


class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoiceLine
        fields = ["id", "product", "quantity", "unit_price", "line_total", "so_line"]
        read_only_fields = ["id", "line_total"]


class SalesInvoiceSerializer(serializers.ModelSerializer):
    lines = SalesInvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = SalesInvoice
        fields = [
            "id", "invoice_number", "customer", "sales_order", "date", "due_date",
            "currency", "exchange_rate", "transaction_subtotal", "transaction_tax_amount",
            "transaction_total", "transaction_amount_paid", "subtotal", "tax_amount", "total",
            "amount_paid", "status", "lines",
        ]
        read_only_fields = fields


class CreateInvoiceLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_code = serializers.PrimaryKeyRelatedField(queryset=TaxCode.objects.all(), required=False, allow_null=True)


class CreateInvoiceInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    date = serializers.DateField()
    due_date = serializers.DateField(required=False, allow_null=True)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, default=0)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_reason = serializers.CharField(required=False, allow_blank=True, default="")
    currency = serializers.CharField(max_length=3, required=False)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    lines = CreateInvoiceLineInputSerializer(many=True)


class CustomerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerPayment
        fields = ["id", "customer", "invoice", "amount", "date", "method", "currency",
                  "transaction_amount", "exchange_rate", "base_amount"]
        read_only_fields = ["id"]


class SalesReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesReturnLine
        fields = ["id", "product", "quantity", "unit_price", "line_total"]
        read_only_fields = ["id", "line_total"]


class SalesReturnSerializer(serializers.ModelSerializer):
    lines = SalesReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = SalesReturn
        fields = ["id", "invoice", "date", "reason", "total", "refund_method", "lines"]
        read_only_fields = fields


class SalesReturnLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class ProcessReturnInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    refund_method = serializers.ChoiceField(choices=SalesReturn.REFUND_METHOD, default="cash")
    lines = SalesReturnLineInputSerializer(many=True)


# ---------------------------------------------------------------- Phase 33


class QuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLine
        fields = ["id", "product", "quantity", "unit_price", "line_total"]
        read_only_fields = ["id", "line_total"]


class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True, read_only=True)

    class Meta:
        model = Quotation
        fields = ["id", "customer", "date", "status", "notes", "created_by", "created_at", "lines"]
        read_only_fields = ["id", "status", "created_by", "created_at", "lines"]


class QuotationLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class CreateQuotationInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = QuotationLineInputSerializer(many=True)


class SalesOrderLineSerializer(serializers.ModelSerializer):
    delivered_quantity = serializers.SerializerMethodField()
    invoiced_quantity = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrderLine
        fields = ["id", "product", "quantity", "unit_price", "line_total", "delivered_quantity", "invoiced_quantity"]
        read_only_fields = ["id", "line_total", "delivered_quantity", "invoiced_quantity"]

    def get_delivered_quantity(self, obj):
        from .services import delivered_quantity
        return str(delivered_quantity(obj))

    def get_invoiced_quantity(self, obj):
        from .services import invoiced_quantity
        return str(invoiced_quantity(obj))


class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = SalesOrder
        fields = ["id", "quotation", "customer", "date", "reference", "status", "created_by", "created_at", "lines"]
        read_only_fields = ["id", "status", "created_by", "created_at", "lines"]


class SalesOrderLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class CreateSalesOrderInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    date = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    quotation = serializers.PrimaryKeyRelatedField(queryset=Quotation.objects.all(), required=False, allow_null=True)
    lines = SalesOrderLineInputSerializer(many=True, required=False)


class DeliveryLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryLine
        fields = ["id", "so_line", "quantity", "unit_price", "line_total"]
        read_only_fields = fields


class DeliveryNoteSerializer(serializers.ModelSerializer):
    lines = DeliveryLineSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryNote
        fields = ["id", "sales_order", "warehouse", "date", "delivered_by", "created_at", "lines"]
        read_only_fields = fields


class DeliveryLineInputSerializer(serializers.Serializer):
    so_line = serializers.PrimaryKeyRelatedField(queryset=SalesOrderLine.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)


class CreateDeliveryInputSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    date = serializers.DateField()
    allow_over_delivery = serializers.BooleanField(required=False, default=False)
    lines = DeliveryLineInputSerializer(many=True)


class InvoiceFromOrderLineInputSerializer(serializers.Serializer):
    so_line = serializers.PrimaryKeyRelatedField(queryset=SalesOrderLine.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class CreateInvoiceFromOrderInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    due_date = serializers.DateField(required=False, allow_null=True)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, default=0)
    allow_over_invoicing = serializers.BooleanField(required=False, default=False)
    lines = InvoiceFromOrderLineInputSerializer(many=True)


class POSShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSShift
        fields = ["id", "cashier", "warehouse", "opened_at", "closed_at", "opening_cash",
                  "expected_cash", "counted_cash", "variance", "status"]
        read_only_fields = fields


class POSCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSCart
        fields = ["id", "shift", "customer", "reference", "status", "created_by", "created_at", "completed_at"]
        read_only_fields = fields


class POSReceiptSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    payments = serializers.SerializerMethodField()

    class Meta:
        model = POSReceipt
        fields = ["id", "receipt_number", "shift", "invoice", "invoice_number", "cart", "payments", "created_at"]
        read_only_fields = fields

    def get_payments(self, obj):
        return [{"method": p.method, "amount": str(p.amount)} for p in obj.payments.all()]


class OpenPOSShiftInputSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    opening_cash = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)


class POSLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class POSPaymentInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["cash", "card", "bank"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class CompletePOSSaleInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    cart = serializers.PrimaryKeyRelatedField(queryset=POSCart.objects.all(), required=False, allow_null=True)
    date = serializers.DateField()
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, default=0)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_reason = serializers.CharField(required=False, allow_blank=True, default="")
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="")
    loyalty_points = serializers.IntegerField(required=False, min_value=0, default=0)
    lines = POSLineInputSerializer(many=True, required=False, default=list)
    payments = POSPaymentInputSerializer(many=True)


class HoldPOSCartInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    lines = POSLineInputSerializer(many=True)


class POSCashMovementInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["cash_in", "cash_out"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=255)


class ClosePOSShiftInputSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(max_digits=14, decimal_places=2)


class PriceListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceListItem
        fields = ["id", "product", "unit_price"]


class PriceListSerializer(serializers.ModelSerializer):
    items = PriceListItemSerializer(many=True)

    class Meta:
        model = PriceList
        fields = ["id", "name", "customer", "priority", "start_date", "end_date", "is_active", "items"]

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        obj = PriceList.objects.create(company=self.context["request"].company, **validated_data)
        PriceListItem.objects.bulk_create([PriceListItem(price_list=obj, **item) for item in items])
        return obj


class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ["id", "name", "product", "discount_type", "discount_value", "priority",
                  "start_date", "end_date", "is_active"]


class CommercialSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommercialSettings
        fields = ["discount_approval_threshold_percent", "loyalty_enabled",
                  "loyalty_currency_per_point", "loyalty_spend_per_point"]


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "currency", "effective_date", "rate", "source", "is_manual"]
        read_only_fields = ["id"]


class TaxSchemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxScheme
        fields = ["id", "name", "registration_number", "is_active"]


class TaxCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxCode
        fields = ["id", "scheme", "code", "name", "rate", "inclusive", "classification",
                  "effective_from", "effective_to", "is_active"]

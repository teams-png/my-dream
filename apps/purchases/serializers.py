from rest_framework import serializers
from apps.suppliers.models import Supplier
from apps.inventory.models import Product, Warehouse
from .models import (
    Purchase, PurchaseLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine,
    PurchaseOrder, PurchaseOrderLine, GoodsReceiptNote, GoodsReceiptNoteLine,
)


class PurchaseLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseLine
        fields = ["id", "product", "quantity", "unit_cost", "line_total", "po_line"]
        read_only_fields = ["id", "line_total"]


class PurchaseSerializer(serializers.ModelSerializer):
    lines = PurchaseLineSerializer(many=True, read_only=True)

    class Meta:
        model = Purchase
        fields = [
            "id", "bill_number", "supplier", "purchase_order", "date", "subtotal",
            "tax_amount", "total", "amount_paid", "status", "lines",
        ]
        read_only_fields = fields


class CreatePurchaseLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2)


class CreatePurchaseInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    date = serializers.DateField()
    bill_number = serializers.CharField(required=False, allow_blank=True, default="")
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, default=0)
    lines = CreatePurchaseLineInputSerializer(many=True)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPayment
        fields = ["id", "supplier", "purchase", "amount", "date", "method"]
        read_only_fields = ["id"]


class PurchaseReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReturnLine
        fields = ["id", "product", "quantity", "unit_cost", "line_total"]
        read_only_fields = ["id", "line_total"]


class PurchaseReturnSerializer(serializers.ModelSerializer):
    lines = PurchaseReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = ["id", "purchase", "date", "reason", "total", "refund_method", "lines"]
        read_only_fields = fields


class PurchaseReturnLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2)


class ProcessPurchaseReturnInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    refund_method = serializers.ChoiceField(choices=PurchaseReturn.REFUND_METHOD, default="supplier_credit")
    lines = PurchaseReturnLineInputSerializer(many=True)


# ---------------------------------------------------------------- Phase 32


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    received_quantity = serializers.SerializerMethodField()
    billed_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "product", "quantity", "unit_cost", "line_total", "received_quantity", "billed_quantity"]
        read_only_fields = ["id", "line_total", "received_quantity", "billed_quantity"]

    def get_received_quantity(self, obj):
        from .services import received_quantity
        return str(received_quantity(obj))

    def get_billed_quantity(self, obj):
        from .services import billed_quantity
        return str(billed_quantity(obj))


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "supplier", "date", "reference", "status", "created_by", "created_at", "lines"]
        read_only_fields = ["id", "status", "created_by", "created_at", "lines"]


class PurchaseOrderLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2)


class CreatePurchaseOrderInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    date = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    lines = PurchaseOrderLineInputSerializer(many=True)


class GoodsReceiptNoteLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodsReceiptNoteLine
        fields = ["id", "po_line", "quantity", "unit_cost", "line_total"]
        read_only_fields = fields


class GoodsReceiptNoteSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptNoteLineSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceiptNote
        fields = ["id", "purchase_order", "warehouse", "date", "received_by", "journal_entry", "created_at", "lines"]
        read_only_fields = fields


class GoodsReceiptLineInputSerializer(serializers.Serializer):
    po_line = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrderLine.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)


class CreateGoodsReceiptInputSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    date = serializers.DateField()
    allow_over_receipt = serializers.BooleanField(required=False, default=False)
    lines = GoodsReceiptLineInputSerializer(many=True)


class BillFromGrnLineInputSerializer(serializers.Serializer):
    po_line = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrderLine.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)


class CreateBillFromGrnInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    bill_number = serializers.CharField(required=False, allow_blank=True, default="")
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=4, default=0)
    allow_over_billing = serializers.BooleanField(required=False, default=False)
    lines = BillFromGrnLineInputSerializer(many=True)

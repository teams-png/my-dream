from rest_framework import serializers
from .models import (
    ProductCategory, Brand, Unit, Warehouse, Product, StockMovement,
    ProductBatch, ProductSerial, StockCount, StockCountLine,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name"]


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "is_default"]


class ProductSerializer(serializers.ModelSerializer):
    current_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "category", "brand", "unit",
            "cost_price", "selling_price", "reorder_level", "is_active", "current_stock",
            "is_stock_tracked", "tracking_type", "block_expired_batch_sale",
            "parent", "variant_label", "size", "colour", "material", "design", "attributes",
        ]
        read_only_fields = ["id"]

    def get_current_stock(self, obj):
        return obj.current_stock()


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = ["id", "product", "warehouse", "quantity", "reason", "reference", "batch", "serial", "moved_at"]
        read_only_fields = fields


class ProductBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBatch
        fields = ["id", "product", "batch_number", "manufacture_date", "expiry_date", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_product(self, product):
        request = self.context["request"]
        if product.company_id != request.company.id:
            raise serializers.ValidationError("This product does not belong to the active company.")
        if product.tracking_type != "batch":
            raise serializers.ValidationError("This product is not batch-tracked.")
        return product


class ProductSerialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSerial
        fields = ["id", "product", "warehouse", "serial_number", "status", "received_date", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class StockCountLineSerializer(serializers.ModelSerializer):
    variance = serializers.ReadOnlyField()

    class Meta:
        model = StockCountLine
        fields = ["id", "product", "system_quantity", "counted_quantity", "notes", "variance"]
        read_only_fields = ["id", "system_quantity", "variance"]


class StockCountSerializer(serializers.ModelSerializer):
    lines = StockCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockCount
        fields = ["id", "warehouse", "date", "status", "created_by", "completed_by", "completed_at", "created_at", "lines"]
        read_only_fields = ["id", "status", "created_by", "completed_by", "completed_at", "created_at", "lines"]


class StartStockCountInputSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    product_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class SubmitStockCountLineInputSerializer(serializers.Serializer):
    counted_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class StockTransferInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    from_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    to_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    batch = serializers.PrimaryKeyRelatedField(queryset=ProductBatch.objects.all(), required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, default="")


class StockAdjustmentInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity_delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason_note = serializers.CharField(required=False, allow_blank=True, default="")
    batch = serializers.PrimaryKeyRelatedField(queryset=ProductBatch.objects.all(), required=False, allow_null=True)

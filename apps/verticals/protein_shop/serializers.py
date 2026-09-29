from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Warehouse

from .models import ProteinBatch, SaleRecord


class ProteinBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProteinBatch
        fields = [
            "id", "product", "batch_number", "flavour", "weight_grams", "expiry_date", "received_date",
            "purchase_price", "selling_price", "quantity_received", "quantity_remaining", "is_expired",
        ]
        read_only_fields = ["id", "is_expired"]

    def create(self, validated_data):
        validated_data["quantity_remaining"] = validated_data["quantity_received"]
        return super().create(validated_data)


class SaleRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleRecord
        fields = ["id", "batch", "customer", "quantity", "sold_price", "sold_date", "is_returned"]
        read_only_fields = ["id", "is_returned"]


class SellActionSerializer(serializers.Serializer):
    """Parses date/decimal fields before services.sell() — same care as medical_shop's DispenseActionSerializer."""
    customer = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Customer.objects.none())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_date = serializers.DateField()

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)

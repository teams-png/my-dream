from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Warehouse

from .models import MedicineBatch, DispenseRecord


class MedicineBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineBatch
        fields = [
            "id", "product", "batch_number", "manufacturer", "expiry_date", "received_date",
            "purchase_price", "selling_price", "quantity_received", "quantity_remaining", "is_expired",
        ]
        read_only_fields = ["id", "is_expired"]

    def create(self, validated_data):
        # quantity_remaining starts equal to quantity_received on receipt
        validated_data["quantity_remaining"] = validated_data["quantity_received"]
        return super().create(validated_data)


class DispenseRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DispenseRecord
        fields = [
            "id", "batch", "customer", "quantity", "sold_price",
            "sold_date", "prescription_reference", "is_returned",
        ]
        read_only_fields = ["id", "is_returned"]


class DispenseActionSerializer(serializers.Serializer):
    """Parses date/decimal fields before services.dispense() — same care as SellCycleUnitSerializer."""
    customer = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Customer.objects.none())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_date = serializers.DateField()
    prescription_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)

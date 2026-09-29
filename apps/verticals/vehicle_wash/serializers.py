from rest_framework import serializers
from apps.inventory.models import Warehouse
from .models import Vehicle, WashPackage, WashOrder


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "customer", "vehicle_number", "vehicle_type", "make", "model", "color"]
        read_only_fields = ["id"]


class WashPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WashPackage
        fields = ["id", "name", "vehicle_type", "price", "duration_minutes", "description", "is_active", "product"]
        read_only_fields = ["id", "product"]


class CreateWashPackageSerializer(serializers.Serializer):
    """Input for WashPackageViewSet.create — goes through vehicle_wash.services.create_wash_package
    so the linked service Product is always created alongside the package."""
    name = serializers.CharField(max_length=100)
    vehicle_type = serializers.ChoiceField(choices=Vehicle.VEHICLE_TYPE)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = serializers.IntegerField(min_value=1, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class WashOrderSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = WashOrder
        fields = ["id", "vehicle", "package", "staff", "scheduled_at", "status", "price", "payment_method", "sales_invoice"]
        read_only_fields = ["id", "status", "sales_invoice"]


class CompleteWashSerializer(serializers.Serializer):
    """Input for WashOrderViewSet.complete — a warehouse is required because
    completing a wash now invoices (see vehicle_wash.services.complete_wash)."""
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)

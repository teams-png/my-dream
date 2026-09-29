from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Product, Warehouse
from .models import FabricDetail, Measurement, TailoringOrder


class FabricDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = FabricDetail
        fields = [
            "id", "product", "fabric_type", "color", "design",
            "material", "length_per_unit", "width_inches",
        ]
        read_only_fields = ["id"]


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = ["id", "customer", "garment_type", "values", "taken_on", "notes"]
        read_only_fields = ["id"]


class TailoringOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = TailoringOrder
        fields = [
            "id", "customer", "measurement", "fabric_product", "order_date",
            "expected_delivery_date", "delivered_date", "status", "price", "notes", "sales_invoice",
        ]
        read_only_fields = ["id", "delivered_date", "status", "sales_invoice"]


class CreateTailoringOrderSerializer(serializers.Serializer):
    """Input for TailoringOrderViewSet.create — goes through services.create_tailoring_order,
    which invoices the order's price before the order row is created."""
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none())
    measurement = serializers.PrimaryKeyRelatedField(queryset=Measurement.objects.none(), required=False, allow_null=True)
    fabric_product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none(), required=False, allow_null=True)
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    order_date = serializers.DateField()
    expected_delivery_date = serializers.DateField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        self.fields["measurement"].queryset = Measurement.objects.for_company(company)
        self.fields["fabric_product"].queryset = Product.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)

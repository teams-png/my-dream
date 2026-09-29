from rest_framework import serializers
from apps.customers.models import Customer
from apps.inventory.models import Warehouse

from .models import CycleUnit, ServiceTicket


class CycleUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CycleUnit
        fields = [
            "id", "product", "serial_number", "warranty_months", "purchase_price",
            "status", "sold_price", "sold_date", "buyer",
        ]
        read_only_fields = ["id", "status", "sold_price", "sold_date", "buyer"]


class SellCycleUnitSerializer(serializers.Serializer):
    """Parses dates/decimals to real Python types before services.sell_unit — see mobile_shop's warranty_expires bug."""
    buyer = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Customer.objects.none())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    sold_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_date = serializers.DateField()

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["buyer"].queryset = Customer.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)


class ServiceTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceTicket
        fields = [
            "id", "customer", "cycle_unit", "cycle_description", "issue_description",
            "staff", "received_date", "status", "cost", "delivered_date",
        ]
        read_only_fields = ["id", "status", "cost", "delivered_date"]


class CompleteServiceSerializer(serializers.Serializer):
    cost = serializers.DecimalField(max_digits=10, decimal_places=2)


class DeliverServiceSerializer(serializers.Serializer):
    delivered_date = serializers.DateField()

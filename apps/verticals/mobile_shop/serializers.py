from rest_framework import serializers
from .models import MobileUnit, MobileRepairJob, MobileTradeIn


class MobileUnitSerializer(serializers.ModelSerializer):
    warranty_expires = serializers.ReadOnlyField()

    class Meta:
        model = MobileUnit
        fields = [
            "id", "product", "imei", "serial_number", "condition", "warranty_months",
            "purchase_price", "status", "sold_price", "sold_date", "buyer", "warranty_expires", "sale_invoice", "warehouse",
        ]
        read_only_fields = ["id", "status", "sold_price", "sold_date", "buyer", "warranty_expires", "sale_invoice", "warehouse"]


class MobileRepairJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileRepairJob
        exclude = ["company"]
        read_only_fields = ["job_number", "invoice", "status", "received_at", "completed_at"]


class MobileTradeInSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileTradeIn
        exclude = ["company"]
        read_only_fields = ["status", "purchase", "mobile_unit", "created_at"]

from rest_framework import serializers

from apps.sales.models import SalesInvoice
from apps.purchases.models import Purchase
from apps.customers.models import Customer
from apps.suppliers.models import Supplier

from .models import AgeingBucket, CollectionNote


class AgeingBucketSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgeingBucket
        fields = ["id", "label", "min_days", "max_days", "order"]
        read_only_fields = ["id"]


class AgeingSummaryBucketSerializer(serializers.Serializer):
    label = serializers.CharField()
    min_days = serializers.IntegerField()
    max_days = serializers.IntegerField(allow_null=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    count = serializers.IntegerField()


class AgeingSummarySerializer(serializers.Serializer):
    not_due = serializers.DecimalField(max_digits=14, decimal_places=2)
    no_due_date = serializers.DecimalField(max_digits=14, decimal_places=2)
    unbucketed_overdue = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    buckets = AgeingSummaryBucketSerializer(many=True)


class AgeingDetailRowSerializer(serializers.Serializer):
    document_id = serializers.SerializerMethodField()
    document_label = serializers.SerializerMethodField()
    party_id = serializers.SerializerMethodField()
    party_name = serializers.SerializerMethodField()
    due_date = serializers.DateField(allow_null=True)
    days_overdue = serializers.IntegerField(allow_null=True)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    bucket = serializers.CharField()

    def get_document_id(self, row):
        return row["document"].id

    def get_document_label(self, row):
        doc = row["document"]
        return getattr(doc, "invoice_number", None) or getattr(doc, "bill_number", "") or f"#{doc.id}"

    def get_party_id(self, row):
        return row["party"].id

    def get_party_name(self, row):
        return row["party"].name


class CollectionNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectionNote
        fields = [
            "id", "party_type", "customer", "supplier", "invoice", "purchase",
            "note", "follow_up_date", "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        party_type = attrs.get("party_type")
        customer = attrs.get("customer")
        supplier = attrs.get("supplier")

        if party_type == "customer" and not customer:
            raise serializers.ValidationError("customer is required when party_type='customer'.")
        if party_type == "supplier" and not supplier:
            raise serializers.ValidationError("supplier is required when party_type='supplier'.")
        if customer and customer.company_id != request.company.id:
            raise serializers.ValidationError("This customer does not belong to the active company.")
        if supplier and supplier.company_id != request.company.id:
            raise serializers.ValidationError("This supplier does not belong to the active company.")
        return attrs


class CustomerCreditStatusSerializer(serializers.Serializer):
    customer_id = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    credit_limit = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    available_credit = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    over_limit = serializers.BooleanField()

    def get_customer_id(self, obj):
        return obj["customer"].id

    def get_customer_name(self, obj):
        return obj["customer"].name

from rest_framework import serializers
from .models import Account, JournalEntry, JournalLine, FiscalYear


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "code", "name", "type", "parent", "is_system_account", "is_active"]
        read_only_fields = ["id", "is_system_account"]


class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ["id", "account", "debit", "credit", "description"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ["id", "date", "reference", "memo", "source_type", "source_id", "is_void", "lines"]
        read_only_fields = fields


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = [
            "id", "start_date", "end_date", "is_closed", "lock_date",
            "closed_at", "closed_by",
        ]
        read_only_fields = ["id", "is_closed", "closed_at", "closed_by"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and start >= end:
            raise serializers.ValidationError("start_date must be before end_date.")
        lock_date = attrs.get("lock_date")
        if lock_date and start and end and not (start <= lock_date <= end):
            raise serializers.ValidationError("lock_date must fall within the fiscal year.")
        return attrs

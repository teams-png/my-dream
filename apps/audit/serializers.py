from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "user_email", "action", "model_name",
            "object_id", "changes", "ip_address", "timestamp",
        ]
        read_only_fields = fields  # append-only ledger — no write endpoint at all (Section 28)

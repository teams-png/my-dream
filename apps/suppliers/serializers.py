from rest_framework import serializers
from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email", "address", "opening_balance", "is_active"]
        read_only_fields = ["id"]

from rest_framework import serializers
from .models import SportsProductDetail


class SportsProductDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SportsProductDetail
        fields = ["id", "product", "sport_category", "size", "gender", "material"]
        read_only_fields = ["id"]

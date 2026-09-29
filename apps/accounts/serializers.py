from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "username", "phone", "password"]

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data.get("username") or validated_data["email"],
            email=validated_data["email"],
            phone=validated_data.get("phone", ""),
            password=validated_data["password"],
        )


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "phone", "is_platform_admin"]
        read_only_fields = fields

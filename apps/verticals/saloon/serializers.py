from rest_framework import serializers
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.inventory.models import Warehouse

from .models import SaloonService, ServicePackage, CustomerPackage, Appointment


class SaloonServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaloonService
        fields = ["id", "name", "duration_minutes", "price", "is_active", "product"]
        read_only_fields = ["id", "product"]


class CreateSaloonServiceSerializer(serializers.Serializer):
    """Input for SaloonServiceViewSet.create — goes through saloon.services.create_saloon_service
    so the linked service Product is always created alongside the service."""
    name = serializers.CharField(max_length=150)
    duration_minutes = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class ServicePackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = ["id", "name", "service", "session_count", "price", "is_active", "product"]
        read_only_fields = ["id", "product"]


class CreateServicePackageSerializer(serializers.Serializer):
    """Input for ServicePackageViewSet.create — goes through saloon.services.create_service_package."""
    name = serializers.CharField(max_length=150)
    service = serializers.PrimaryKeyRelatedField(queryset=SaloonService.objects.all())
    session_count = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CustomerPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerPackage
        fields = ["id", "customer", "package", "purchased_on", "sessions_remaining"]
        read_only_fields = ["id", "sessions_remaining"]


class PurchasePackageSerializer(serializers.Serializer):
    """Input for CustomerPackageViewSet.create — goes through saloon.services.purchase_package,
    which invoices the package's price before the CustomerPackage row is created."""
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    package = serializers.PrimaryKeyRelatedField(queryset=ServicePackage.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    purchased_on = serializers.DateField()


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            "id", "customer", "service", "stylist", "customer_package",
            "scheduled_at", "status", "price", "commission_rate_percent",
        ]
        read_only_fields = ["id", "status"]


class BookAppointmentSerializer(serializers.Serializer):
    """Input for AppointmentViewSet.create — goes through saloon.services.book_appointment,
    which invoices a walk-in (no customer_package) before the Appointment row is created."""
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    service = serializers.PrimaryKeyRelatedField(queryset=SaloonService.objects.all())
    stylist = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    customer_package = serializers.PrimaryKeyRelatedField(
        queryset=CustomerPackage.objects.all(), required=False, allow_null=True,
    )
    scheduled_at = serializers.DateTimeField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    commission_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import SaloonService, ServicePackage, CustomerPackage, Appointment
from .serializers import (
    SaloonServiceSerializer, CreateSaloonServiceSerializer,
    ServicePackageSerializer, CreateServicePackageSerializer,
    CustomerPackageSerializer, PurchasePackageSerializer,
    AppointmentSerializer, BookAppointmentSerializer,
)
from . import services


def _require_saloon_module(request):
    return request.company.active_modules().filter(code="saloon").exists()


def _idor_guard(request, *objs):
    """Same pattern as apps.verticals.spa views — a client-supplied id only proves the row
    exists somewhere, not that it belongs to this tenant."""
    for obj in objs:
        if obj is not None and obj.company_id != request.company.id:
            return False
    return True


class SaloonServiceViewSet(viewsets.ModelViewSet):
    """Creation goes through saloon.services.create_saloon_service so every service
    gets its linked Product atomically — never a bare model write."""
    serializer_class = SaloonServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_saloon_module(self.request):
            return SaloonService.objects.none()
        return SaloonService.objects.for_company(self.request.company)

    def create(self, request, *args, **kwargs):
        serializer = CreateSaloonServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        svc = services.create_saloon_service(company=request.company, **serializer.validated_data)
        return Response(SaloonServiceSerializer(svc).data, status=201)


class ServicePackageViewSet(viewsets.ModelViewSet):
    """Creation goes through saloon.services.create_service_package for the same reason."""
    serializer_class = ServicePackageSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_saloon_module(self.request):
            return ServicePackage.objects.none()
        return ServicePackage.objects.for_company(self.request.company).select_related("service")

    def create(self, request, *args, **kwargs):
        serializer = CreateServicePackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not _idor_guard(request, data["service"]):
            return Response({"detail": "Invalid service for this company."}, status=400)
        pkg = services.create_service_package(company=request.company, **data)
        return Response(ServicePackageSerializer(pkg).data, status=201)


class CustomerPackageViewSet(viewsets.ModelViewSet):
    """Creation goes through saloon.services.purchase_package(), which invoices the package's
    price before the CustomerPackage row is created — a package is never active unpaid."""
    serializer_class = CustomerPackageSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "post"]

    def get_queryset(self):
        if not _require_saloon_module(self.request):
            return CustomerPackage.objects.none()
        return CustomerPackage.objects.for_company(self.request.company).select_related("customer", "package")

    def create(self, request, *args, **kwargs):
        serializer = PurchasePackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not _idor_guard(request, data["customer"], data["package"], data["warehouse"]):
            return Response({"detail": "Invalid customer, package, or warehouse for this company."}, status=400)
        cp = services.purchase_package(company=request.company, user=request.user, **data)
        return Response(CustomerPackageSerializer(cp).data, status=201)


class AppointmentViewSet(viewsets.ModelViewSet):
    """Creation goes through saloon.services.book_appointment(), which invoices walk-ins
    before the Appointment row is created (package-covered ones are already paid for)."""
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_saloon_module(self.request):
            return Appointment.objects.none()
        return Appointment.objects.for_company(self.request.company).select_related(
            "customer", "service", "stylist", "customer_package",
        )

    def create(self, request, *args, **kwargs):
        serializer = BookAppointmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not _idor_guard(
            request, data["customer"], data["service"], data["stylist"],
            data["warehouse"], data.get("customer_package"),
        ):
            return Response({"detail": "Invalid customer, service, stylist, warehouse, or package for this company."}, status=400)
        appt = services.book_appointment(company=request.company, user=request.user, **data)
        return Response(AppointmentSerializer(appt).data, status=201)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        appt = services.complete_appointment(self.get_object())
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        appt = services.cancel_appointment(self.get_object(), no_show=request.data.get("no_show", False))
        return Response(AppointmentSerializer(appt).data)

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Vehicle, WashPackage, WashOrder
from .serializers import (
    VehicleSerializer, WashPackageSerializer, CreateWashPackageSerializer,
    WashOrderSerializer, CompleteWashSerializer,
)
from . import services


def _require_vehicle_wash_module(request):
    return request.company.active_modules().filter(code="vehicle_wash").exists()


def _idor_guard(request, *objs):
    """Same pattern as apps.verticals.spa/saloon/beauty_parlour/textile views."""
    for obj in objs:
        if obj is not None and obj.company_id != request.company.id:
            return False
    return True


class VehicleViewSet(viewsets.ModelViewSet):
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_vehicle_wash_module(self.request):
            return Vehicle.objects.none()
        return Vehicle.objects.for_company(self.request.company).select_related("customer")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class WashPackageViewSet(viewsets.ModelViewSet):
    """Creation goes through vehicle_wash.services.create_wash_package so every
    package gets its linked Product atomically — never a bare model write."""
    serializer_class = WashPackageSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_vehicle_wash_module(self.request):
            return WashPackage.objects.none()
        return WashPackage.objects.for_company(self.request.company)

    def create(self, request, *args, **kwargs):
        serializer = CreateWashPackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pkg = services.create_wash_package(company=request.company, **serializer.validated_data)
        return Response(WashPackageSerializer(pkg).data, status=201)


class WashOrderViewSet(viewsets.ModelViewSet):
    """Creation goes through services.book_wash() (no invoice yet — a wash bills on
    completion); status changes via explicit actions, not raw PATCH."""
    serializer_class = WashOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_vehicle_wash_module(self.request):
            return WashOrder.objects.none()
        return WashOrder.objects.for_company(self.request.company).select_related("vehicle", "package", "staff")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.book_wash(company=request.company, **serializer.validated_data)
        return Response(WashOrderSerializer(order).data, status=201)

    def _transition(self, request, pk, fn):
        order = self.get_object()
        try:
            fn(order)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(WashOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._transition(request, pk, services.start_wash)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        order = self.get_object()
        serializer = CompleteWashSerializer(data=request.data, company=request.company)
        serializer.is_valid(raise_exception=True)
        warehouse = serializer.validated_data["warehouse"]
        try:
            services.complete_wash(order, user=request.user, warehouse=warehouse)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(WashOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(request, pk, services.cancel_wash)

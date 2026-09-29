from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import FabricDetail, Measurement, TailoringOrder
from .serializers import (
    FabricDetailSerializer, MeasurementSerializer,
    TailoringOrderSerializer, CreateTailoringOrderSerializer,
)
from .services import create_tailoring_order, mark_ready, mark_delivered


def _require_textile_module(request):
    return request.company.active_modules().filter(code="textile").exists()


def _idor_guard(request, *objs):
    """Same pattern as apps.verticals.spa/saloon/beauty_parlour views."""
    for obj in objs:
        if obj is not None and obj.company_id != request.company.id:
            return False
    return True


class FabricDetailViewSet(viewsets.ModelViewSet):
    serializer_class = FabricDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_textile_module(self.request):
            return FabricDetail.objects.none()
        return FabricDetail.objects.for_company(self.request.company).select_related("product")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class MeasurementViewSet(viewsets.ModelViewSet):
    serializer_class = MeasurementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_textile_module(self.request):
            return Measurement.objects.none()
        return Measurement.objects.for_company(self.request.company).select_related("customer")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class TailoringOrderViewSet(viewsets.ModelViewSet):
    """
    Creation goes through services.create_tailoring_order(), which now
    invoices the order's price (against a shared per-company "Tailoring
    Service" placeholder Product) before the order row is created — see
    the module docstring in services.py for why a shared Product rather
    than one per order.
    """
    serializer_class = TailoringOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_textile_module(self.request):
            return TailoringOrder.objects.none()
        return TailoringOrder.objects.for_company(self.request.company).select_related("customer", "measurement")

    def create(self, request, *args, **kwargs):
        serializer = CreateTailoringOrderSerializer(data=request.data, company=request.company)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not _idor_guard(
            request, data["customer"], data.get("measurement"), data.get("fabric_product"), data["warehouse"],
        ):
            return Response({"detail": "Invalid customer, measurement, fabric product, or warehouse for this company."}, status=400)
        order = create_tailoring_order(company=request.company, user=request.user, **data)
        return Response(TailoringOrderSerializer(order).data, status=201)

    @action(detail=True, methods=["post"])
    def ready(self, request, pk=None):
        order = self.get_object()
        mark_ready(order)
        return Response(TailoringOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        order = self.get_object()
        delivered_date = request.data.get("delivered_date")
        mark_delivered(order, delivered_date)
        return Response(TailoringOrderSerializer(order).data)

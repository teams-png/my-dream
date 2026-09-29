from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CycleUnit, ServiceTicket
from .serializers import (
    CycleUnitSerializer, SellCycleUnitSerializer,
    ServiceTicketSerializer, CompleteServiceSerializer, DeliverServiceSerializer,
)
from . import services


def _require_cycle_shop_module(request):
    return request.company.active_modules().filter(code="cycle_shop").exists()


class CycleUnitViewSet(viewsets.ModelViewSet):
    serializer_class = CycleUnitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_cycle_shop_module(self.request):
            return CycleUnit.objects.none()
        qs = CycleUnit.objects.for_company(self.request.company).select_related("product", "buyer")
        status = self.request.query_params.get("status")
        return qs.filter(status=status) if status else qs

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, status="in_stock")

    @action(detail=True, methods=["post"])
    def sell(self, request, pk=None):
        unit = self.get_object()
        payload = SellCycleUnitSerializer(data=request.data, company=request.company)
        payload.is_valid(raise_exception=True)
        try:
            services.sell_unit(unit, company=request.company, user=request.user, **payload.validated_data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(CycleUnitSerializer(unit).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_sale(self, request, pk=None):
        unit = self.get_object()
        try:
            services.return_unit(unit)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(CycleUnitSerializer(unit).data)


class ServiceTicketViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceTicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_cycle_shop_module(self.request):
            return ServiceTicket.objects.none()
        return ServiceTicket.objects.for_company(self.request.company).select_related(
            "customer", "cycle_unit", "staff",
        )

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        ticket = self.get_object()
        try:
            services.start_service(ticket)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(ServiceTicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        ticket = self.get_object()
        payload = CompleteServiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.complete_service(ticket, **payload.validated_data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(ServiceTicketSerializer(ticket).data)

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        ticket = self.get_object()
        payload = DeliverServiceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.deliver_service(ticket, **payload.validated_data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(ServiceTicketSerializer(ticket).data)

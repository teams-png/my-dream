from rest_framework import serializers, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.customers.models import Customer
from apps.inventory.models import Warehouse

from .models import MobileUnit, MobileRepairJob, MobileTradeIn
from .serializers import MobileUnitSerializer, MobileRepairJobSerializer, MobileTradeInSerializer
from . import services


def _require_mobile_shop_module(request):
    return request.company.active_modules().filter(code="mobile_shop").exists()


class SellUnitSerializer(serializers.Serializer):
    """
    Validates/parses the sell action's input (dates and decimals as real
    Python types, not raw request strings) before it reaches
    services.sell_unit — a bug in the first draft passed raw strings
    straight through, which silently broke MobileUnit.warranty_expires.
    """
    buyer = serializers.PrimaryKeyRelatedField(required=False, allow_null=True, queryset=Customer.objects.none())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    sold_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    sold_date = serializers.DateField()

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["buyer"].queryset = Customer.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company)


class MobileUnitViewSet(viewsets.ModelViewSet):
    """
    Status changes go through explicit actions (sell/return/repair), never
    a raw PATCH on `status` — an IMEI's lifecycle matters for warranty and
    resale-return rules, so it's modeled as transitions, not a free field.
    """
    serializer_class = MobileUnitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_mobile_shop_module(self.request):
            return MobileUnit.objects.none()
        qs = MobileUnit.objects.for_company(self.request.company).select_related("product", "buyer")
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, status="in_stock")

    @action(detail=True, methods=["post"])
    def sell(self, request, pk=None):
        unit = self.get_object()
        payload = SellUnitSerializer(data=request.data, company=request.company)
        payload.is_valid(raise_exception=True)
        try:
            services.sell_unit(unit, company=request.company, user=request.user, **payload.validated_data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(MobileUnitSerializer(unit).data)

    @action(detail=True, methods=["post"])
    def return_sale(self, request, pk=None):
        unit = self.get_object()
        try:
            services.return_unit(unit, company=request.company, user=request.user,
                                 date=request.data.get("date"), refund_method=request.data.get("refund_method", "cash"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(MobileUnitSerializer(unit).data)


class MobileRepairJobViewSet(viewsets.ModelViewSet):
    serializer_class = MobileRepairJobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MobileRepairJob.objects.for_company(self.request.company).select_related("customer", "mobile_unit", "invoice")

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            job = services.create_repair_job(
                company=request.company, customer=data["customer"], warehouse=data["warehouse"],
                device_description=data["device_description"], reported_issue=data["reported_issue"],
                mobile_unit=data.get("mobile_unit"), imei=data.get("imei", ""),
                estimated_cost=data.get("estimated_cost", 0), service_product=data.get("service_product"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(job).data, status=201)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        try:
            job = services.complete_repair_job(
                company=request.company, user=request.user, job=self.get_object(), date=request.data.get("date"),
                final_cost=request.data.get("final_cost", "0"), work_done=request.data.get("work_done", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(job).data)


class MobileTradeInViewSet(viewsets.ModelViewSet):
    serializer_class = MobileTradeInSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MobileTradeIn.objects.for_company(self.request.company).select_related("customer", "product", "purchase", "mobile_unit")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        trade_in = self.get_object()
        if request.data.get("accepted_value") is not None:
            trade_in.accepted_value = request.data["accepted_value"]
            trade_in.save(update_fields=["accepted_value"])
        try:
            trade_in = services.accept_trade_in(company=request.company, user=request.user, trade_in=trade_in, date=request.data.get("date"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(trade_in).data)

    @action(detail=True, methods=["post"])
    def send_for_repair(self, request, pk=None):
        unit = services.send_for_repair(self.get_object())
        return Response(MobileUnitSerializer(unit).data)

    @action(detail=True, methods=["post"])
    def restock(self, request, pk=None):
        unit = services.restock_after_repair(self.get_object())
        return Response(MobileUnitSerializer(unit).data)

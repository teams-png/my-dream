from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import MedicineBatch, DispenseRecord
from .serializers import MedicineBatchSerializer, DispenseRecordSerializer, DispenseActionSerializer
from . import services


def _require_medical_shop_module(request):
    return request.company.active_modules().filter(code="medical_shop").exists()


class MedicineBatchViewSet(viewsets.ModelViewSet):
    serializer_class = MedicineBatchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_medical_shop_module(self.request):
            return MedicineBatch.objects.none()
        qs = MedicineBatch.objects.for_company(self.request.company).select_related("product")
        expiring_within = self.request.query_params.get("expiring_within_days")
        if expiring_within:
            from datetime import timedelta
            from django.utils import timezone
            cutoff = timezone.localdate() + timedelta(days=int(expiring_within))
            qs = qs.filter(expiry_date__lte=cutoff, quantity_remaining__gt=0)
        return qs.order_by("expiry_date")  # FEFO by default

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["post"])
    def dispense(self, request, pk=None):
        batch = self.get_object()
        payload = DispenseActionSerializer(data=request.data, company=request.company)
        payload.is_valid(raise_exception=True)
        try:
            record = services.dispense(batch, company=request.company, user=request.user, **payload.validated_data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(DispenseRecordSerializer(record).data, status=201)


class DispenseRecordViewSet(viewsets.ModelViewSet):
    serializer_class = DispenseRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "post"]

    def get_queryset(self):
        if not _require_medical_shop_module(self.request):
            return DispenseRecord.objects.none()
        return DispenseRecord.objects.for_company(self.request.company).select_related("batch", "customer")

    @action(detail=True, methods=["post"], url_path="return")
    def return_record(self, request, pk=None):
        record = self.get_object()
        try:
            services.return_dispense(record)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        return Response(DispenseRecordSerializer(record).data)

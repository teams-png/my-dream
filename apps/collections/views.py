from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.permissions import HasCompanyPermission
from apps.customers.models import Customer

from .models import AgeingBucket, CollectionNote
from .serializers import (
    AgeingBucketSerializer, AgeingSummarySerializer, AgeingDetailRowSerializer,
    CollectionNoteSerializer, CustomerCreditStatusSerializer,
)
from .services import (
    ar_ageing_summary, ar_ageing_detail, ap_ageing_summary, ap_ageing_detail,
    customer_credit_status, record_collection_note,
)


def _as_drf_error(exc):
    return DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))


class AgeingBucketViewSet(viewsets.ModelViewSet):
    """Lets an Owner/Accountant reconfigure the bucket edges. The four
    standard buckets are seeded at signup — this just allows editing
    them, not choosing whether they exist at all."""
    serializer_class = AgeingBucketSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "collections.view", "retrieve": "collections.view",
        "default": "collections.manage",
    }

    def get_queryset(self):
        return AgeingBucket.objects.for_company(self.request.company).order_by("order")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ARAgeingView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "collections.view"}

    def get(self, request):
        as_of = request.query_params.get("as_of")
        summary = ar_ageing_summary(request.company, as_of=as_of)
        return Response(AgeingSummarySerializer(summary).data)


class ARAgeingDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "collections.view"}

    def get(self, request):
        as_of = request.query_params.get("as_of")
        rows = ar_ageing_detail(request.company, as_of=as_of)
        return Response(AgeingDetailRowSerializer(rows, many=True).data)


class APAgeingView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "collections.view"}

    def get(self, request):
        as_of = request.query_params.get("as_of")
        summary = ap_ageing_summary(request.company, as_of=as_of)
        return Response(AgeingSummarySerializer(summary).data)


class APAgeingDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "collections.view"}

    def get(self, request):
        as_of = request.query_params.get("as_of")
        rows = ap_ageing_detail(request.company, as_of=as_of)
        return Response(AgeingDetailRowSerializer(rows, many=True).data)


class CustomerCreditStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "collections.view"}

    def get(self, request, customer_id):
        customer = Customer.objects.for_company(request.company).filter(id=customer_id).first()
        if not customer:
            return Response(status=404)
        try:
            status_data = customer_credit_status(request.company, customer)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(CustomerCreditStatusSerializer(status_data).data)


class CollectionNoteViewSet(viewsets.ModelViewSet):
    serializer_class = CollectionNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "collections.view", "retrieve": "collections.view",
        "default": "collections.manage",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        qs = CollectionNote.objects.for_company(self.request.company)
        customer_id = self.request.query_params.get("customer")
        supplier_id = self.request.query_params.get("supplier")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            note = record_collection_note(company=request.company, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(CollectionNoteSerializer(note).data, status=201)

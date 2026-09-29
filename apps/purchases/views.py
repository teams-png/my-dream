from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.permissions import HasCompanyPermission

from .models import Purchase, PurchaseOrder, GoodsReceiptNote
from .serializers import (
    PurchaseSerializer, CreatePurchaseInputSerializer, SupplierPaymentSerializer,
    PurchaseReturnSerializer, ProcessPurchaseReturnInputSerializer,
    PurchaseOrderSerializer, CreatePurchaseOrderInputSerializer,
    GoodsReceiptNoteSerializer, CreateGoodsReceiptInputSerializer, CreateBillFromGrnInputSerializer,
)
from .services import (
    create_purchase, record_supplier_payment, process_purchase_return,
    create_purchase_order, confirm_purchase_order, cancel_purchase_order,
    create_goods_receipt, create_bill_from_grn,
)


def _as_drf_error(exc):
    return DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))


def _has_override_permission(request):
    return request.role.permissions.filter(permission__code="purchases.override_receiving_limits").exists()


class PurchaseViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "purchases.view_purchase", "retrieve": "purchases.view_purchase",
        "create": "purchases.create_purchase", "record_payment": "purchases.create_purchase",
        "record_return": "purchases.create_purchase",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return Purchase.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        input_serializer = CreatePurchaseInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        # IDOR guard — see sales/views.py for the same pattern and rationale.
        if data["supplier"].company_id != request.company.id or data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid supplier or warehouse for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        purchase = create_purchase(
            company=request.company, user=request.user, supplier=data["supplier"],
            date=data["date"], bill_number=data.get("bill_number", ""),
            warehouse=data["warehouse"], tax_rate=data.get("tax_rate", 0), lines=data["lines"],
        )
        return Response(PurchaseSerializer(purchase).data, status=201)

    @action(detail=True, methods=["post"])
    def record_payment(self, request, pk=None):
        purchase = self.get_object()
        serializer = SupplierPaymentSerializer(
            data={**request.data, "supplier": purchase.supplier_id, "purchase": purchase.id}
        )
        serializer.is_valid(raise_exception=True)
        payment = record_supplier_payment(
            company=request.company, user=request.user, supplier=purchase.supplier,
            purchase=purchase, amount=serializer.validated_data["amount"],
            date=serializer.validated_data["date"], method=serializer.validated_data.get("method", "cash"),
        )
        return Response(SupplierPaymentSerializer(payment).data, status=201)

    @action(detail=True, methods=["post"])
    def record_return(self, request, pk=None):
        purchase = self.get_object()
        input_serializer = ProcessPurchaseReturnInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        # IDOR guard — same pattern as create(): warehouse/product ids must belong to this tenant.
        if data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid warehouse for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        purchase_return = process_purchase_return(
            company=request.company, user=request.user, purchase=purchase,
            date=data["date"], warehouse=data["warehouse"], reason=data.get("reason", ""),
            refund_method=data.get("refund_method", "supplier_credit"), lines=data["lines"],
        )
        return Response(PurchaseReturnSerializer(purchase_return).data, status=201)


# ---------------------------------------------------------------- Phase 32


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "purchases.view_purchase", "retrieve": "purchases.view_purchase",
        "default": "purchases.create_purchase",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return PurchaseOrder.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        input_serializer = CreatePurchaseOrderInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        if data["supplier"].company_id != request.company.id:
            return Response({"detail": "Invalid supplier for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        try:
            po = create_purchase_order(
                company=request.company, user=request.user, supplier=data["supplier"],
                date=data["date"], reference=data.get("reference", ""), lines=data["lines"],
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PurchaseOrderSerializer(po).data, status=201)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        po = self.get_object()
        try:
            confirm_purchase_order(company=request.company, purchase_order=po)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        po.refresh_from_db()
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        po = self.get_object()
        try:
            cancel_purchase_order(company=request.company, purchase_order=po)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        po.refresh_from_db()
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        po = self.get_object()
        serializer = CreateGoodsReceiptInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid warehouse for this company."}, status=400)
        if data.get("allow_over_receipt") and not _has_override_permission(request):
            raise PermissionDenied("Only a role with purchases.override_receiving_limits can over-receive.")

        try:
            grn = create_goods_receipt(
                company=request.company, user=request.user, purchase_order=po,
                warehouse=data["warehouse"], date=data["date"], lines=data["lines"],
                allow_over_receipt=data.get("allow_over_receipt", False),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GoodsReceiptNoteSerializer(grn).data, status=201)

    @action(detail=True, methods=["post"], url_path="bill")
    def bill(self, request, pk=None):
        po = self.get_object()
        serializer = CreateBillFromGrnInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("allow_over_billing") and not _has_override_permission(request):
            raise PermissionDenied("Only a role with purchases.override_receiving_limits can over-bill.")

        try:
            purchase = create_bill_from_grn(
                company=request.company, user=request.user, purchase_order=po,
                lines=data["lines"], bill_number=data.get("bill_number", ""), date=data["date"],
                tax_rate=data.get("tax_rate", 0), allow_over_billing=data.get("allow_over_billing", False),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PurchaseSerializer(purchase).data, status=201)


class GoodsReceiptNoteViewSet(viewsets.ReadOnlyModelViewSet):
    """Receipts are created only via PurchaseOrderViewSet.receive() — no
    generic create here, same pattern as StockMovementViewSet."""
    serializer_class = GoodsReceiptNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "purchases.view_purchase"}

    def get_queryset(self):
        qs = GoodsReceiptNote.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")
        po_id = self.request.query_params.get("purchase_order")
        if po_id:
            qs = qs.filter(purchase_order_id=po_id)
        return qs

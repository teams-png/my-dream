from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.permissions import HasCompanyPermission

from .models import (SalesInvoice, Quotation, SalesOrder, DeliveryNote, POSShift, POSReceipt,
                     PriceList, Promotion, CommercialSettings, ExchangeRate, TaxScheme, TaxCode)
from .serializers import (
    SalesInvoiceSerializer, CreateInvoiceInputSerializer, CustomerPaymentSerializer,
    SalesReturnSerializer, ProcessReturnInputSerializer,
    QuotationSerializer, CreateQuotationInputSerializer,
    SalesOrderSerializer, CreateSalesOrderInputSerializer,
    DeliveryNoteSerializer, CreateDeliveryInputSerializer, CreateInvoiceFromOrderInputSerializer,
    POSShiftSerializer, POSCartSerializer, POSReceiptSerializer, OpenPOSShiftInputSerializer,
    CompletePOSSaleInputSerializer, HoldPOSCartInputSerializer, POSCashMovementInputSerializer,
    ClosePOSShiftInputSerializer,
    PriceListSerializer, PromotionSerializer, CommercialSettingsSerializer, ExchangeRateSerializer,
    TaxSchemeSerializer, TaxCodeSerializer,
)
from .services import (
    create_invoice, record_customer_payment, process_return,
    create_quotation, send_quotation, accept_quotation, reject_quotation,
    create_sales_order, confirm_sales_order, cancel_sales_order,
    create_delivery, create_invoice_from_order,
    open_pos_shift, hold_pos_cart, complete_pos_sale, add_pos_cash_movement, close_pos_shift,
)


def _as_drf_error(exc):
    return DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))


def _has_override_permission(request):
    return request.role.permissions.filter(permission__code="sales.override_delivery_limits").exists()


class SalesInvoiceViewSet(viewsets.ModelViewSet):
    """
    Creation goes through the `create/` action below, not the default DRF
    create — invoices are never a bare model write, always the atomic
    services.create_invoice() call (Phase 0 Section 1).
    """
    serializer_class = SalesInvoiceSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "sales.view_invoice", "retrieve": "sales.view_invoice",
        "create": "sales.create_invoice", "record_payment": "sales.create_invoice",
        "record_return": "sales.create_invoice",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return SalesInvoice.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        input_serializer = CreateInvoiceInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        # PrimaryKeyRelatedField only proves the id exists SOMEWHERE — it does
        # not scope to this tenant. This explicit check is the IDOR guard
        # required by Phase 0 Section 3/38: never trust a client-supplied id
        # without confirming it belongs to request.company.
        if data["customer"].company_id != request.company.id or data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid customer or warehouse for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)
            if line.get("tax_code") and line["tax_code"].company_id != request.company.id:
                return Response({"detail": "Invalid tax code for this company."}, status=400)

        invoice = create_invoice(
            company=request.company, user=request.user, customer=data["customer"],
            date=data["date"], due_date=data.get("due_date"), warehouse=data["warehouse"],
            tax_rate=data.get("tax_rate", 0), lines=data["lines"],
            discount_amount=data.get("discount_amount", 0),
            discount_reason=data.get("discount_reason", ""),
            currency=data.get("currency"), exchange_rate=data.get("exchange_rate"),
            discount_approved_by=(request.user if data.get("discount_amount") and
                request.role.permissions.filter(permission__code="sales.approve_discount").exists() else None),
        )
        return Response(SalesInvoiceSerializer(invoice).data, status=201)

    @action(detail=True, methods=["post"])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        serializer = CustomerPaymentSerializer(data={**request.data, "customer": invoice.customer_id, "invoice": invoice.id})
        serializer.is_valid(raise_exception=True)
        payment = record_customer_payment(
            company=request.company, user=request.user, customer=invoice.customer,
            invoice=invoice, amount=serializer.validated_data["amount"],
            date=serializer.validated_data["date"], method=serializer.validated_data.get("method", "cash"),
            currency=serializer.validated_data.get("currency"),
            exchange_rate=serializer.validated_data.get("exchange_rate"),
        )
        return Response(CustomerPaymentSerializer(payment).data, status=201)

    @action(detail=True, methods=["post"])
    def record_return(self, request, pk=None):
        invoice = self.get_object()
        input_serializer = ProcessReturnInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        # IDOR guard — same pattern as create(): warehouse/product ids must belong to this tenant.
        if data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid warehouse for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        sales_return = process_return(
            company=request.company, user=request.user, invoice=invoice,
            date=data["date"], warehouse=data["warehouse"], reason=data.get("reason", ""),
            refund_method=data.get("refund_method", "cash"), lines=data["lines"],
        )
        return Response(SalesReturnSerializer(sales_return).data, status=201)


# ---------------------------------------------------------------- Phase 33


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "sales.view_invoice", "retrieve": "sales.view_invoice",
        "default": "sales.create_invoice",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return Quotation.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        input_serializer = CreateQuotationInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        if data["customer"].company_id != request.company.id:
            return Response({"detail": "Invalid customer for this company."}, status=400)
        for line in data["lines"]:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        try:
            quotation = create_quotation(
                company=request.company, user=request.user, customer=data["customer"],
                date=data["date"], notes=data.get("notes", ""), lines=data["lines"],
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(QuotationSerializer(quotation).data, status=201)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        quotation = self.get_object()
        try:
            send_quotation(company=request.company, quotation=quotation)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        quotation = self.get_object()
        try:
            accept_quotation(company=request.company, quotation=quotation)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        quotation = self.get_object()
        try:
            reject_quotation(company=request.company, quotation=quotation)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        quotation.refresh_from_db()
        return Response(QuotationSerializer(quotation).data)


class SalesOrderViewSet(viewsets.ModelViewSet):
    serializer_class = SalesOrderSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "sales.view_invoice", "retrieve": "sales.view_invoice",
        "default": "sales.create_invoice",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return SalesOrder.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        input_serializer = CreateSalesOrderInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        if data["customer"].company_id != request.company.id:
            return Response({"detail": "Invalid customer for this company."}, status=400)
        quotation = data.get("quotation")
        if quotation and quotation.company_id != request.company.id:
            return Response({"detail": "Invalid quotation for this company."}, status=400)
        for line in data.get("lines") or []:
            if line["product"].company_id != request.company.id:
                return Response({"detail": "Invalid product for this company."}, status=400)

        try:
            order = create_sales_order(
                company=request.company, user=request.user, customer=data["customer"],
                date=data["date"], reference=data.get("reference", ""),
                quotation=quotation, lines=data.get("lines") or None,
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(SalesOrderSerializer(order).data, status=201)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = self.get_object()
        try:
            confirm_sales_order(company=request.company, sales_order=order)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        order.refresh_from_db()
        return Response(SalesOrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            cancel_sales_order(company=request.company, sales_order=order)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        order.refresh_from_db()
        return Response(SalesOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="deliver")
    def deliver(self, request, pk=None):
        order = self.get_object()
        serializer = CreateDeliveryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["warehouse"].company_id != request.company.id:
            return Response({"detail": "Invalid warehouse for this company."}, status=400)
        if data.get("allow_over_delivery") and not _has_override_permission(request):
            raise PermissionDenied("Only a role with sales.override_delivery_limits can over-deliver.")

        try:
            delivery = create_delivery(
                company=request.company, user=request.user, sales_order=order,
                warehouse=data["warehouse"], date=data["date"], lines=data["lines"],
                allow_over_delivery=data.get("allow_over_delivery", False),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(DeliveryNoteSerializer(delivery).data, status=201)

    @action(detail=True, methods=["post"], url_path="invoice")
    def invoice(self, request, pk=None):
        order = self.get_object()
        serializer = CreateInvoiceFromOrderInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("allow_over_invoicing") and not _has_override_permission(request):
            raise PermissionDenied("Only a role with sales.override_delivery_limits can over-invoice.")

        try:
            invoice = create_invoice_from_order(
                company=request.company, user=request.user, sales_order=order,
                lines=data["lines"], date=data["date"], due_date=data.get("due_date"),
                tax_rate=data.get("tax_rate", 0), allow_over_invoicing=data.get("allow_over_invoicing", False),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(SalesInvoiceSerializer(invoice).data, status=201)


class DeliveryNoteViewSet(viewsets.ReadOnlyModelViewSet):
    """Deliveries are created only via SalesOrderViewSet.deliver() — no
    generic create here, same pattern as GoodsReceiptNoteViewSet."""
    serializer_class = DeliveryNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "sales.view_invoice"}

    def get_queryset(self):
        qs = DeliveryNote.objects.for_company(self.request.company).prefetch_related("lines").order_by("-date", "-id")
        so_id = self.request.query_params.get("sales_order")
        if so_id:
            qs = qs.filter(sales_order_id=so_id)
        return qs


class POSViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "sales.create_invoice"}

    def get_queryset(self):
        return POSShift.objects.for_company(self.request.company).filter(cashier=self.request.user)

    @action(detail=False, methods=["post"], url_path="open-shift")
    def open_shift(self, request):
        serializer = OpenPOSShiftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            shift = open_pos_shift(company=request.company, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(POSShiftSerializer(shift).data, status=201)

    @action(detail=True, methods=["post"], url_path="hold-cart")
    def hold_cart(self, request, pk=None):
        shift = self.get_object()
        serializer = HoldPOSCartInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = hold_pos_cart(company=request.company, user=request.user, shift=shift, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(POSCartSerializer(cart).data, status=201)

    @action(detail=True, methods=["post"], url_path="checkout")
    def checkout(self, request, pk=None):
        shift = self.get_object()
        serializer = CompletePOSSaleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("discount_amount") and request.role.permissions.filter(
                permission__code="sales.approve_discount").exists():
            data["discount_approved_by"] = request.user
        try:
            receipt = complete_pos_sale(company=request.company, user=request.user, shift=shift, **data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(POSReceiptSerializer(receipt).data, status=201)

    @action(detail=True, methods=["post"], url_path="cash-movement")
    def cash_movement(self, request, pk=None):
        shift = self.get_object()
        serializer = POSCashMovementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movement = add_pos_cash_movement(company=request.company, user=request.user, shift=shift,
                                             **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response({"id": movement.id}, status=201)

    @action(detail=True, methods=["post"], url_path="close-shift")
    def close_shift(self, request, pk=None):
        shift = self.get_object()
        serializer = ClosePOSShiftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            shift = close_pos_shift(company=request.company, user=request.user, shift=shift,
                                    **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(POSShiftSerializer(shift).data)

    @action(detail=False, methods=["get"], url_path=r"receipts/(?P<receipt_number>[^/.]+)")
    def receipt(self, request, receipt_number=None):
        receipt = POSReceipt.objects.for_company(request.company).prefetch_related("payments").filter(
            receipt_number=receipt_number
        ).first()
        if receipt is None:
            return Response({"detail": "Receipt not found."}, status=404)
        return Response(POSReceiptSerializer(receipt).data)


class PriceListViewSet(viewsets.ModelViewSet):
    serializer_class = PriceListSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "sales.create_invoice"}

    def get_queryset(self):
        return PriceList.objects.for_company(self.request.company).prefetch_related("items")


class PromotionViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "sales.create_invoice"}

    def get_queryset(self):
        return Promotion.objects.for_company(self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class CommercialSettingsViewSet(viewsets.GenericViewSet):
    serializer_class = CommercialSettingsSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "sales.create_invoice"}

    def list(self, request):
        obj, _ = CommercialSettings.objects.get_or_create(company=request.company)
        return Response(self.get_serializer(obj).data)

    @action(detail=False, methods=["patch"])
    def update_settings(self, request):
        obj, _ = CommercialSettings.objects.get_or_create(company=request.company)
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ExchangeRateViewSet(viewsets.ModelViewSet):
    serializer_class = ExchangeRateSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.post_journal_entry"}

    def get_queryset(self):
        return ExchangeRate.objects.for_company(self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, currency=serializer.validated_data["currency"].upper())


class TaxSchemeViewSet(viewsets.ModelViewSet):
    serializer_class = TaxSchemeSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.post_journal_entry"}
    def get_queryset(self):
        return TaxScheme.objects.for_company(self.request.company)
    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class TaxCodeViewSet(viewsets.ModelViewSet):
    serializer_class = TaxCodeSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.post_journal_entry"}
    def get_queryset(self):
        return TaxCode.objects.for_company(self.request.company).select_related("scheme")
    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.permissions import HasCompanyPermission
from .models import (
    ProductCategory, Brand, Unit, Warehouse, Product, StockMovement,
    ProductBatch, ProductSerial, StockCount,
)
from .serializers import (
    ProductCategorySerializer, BrandSerializer, UnitSerializer,
    WarehouseSerializer, ProductSerializer, StockMovementSerializer,
    ProductBatchSerializer, ProductSerialSerializer, StockCountSerializer,
    StockCountLineSerializer, StartStockCountInputSerializer, SubmitStockCountLineInputSerializer,
    StockTransferInputSerializer, StockAdjustmentInputSerializer,
)
from .services import (
    start_stock_count, submit_stock_count_line, complete_stock_count,
    create_stock_transfer, create_stock_adjustment,
)


def _as_drf_error(exc):
    return DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))


class _CompanyScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.manage_products", "list": "inventory.view_products", "retrieve": "inventory.view_products"}

    def get_queryset(self):
        return self.model.objects.for_company(self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ProductCategoryViewSet(_CompanyScopedViewSet):
    model = ProductCategory
    serializer_class = ProductCategorySerializer


class BrandViewSet(_CompanyScopedViewSet):
    model = Brand
    serializer_class = BrandSerializer


class UnitViewSet(_CompanyScopedViewSet):
    model = Unit
    serializer_class = UnitSerializer


class WarehouseViewSet(_CompanyScopedViewSet):
    model = Warehouse
    serializer_class = WarehouseSerializer


class ProductViewSet(_CompanyScopedViewSet):
    model = Product
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.for_company(self.request.company).select_related("category", "brand", "unit")


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only from the API — writes only happen via inventory.services.record_stock_movement,
    called from other apps' services (sales, purchases, manual adjustment endpoint TBD)."""
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.view_products"}

    def get_queryset(self):
        return StockMovement.objects.for_company(self.request.company).order_by("-moved_at")


class ProductBatchViewSet(viewsets.ModelViewSet):
    serializer_class = ProductBatchSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.manage_stock", "list": "inventory.view_products", "retrieve": "inventory.view_products"}

    def get_queryset(self):
        qs = ProductBatch.objects.for_company(self.request.company).select_related("product")
        product_id = self.request.query_params.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ProductSerialViewSet(viewsets.ReadOnlyModelViewSet):
    """Serials are created via register_serial() (typically alongside a
    purchase), not a generic create — so this is read-only from the API,
    same pattern as StockMovementViewSet."""
    serializer_class = ProductSerialSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.view_products"}

    def get_queryset(self):
        qs = ProductSerial.objects.for_company(self.request.company).select_related("product", "warehouse")
        product_id = self.request.query_params.get("product")
        status_filter = self.request.query_params.get("status")
        if product_id:
            qs = qs.filter(product_id=product_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class StockCountViewSet(viewsets.ModelViewSet):
    serializer_class = StockCountSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "inventory.view_products", "retrieve": "inventory.view_products",
        "submit_line": "inventory.manage_stock", "complete": "inventory.manage_stock",
        "default": "inventory.manage_stock",
    }
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return StockCount.objects.for_company(self.request.company).prefetch_related("lines__product").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = StartStockCountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        warehouse = serializer.validated_data["warehouse"]
        product_ids = serializer.validated_data.get("product_ids")

        products_qs = Product.objects.for_company(request.company).filter(is_active=True, is_stock_tracked=True)
        if product_ids:
            products_qs = products_qs.filter(id__in=product_ids)

        try:
            stock_count = start_stock_count(company=request.company, user=request.user, warehouse=warehouse, products=list(products_qs))
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(StockCountSerializer(stock_count).data, status=201)

    @action(detail=True, methods=["post"], url_path="lines/(?P<line_id>[^/.]+)")
    def submit_line(self, request, pk=None, line_id=None):
        stock_count = self.get_object()
        line = stock_count.lines.filter(id=line_id).first()
        if not line:
            return Response(status=404)
        serializer = SubmitStockCountLineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submit_stock_count_line(company=request.company, stock_count_line=line, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(StockCountLineSerializer(line).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        stock_count = self.get_object()
        try:
            complete_stock_count(company=request.company, user=request.user, stock_count=stock_count)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        stock_count.refresh_from_db()
        return Response(StockCountSerializer(stock_count).data)


class StockTransferView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.manage_stock"}

    def post(self, request):
        serializer = StockTransferInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            out_move, in_move = create_stock_transfer(company=request.company, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response({
            "transfer_out": StockMovementSerializer(out_move).data,
            "transfer_in": StockMovementSerializer(in_move).data,
        }, status=201)


class StockAdjustmentView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "inventory.manage_stock"}

    def post(self, request):
        serializer = StockAdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movement = create_stock_adjustment(company=request.company, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(StockMovementSerializer(movement).data, status=201)

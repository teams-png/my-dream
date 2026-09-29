from rest_framework import viewsets, permissions
from apps.tenants.permissions import HasCompanyPermission
from .models import Supplier
from .serializers import SupplierSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "suppliers.manage"}

    def get_queryset(self):
        return Supplier.objects.for_company(self.request.company).order_by("name")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

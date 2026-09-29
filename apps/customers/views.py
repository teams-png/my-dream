from rest_framework import viewsets, permissions
from apps.tenants.permissions import HasCompanyPermission
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "customers.manage"}

    def get_queryset(self):
        return Customer.objects.for_company(self.request.company).order_by("name")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

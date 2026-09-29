from rest_framework import viewsets, permissions
from rest_framework.response import Response

from apps.tenants.permissions import HasCompanyPermission

from .models import ExpenseCategory, Expense
from .serializers import ExpenseCategorySerializer, ExpenseSerializer
from .services import record_expense


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "expenses.manage", "list": "expenses.view", "retrieve": "expenses.view"}

    def get_queryset(self):
        return ExpenseCategory.objects.for_company(self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ExpenseViewSet(viewsets.ModelViewSet):
    """Creation goes through services.record_expense so every expense posts a journal entry."""
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "expenses.manage", "list": "expenses.view", "retrieve": "expenses.view", "create": "expenses.manage"}
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return Expense.objects.for_company(self.request.company).order_by("-date", "-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = record_expense(company=request.company, user=request.user, **serializer.validated_data)
        return Response(ExpenseSerializer(expense).data, status=201)

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Project, Contractor, ProjectAssignment, ProjectExpense
from .serializers import (
    ProjectSerializer, ContractorSerializer,
    ProjectAssignmentSerializer, ProjectExpenseSerializer,
)
from .services import record_project_expense, project_summary


def _require_construction_module(request):
    return request.company.active_modules().filter(code="construction").exists()


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_construction_module(self.request):
            return Project.objects.none()
        return Project.objects.for_company(self.request.company).select_related("client")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        return Response(project_summary(self.get_object()))


class ContractorViewSet(viewsets.ModelViewSet):
    serializer_class = ContractorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_construction_module(self.request):
            return Contractor.objects.none()
        return Contractor.objects.for_company(self.request.company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ProjectAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_construction_module(self.request):
            return ProjectAssignment.objects.none()
        return ProjectAssignment.objects.for_company(self.request.company).select_related("project", "employee")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ProjectExpenseViewSet(viewsets.ModelViewSet):
    """Creation goes through services.record_project_expense so every project cost still posts a journal entry."""
    serializer_class = ProjectExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if not _require_construction_module(self.request):
            return ProjectExpense.objects.none()
        return ProjectExpense.objects.for_company(self.request.company).select_related("project", "contractor")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = record_project_expense(company=request.company, user=request.user, **serializer.validated_data)
        return Response(ProjectExpenseSerializer(expense).data, status=201)

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.tenants.permissions import HasCompanyPermission
from .models import (Employee, Department, Designation, WorkShift, Attendance, LeaveType,
                     LeaveBalance, LeaveRequest, Holiday, EmployeeDocument, SalaryStructure,
                     OvertimeEntry, PayrollPeriod, PayrollRun, PayrollLine)
from .serializers import (EmployeeSerializer, DepartmentSerializer, DesignationSerializer,
    WorkShiftSerializer, AttendanceSerializer, LeaveTypeSerializer, LeaveBalanceSerializer,
    LeaveRequestSerializer, HolidaySerializer, EmployeeDocumentSerializer, SalaryStructureSerializer,
    OvertimeEntrySerializer, PayrollPeriodSerializer, PayrollRunSerializer, PayrollLineSerializer)
from .services import (request_leave, review_leave, record_attendance, submit_overtime,
                       review_overtime, create_payroll_run, post_payroll, reverse_payroll,
                       mark_payroll_paid)


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "employees.manage"}

    def get_queryset(self):
        return Employee.objects.for_company(self.request.company).order_by("name")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)


class ScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "employees.manage"}
    def get_queryset(self):
        return self.queryset_model.objects.for_company(self.request.company)

class DepartmentViewSet(ScopedModelViewSet): queryset_model=Department; serializer_class=DepartmentSerializer
class DesignationViewSet(ScopedModelViewSet): queryset_model=Designation; serializer_class=DesignationSerializer
class WorkShiftViewSet(ScopedModelViewSet): queryset_model=WorkShift; serializer_class=WorkShiftSerializer
class LeaveTypeViewSet(ScopedModelViewSet): queryset_model=LeaveType; serializer_class=LeaveTypeSerializer
class LeaveBalanceViewSet(ScopedModelViewSet): queryset_model=LeaveBalance; serializer_class=LeaveBalanceSerializer
class HolidayViewSet(ScopedModelViewSet): queryset_model=Holiday; serializer_class=HolidaySerializer
class EmployeeDocumentViewSet(ScopedModelViewSet): queryset_model=EmployeeDocument; serializer_class=EmployeeDocumentSerializer


class AttendanceViewSet(ScopedModelViewSet):
    queryset_model = Attendance
    serializer_class = AttendanceSerializer
    def perform_create(self, serializer):
        obj = record_attendance(company=self.request.company, **serializer.validated_data)
        serializer.instance = obj


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"create": "employees.self_service", "list": "employees.self_service",
                            "retrieve": "employees.self_service", "approve": "employees.manage",
                            "reject": "employees.manage"}
    http_method_names = ["get", "post", "head"]
    def get_queryset(self):
        qs = LeaveRequest.objects.for_company(self.request.company)
        if not self.request.role.permissions.filter(permission__code="employees.manage").exists():
            qs = qs.filter(employee__user=self.request.user)
        return qs
    def perform_create(self, serializer):
        employee = serializer.validated_data["employee"]
        if employee.user_id != self.request.user.id and not self.request.role.permissions.filter(permission__code="employees.manage").exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can request leave only for your own employee profile.")
        serializer.instance = request_leave(company=self.request.company, **serializer.validated_data)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = review_leave(company=request.company, request=self.get_object(), reviewer=request.user, approve=True)
        return Response(self.get_serializer(obj).data)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = review_leave(company=request.company, request=self.get_object(), reviewer=request.user, approve=False)
        return Response(self.get_serializer(obj).data)


class SalaryStructureViewSet(ScopedModelViewSet):
    queryset_model = SalaryStructure
    serializer_class = SalaryStructureSerializer
    required_permissions = {"default": "employees.manage_payroll"}


class OvertimeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = OvertimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"create": "employees.self_service", "list": "employees.self_service",
                            "retrieve": "employees.self_service", "approve": "employees.manage_payroll",
                            "reject": "employees.manage_payroll"}
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        qs = OvertimeEntry.objects.for_company(self.request.company).select_related("employee")
        if not self.request.role.permissions.filter(permission__code="employees.manage_payroll").exists():
            qs = qs.filter(employee__user=self.request.user)
        return qs.order_by("-date", "-id")

    def perform_create(self, serializer):
        employee = serializer.validated_data["employee"]
        can_manage = self.request.role.permissions.filter(permission__code="employees.manage_payroll").exists()
        if employee.user_id != self.request.user.id and not can_manage:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can submit overtime only for your own employee profile.")
        serializer.instance = submit_overtime(company=self.request.company, **serializer.validated_data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        obj = review_overtime(company=request.company, overtime=self.get_object(), reviewer=request.user, approve=True)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        obj = review_overtime(company=request.company, overtime=self.get_object(), reviewer=request.user, approve=False)
        return Response(self.get_serializer(obj).data)


class PayrollPeriodViewSet(ScopedModelViewSet):
    queryset_model = PayrollPeriod
    serializer_class = PayrollPeriodSerializer
    required_permissions = {"default": "employees.manage_payroll"}


class PayrollRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayrollRunSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "employees.manage_payroll"}

    def get_queryset(self):
        return PayrollRun.objects.for_company(self.request.company).select_related(
            "period", "created_by", "posted_by", "journal_entry", "reversal_journal_entry",
        ).prefetch_related("lines__employee").order_by("-period__start_date")

    def create(self, request, *args, **kwargs):
        period = PayrollPeriod.objects.for_company(request.company).get(pk=request.data.get("period"))
        obj = create_payroll_run(company=request.company, user=request.user, period=period)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        obj = post_payroll(company=request.company, user=request.user, payroll_run=self.get_object(),
                           date=request.data.get("date") or self.get_object().period.end_date)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        obj = reverse_payroll(company=request.company, user=request.user, payroll_run=self.get_object(),
                              date=request.data.get("date") or self.get_object().period.end_date)
        return Response(self.get_serializer(obj).data)


class PayrollLineViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayrollLineSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "employees.manage_payroll", "payslip": "employees.self_service",
                            "mark_paid": "employees.manage_payroll"}

    def get_queryset(self):
        qs = PayrollLine.objects.for_company(self.request.company).select_related("employee", "payroll_run__period")
        if self.action == "payslip" and not self.request.role.permissions.filter(permission__code="employees.manage_payroll").exists():
            qs = qs.filter(employee__user=self.request.user)
        return qs

    @action(detail=True, methods=["get"])
    def payslip(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        obj = mark_payroll_paid(company=request.company, payroll_line=self.get_object())
        return Response(self.get_serializer(obj).data)

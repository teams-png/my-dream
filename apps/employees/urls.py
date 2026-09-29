from rest_framework.routers import DefaultRouter
from .views import (EmployeeViewSet, DepartmentViewSet, DesignationViewSet, WorkShiftViewSet,
                    AttendanceViewSet, LeaveTypeViewSet, LeaveBalanceViewSet, LeaveRequestViewSet,
                    HolidayViewSet, EmployeeDocumentViewSet, SalaryStructureViewSet,
                    OvertimeEntryViewSet, PayrollPeriodViewSet, PayrollRunViewSet, PayrollLineViewSet)

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("departments", DepartmentViewSet, basename="department")
router.register("designations", DesignationViewSet, basename="designation")
router.register("shifts", WorkShiftViewSet, basename="work-shift")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("leave-types", LeaveTypeViewSet, basename="leave-type")
router.register("leave-balances", LeaveBalanceViewSet, basename="leave-balance")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register("holidays", HolidayViewSet, basename="holiday")
router.register("documents", EmployeeDocumentViewSet, basename="employee-document")
router.register("salary-structures", SalaryStructureViewSet, basename="salary-structure")
router.register("overtime", OvertimeEntryViewSet, basename="overtime-entry")
router.register("payroll-periods", PayrollPeriodViewSet, basename="payroll-period")
router.register("payroll-runs", PayrollRunViewSet, basename="payroll-run")
router.register("payslips", PayrollLineViewSet, basename="payroll-line")
router.register("", EmployeeViewSet, basename="employee-root")

urlpatterns = router.urls

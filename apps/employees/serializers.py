from rest_framework import serializers
from .models import (Employee, Department, Designation, WorkShift, Attendance, LeaveType,
                     LeaveBalance, LeaveRequest, Holiday, EmployeeDocument, SalaryStructure,
                     OvertimeEntry, PayrollPeriod, PayrollRun, PayrollLine)


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "name", "phone", "role_title", "salary", "joined_date", "leaving_date",
                  "is_active", "user", "department", "designation", "employment_status", "shift"]
        read_only_fields = ["id"]


class CompanyModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        return self.Meta.model.objects.create(company=self.context["request"].company, **validated_data)


class DepartmentSerializer(CompanyModelSerializer):
    class Meta: model = Department; fields = ["id", "name"]
class DesignationSerializer(CompanyModelSerializer):
    class Meta: model = Designation; fields = ["id", "name"]
class WorkShiftSerializer(CompanyModelSerializer):
    class Meta: model = WorkShift; fields = ["id", "name", "start_time", "end_time", "working_days"]
class AttendanceSerializer(serializers.ModelSerializer):
    class Meta: model = Attendance; fields = ["id", "employee", "date", "status", "check_in", "check_out", "notes"]
class LeaveTypeSerializer(CompanyModelSerializer):
    class Meta: model = LeaveType; fields = ["id", "name", "paid", "annual_entitlement"]
class LeaveBalanceSerializer(serializers.ModelSerializer):
    available = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    class Meta: model = LeaveBalance; fields = ["id", "employee", "leave_type", "year", "opening", "used", "adjustment", "available"]
class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = ["id", "employee", "leave_type", "start_date", "end_date", "days", "reason", "status", "reviewed_by", "reviewed_at"]
        read_only_fields = ["id", "days", "status", "reviewed_by", "reviewed_at"]
class HolidaySerializer(CompanyModelSerializer):
    class Meta: model = Holiday; fields = ["id", "name", "date"]
class EmployeeDocumentSerializer(CompanyModelSerializer):
    class Meta: model = EmployeeDocument; fields = ["id", "employee", "document_type", "document_number", "expiry_date", "notes"]


class SalaryStructureSerializer(CompanyModelSerializer):
    class Meta:
        model = SalaryStructure
        fields = ["id", "employee", "basic_pay", "allowances", "deductions", "overtime_hourly_rate", "is_active"]

    def validate_employee(self, employee):
        if employee.company_id != self.context["request"].company.id:
            raise serializers.ValidationError("Employee must belong to the active company.")
        return employee


class OvertimeEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = OvertimeEntry
        fields = ["id", "employee", "date", "hours", "overtime_type", "multiplier", "status", "approved_by", "approved_at", "notes"]
        read_only_fields = ["id", "status", "approved_by", "approved_at"]


class PayrollPeriodSerializer(CompanyModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = ["id", "name", "start_date", "end_date"]

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError("End date cannot be before start date.")
        return attrs


class PayrollLineSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    period_name = serializers.CharField(source="payroll_run.period.name", read_only=True)
    class Meta:
        model = PayrollLine
        fields = ["id", "payroll_run", "employee", "employee_name", "period_name", "basic_pay",
                  "allowances", "overtime_hours", "overtime_amount", "deductions", "gross_pay",
                  "net_pay", "payment_status", "paid_at"]
        read_only_fields = fields


class PayrollRunSerializer(serializers.ModelSerializer):
    lines = PayrollLineSerializer(many=True, read_only=True)
    class Meta:
        model = PayrollRun
        fields = ["id", "period", "status", "total_gross", "total_deductions", "total_net",
                  "created_by", "posted_by", "posted_at", "journal_entry", "reversal_journal_entry", "lines"]
        read_only_fields = fields

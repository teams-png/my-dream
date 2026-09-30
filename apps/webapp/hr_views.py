"""Staff & HR for every business type: staff, attendance, leave, salary advances, payroll and documents."""
import calendar
from datetime import date as date_cls, timedelta
from decimal import Decimal
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.employees import services as hr
from apps.employees.models import (AdvanceRecovery, Attendance, Employee, EmployeeDocument, Holiday, HRSettings,
                                   LeaveBalance, LeaveRequest, LeaveType, PayrollLine, PayrollRun, SalaryAdvance,
                                   SalaryStructure)

from .views import require_permission

MANAGE = "employees.manage"
PAYROLL = "employees.manage_payroll"
METHODS = [("cash", gettext_lazy("Cash")), ("bank", gettext_lazy("Bank"))]
WEEKDAYS = [(0, gettext_lazy("Monday")), (1, gettext_lazy("Tuesday")), (2, gettext_lazy("Wednesday")),
            (3, gettext_lazy("Thursday")), (4, gettext_lazy("Friday")), (5, gettext_lazy("Saturday")),
            (6, gettext_lazy("Sunday"))]


def _next(request, fallback):
    target = request.POST.get("next") or ""
    return target if target.startswith("/") and not target.startswith("//") else fallback


def _error(exc):
    return "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)


def _month_key(value=None):
    today = timezone.localdate()
    try:
        year, month = (int(part) for part in (value or "").split("-"))
        date_cls(year, month, 1)
        return f"{year:04d}-{month:02d}"
    except (ValueError, TypeError):
        return f"{today.year:04d}-{today.month:02d}"


def _shift_month(key, delta):
    year, month = (int(part) for part in key.split("-"))
    month += delta
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}"


def _month_label(key):
    year, month = (int(part) for part in key.split("-"))
    return date_cls(year, month, 1)


def _staff(company):
    return Employee.objects.for_company(company).filter(is_active=True).order_by("name")


# ------------------------------------------------------------------ forms

class StaffForm(forms.ModelForm):
    basic_pay = forms.DecimalField(label=gettext_lazy("Basic salary (monthly)"), max_digits=12, decimal_places=2,
                                   min_value=0, initial=0)
    allowance = forms.DecimalField(label=gettext_lazy("Allowances (housing, transport...)"), max_digits=12,
                                   decimal_places=2, min_value=0, required=False)
    deduction = forms.DecimalField(label=gettext_lazy("Fixed deductions"), max_digits=12, decimal_places=2,
                                   min_value=0, required=False)
    overtime_rate = forms.DecimalField(label=gettext_lazy("Overtime rate per hour"), max_digits=12,
                                       decimal_places=2, min_value=0, required=False)

    class Meta:
        model = Employee
        fields = ["name", "phone", "role_title", "joined_date", "employment_status", "user"]
        labels = {"role_title": gettext_lazy("Job title"), "user": gettext_lazy("Login (optional)"),
                  "employment_status": gettext_lazy("Status")}
        widgets = {"joined_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import User
        self.company = company
        self.fields["user"].queryset = User.objects.filter(memberships__company=company).distinct()
        self.fields["user"].required = False
        structure = getattr(self.instance, "salary_structure", None) if self.instance.pk else None
        if structure:
            self.fields["basic_pay"].initial = structure.basic_pay
            self.fields["allowance"].initial = hr._money_total(structure.allowances) or None
            self.fields["deduction"].initial = hr._money_total(structure.deductions) or None
            self.fields["overtime_rate"].initial = structure.overtime_hourly_rate or None
        elif self.instance.pk:
            self.fields["basic_pay"].initial = self.instance.salary

    def clean_user(self):
        user = self.cleaned_data.get("user")
        if user and Employee.objects.filter(user=user).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("This login is already linked to another staff member."))
        return user

    @transaction.atomic
    def save(self, commit=True):
        employee = super().save(commit=False)
        employee.company = self.company
        employee.salary = self.cleaned_data["basic_pay"]
        employee.is_active = employee.employment_status not in ("inactive", "terminated")
        employee.save()
        data = self.cleaned_data
        SalaryStructure.objects.update_or_create(company=self.company, employee=employee, defaults={
            "basic_pay": data["basic_pay"],
            "allowances": {"Allowances": str(data["allowance"])} if data.get("allowance") else {},
            "deductions": {"Deductions": str(data["deduction"])} if data.get("deduction") else {},
            "overtime_hourly_rate": data.get("overtime_rate") or 0, "is_active": True})
        return employee


class AdvanceForm(forms.Form):
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label=gettext_lazy("Staff member"))
    amount = forms.DecimalField(label=gettext_lazy("Advance amount"), max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    monthly_deduction = forms.DecimalField(label=gettext_lazy("Deduct from salary each month"), max_digits=12,
                                           decimal_places=2, min_value=Decimal("0.01"), required=False,
                                           help_text=gettext_lazy("Leave empty to deduct it all from the next salary."))
    date = forms.DateField(label=gettext_lazy("Date"), widget=forms.DateInput(attrs={"type": "date"}))
    method = forms.ChoiceField(label=gettext_lazy("Paid from"), choices=METHODS)
    reason = forms.CharField(label=gettext_lazy("Reason / note"), max_length=255, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = _staff(company)
        self.fields["date"].initial = timezone.localdate()


class LeaveForm(forms.Form):
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label=gettext_lazy("Staff member"))
    leave_type = forms.ModelChoiceField(queryset=LeaveType.objects.none(), label=gettext_lazy("Leave type"))
    start_date = forms.DateField(label=gettext_lazy("From"), widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label=gettext_lazy("To"), widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label=gettext_lazy("Reason"), max_length=255, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = _staff(company)
        self.fields["leave_type"].queryset = LeaveType.objects.for_company(company).order_by("name")


class DocumentForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ["employee", "document_type", "document_number", "expiry_date", "notes"]
        labels = {"employee": gettext_lazy("Staff member"), "document_type": gettext_lazy("Document"),
                  "document_number": gettext_lazy("Number"), "expiry_date": gettext_lazy("Expiry date"),
                  "notes": gettext_lazy("Notes")}
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.TextInput(),
                   "document_type": forms.TextInput(attrs={"list": "docTypes"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = _staff(company)


# ------------------------------------------------------------------ staff

@login_required
@require_permission(MANAGE)
def staff_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    today = timezone.localdate()
    show = request.GET.get("show", "active")
    staff = Employee.objects.for_company(company).select_related("salary_structure").order_by("name")
    staff = staff.filter(is_active=(show != "former"))
    query = (request.GET.get("q") or "").strip()
    if query:
        staff = staff.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(role_title__icontains=query))
    today_status = dict(Attendance.objects.for_company(company).filter(date=today).values_list("employee_id", "status"))
    advances = {}
    for advance in SalaryAdvance.objects.for_company(company).prefetch_related("recoveries"):
        advances[advance.employee_id] = advances.get(advance.employee_id, Decimal("0")) + advance.outstanding
    staff = list(staff)
    for person in staff:
        structure = getattr(person, "salary_structure", None)
        person.monthly = (structure.basic_pay + hr._money_total(structure.allowances)) if structure else person.salary
        person.today = today_status.get(person.id, "")
        person.advance_balance = advances.get(person.id, Decimal("0"))
    active = _staff(company)
    soon = today + timedelta(days=30)
    return render(request, "webapp/hr/staff_list.html", {
        "staff": staff, "show": show, "q": query, "today": today,
        "stats": {
            "count": active.count(),
            "present": Attendance.objects.for_company(company).filter(date=today, status__in=["present", "half_day"],
                                                                       employee__is_active=True).count(),
            "marked": len(today_status),
            "payroll": sum((p.monthly for p in staff if p.is_active), Decimal("0")) if show != "former" else None,
            "advances": sum(advances.values(), Decimal("0")),
            "documents": EmployeeDocument.objects.for_company(company).filter(
                employee__is_active=True, expiry_date__isnull=False, expiry_date__lte=soon).count(),
            "pending_leave": LeaveRequest.objects.for_company(company).filter(status="pending").count(),
        },
    })


@login_required
@require_permission(MANAGE)
def staff_add(request):
    return _staff_form(request, None)


@login_required
@require_permission(MANAGE)
def staff_edit(request, staff_id):
    return _staff_form(request, get_object_or_404(Employee.objects.for_company(request.company), id=staff_id))


def _staff_form(request, employee):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    form = StaffForm(request.POST or None, instance=employee, company=company)
    if request.method == "POST" and form.is_valid():
        employee = form.save()
        messages.success(request, _("%(name)s saved.") % {"name": employee.name})
        return redirect("webapp:staff_detail", employee.id)
    return render(request, "webapp/hr/staff_form.html", {"form": form, "employee": employee})


@login_required
@require_permission(MANAGE)
def staff_delete(request, staff_id):
    employee = get_object_or_404(Employee.objects.for_company(request.company), id=staff_id)
    if request.method == "POST":
        try:
            with transaction.atomic():
                employee.delete()
            messages.success(request, _("%(name)s removed.") % {"name": employee.name})
        except ProtectedError:
            employee.is_active = False
            employee.employment_status = "terminated"
            employee.leaving_date = employee.leaving_date or timezone.localdate()
            employee.save(update_fields=["is_active", "employment_status", "leaving_date"])
            messages.success(request, _("%(name)s has salary history, so they were moved to former staff.") % {"name": employee.name})
        return redirect("webapp:staff_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": employee, "cancel_url": "webapp:staff_list", "delete_url": "webapp:staff_delete", "delete_id": staff_id})


@login_required
@require_permission(MANAGE)
def staff_detail(request, staff_id):
    company = request.company
    employee = get_object_or_404(Employee.objects.for_company(company).select_related("salary_structure", "user"), id=staff_id)
    key = _month_key(request.GET.get("m"))
    start = _month_label(key)
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    marks = Attendance.objects.for_company(company).filter(employee=employee, date__range=(start, end))
    counts = {}
    for status in marks.values_list("status", flat=True):
        counts[status] = counts.get(status, 0) + 1
    advances = list(SalaryAdvance.objects.for_company(company).filter(employee=employee).prefetch_related("recoveries"))
    year = timezone.localdate().year
    balances = LeaveBalance.objects.for_company(company).filter(employee=employee, year=year).select_related("leave_type")
    structure = getattr(employee, "salary_structure", None)
    return render(request, "webapp/hr/staff_detail.html", {
        "employee": employee, "structure": structure, "key": key, "month": start,
        "prev": _shift_month(key, -1), "next": _shift_month(key, 1), "counts": counts,
        "absence": hr.unpaid_absence_days(company=company, employee=employee, start=start, end=end),
        "advances": advances, "advance_balance": sum((a.outstanding for a in advances), Decimal("0")),
        "next_deduction": hr.advance_due(company=company, employee=employee),
        "payslips": PayrollLine.objects.for_company(company).filter(employee=employee)
        .select_related("payroll_run__period").order_by("-payroll_run__period__start_date")[:12],
        "leaves": LeaveRequest.objects.for_company(company).filter(employee=employee).select_related("leave_type")
        .order_by("-start_date")[:10],
        "balances": balances, "documents": EmployeeDocument.objects.for_company(company).filter(employee=employee)
        .order_by("expiry_date"), "today": timezone.localdate(),
        "allowances": hr._money_total(structure.allowances) if structure else Decimal("0"),
        "deductions": hr._money_total(structure.deductions) if structure else Decimal("0"),
    })


# ------------------------------------------------------------------ attendance

@login_required
@require_permission(MANAGE)
def attendance(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    day = parse_date(request.GET.get("date") or request.POST.get("date") or "") or timezone.localdate()
    staff = list(_staff(company))
    if request.method == "POST":
        valid = dict(Attendance.STATUS)
        saved = 0
        with transaction.atomic():
            for person in staff:
                status = request.POST.get(f"s_{person.id}", "")
                if status in valid:
                    hr.record_attendance(company=company, employee=person, date=day, status=status,
                                         check_in=request.POST.get(f"in_{person.id}") or None,
                                         check_out=request.POST.get(f"out_{person.id}") or None,
                                         notes=(request.POST.get(f"n_{person.id}") or "")[:255])
                    saved += 1
                elif status == "clear":
                    Attendance.objects.for_company(company).filter(employee=person, date=day).delete()
        messages.success(request, _("Attendance saved for %(count)s staff on %(day)s.") % {"count": saved, "day": day})
        return redirect(f"{request.path}?date={day.isoformat()}")
    existing = {a.employee_id: a for a in Attendance.objects.for_company(company).filter(date=day)}
    on_leave = set(LeaveRequest.objects.for_company(company).filter(status="approved", start_date__lte=day, end_date__gte=day)
                   .values_list("employee_id", flat=True))
    settings = HRSettings.load(company)
    holiday = Holiday.objects.for_company(company).filter(date=day).first()
    for person in staff:
        person.mark = existing.get(person.id)
        person.on_leave = person.id in on_leave
    return render(request, "webapp/hr/attendance.html", {
        "staff": staff, "day": day, "prev": day - timedelta(days=1), "next": day + timedelta(days=1),
        "statuses": Attendance.STATUS, "is_off": day.weekday() in (settings.weekly_off_days or []),
        "holiday": holiday, "today": timezone.localdate(),
    })


@login_required
@require_permission(MANAGE)
def attendance_month(request):
    company = request.company
    key = _month_key(request.GET.get("m"))
    start = _month_label(key)
    days = [start.replace(day=d) for d in range(1, calendar.monthrange(start.year, start.month)[1] + 1)]
    marks = {}
    for row in Attendance.objects.for_company(company).filter(date__range=(days[0], days[-1])):
        marks[(row.employee_id, row.date)] = row.status
    off = set(HRSettings.load(company).weekly_off_days or [])
    holidays = set(Holiday.objects.for_company(company).filter(date__range=(days[0], days[-1])).values_list("date", flat=True))
    letters = {"present": "P", "absent": "A", "half_day": "½", "leave": "L", "holiday": "H"}
    rows = []
    for person in _staff(company):
        cells, totals = [], {"present": 0, "absent": 0, "half_day": 0, "leave": 0}
        for day in days:
            status = marks.get((person.id, day), "")
            if status in totals:
                totals[status] += 1
            cells.append({"status": status, "letter": letters.get(status, ""),
                          "off": day.weekday() in off or day in holidays})
        rows.append({"person": person, "cells": cells, "totals": totals,
                     "unpaid": hr.unpaid_absence_days(company=company, employee=person, start=days[0], end=days[-1])})
    return render(request, "webapp/hr/attendance_month.html", {
        "rows": rows, "days": days, "key": key, "month": start, "prev": _shift_month(key, -1),
        "next": _shift_month(key, 1), "off": off, "holidays": holidays})


# ------------------------------------------------------------------ leave

@login_required
@require_permission(MANAGE)
def leave(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    form = LeaveForm(company=company)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "request":
                form = LeaveForm(request.POST, company=company)
                if form.is_valid():
                    data = form.cleaned_data
                    request_obj = hr.request_leave(company=company, employee=data["employee"], leave_type=data["leave_type"],
                                                   start_date=data["start_date"], end_date=data["end_date"],
                                                   reason=data["reason"])
                    if request.POST.get("approve_now"):
                        hr.review_leave(company=company, request=request_obj, reviewer=request.user, approve=True)
                    messages.success(request, _("Leave saved for %(name)s (%(days)s days).") % {
                        "name": data["employee"].name, "days": request_obj.days.normalize()})
                    return redirect("webapp:hr_leave")
            elif action in ("approve", "reject"):
                leave_request = get_object_or_404(LeaveRequest.objects.for_company(company), id=request.POST.get("id"))
                hr.review_leave(company=company, request=leave_request, reviewer=request.user, approve=action == "approve")
                messages.success(request, _("Leave approved.") if action == "approve" else _("Leave rejected."))
                return redirect("webapp:hr_leave")
            elif action == "add_type":
                name = (request.POST.get("name") or "").strip()
                if name:
                    LeaveType.objects.create(company=company, name=name[:120], paid=bool(request.POST.get("paid")),
                                             annual_entitlement=Decimal(request.POST.get("days") or "0"))
                    messages.success(request, _("Leave type added."))
                return redirect("webapp:hr_leave")
            elif action == "add_holiday":
                day = parse_date(request.POST.get("date") or "")
                name = (request.POST.get("name") or "").strip()
                if day and name:
                    Holiday.objects.update_or_create(company=company, date=day, defaults={"name": name[:120]})
                    messages.success(request, _("Holiday saved."))
                return redirect("webapp:hr_leave")
            elif action == "delete_holiday":
                Holiday.objects.for_company(company).filter(id=request.POST.get("id")).delete()
                return redirect("webapp:hr_leave")
        except (ValidationError, ArithmeticError, ValueError) as exc:
            messages.error(request, _error(exc))
    if not LeaveType.objects.for_company(company).exists():
        LeaveType.objects.bulk_create([
            LeaveType(company=company, name=_("Annual leave"), paid=True, annual_entitlement=30),
            LeaveType(company=company, name=_("Sick leave"), paid=True, annual_entitlement=14),
            LeaveType(company=company, name=_("Unpaid leave"), paid=False, annual_entitlement=365)])
        form = LeaveForm(company=company)
    year = timezone.localdate().year
    balances = {}
    for b in LeaveBalance.objects.for_company(company).filter(year=year, employee__is_active=True).select_related("employee", "leave_type"):
        balances.setdefault(b.employee, []).append(b)
    return render(request, "webapp/hr/leave.html", {
        "form": form, "pending": LeaveRequest.objects.for_company(company).filter(status="pending")
        .select_related("employee", "leave_type").order_by("start_date"),
        "recent": LeaveRequest.objects.for_company(company).exclude(status="pending")
        .select_related("employee", "leave_type").order_by("-start_date")[:20],
        "types": LeaveType.objects.for_company(company).order_by("name"),
        "holidays": Holiday.objects.for_company(company).filter(date__year__gte=year).order_by("date"),
        "balances": balances, "year": year,
    })


# ------------------------------------------------------------------ salary advances

@login_required
@require_permission(PAYROLL)
def advances(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    form = AdvanceForm(company=company, initial={"employee": request.GET.get("employee")})
    if request.method == "POST":
        try:
            if request.POST.get("action") == "repay":
                advance = get_object_or_404(SalaryAdvance.objects.for_company(company), id=request.POST.get("id"))
                hr.repay_advance(company=company, user=request.user, advance=advance, amount=request.POST.get("amount") or "0",
                                 date=parse_date(request.POST.get("date") or "") or timezone.localdate(),
                                 method=request.POST.get("method") or "cash")
                messages.success(request, _("Repayment recorded."))
                return redirect(_next(request, "webapp:hr_advances"))
            form = AdvanceForm(request.POST, company=company)
            if form.is_valid():
                data = form.cleaned_data
                advance = hr.give_advance(company=company, user=request.user, employee=data["employee"],
                                          amount=data["amount"], date=data["date"],
                                          monthly_deduction=data.get("monthly_deduction"), method=data["method"],
                                          reason=data["reason"])
                messages.success(request, _("Advance of %(amount)s given to %(name)s. It will be deducted from salary.") % {
                    "amount": advance.amount, "name": advance.employee.name})
                return redirect("webapp:hr_advances")
        except (ValidationError, ArithmeticError, ValueError) as exc:
            messages.error(request, _error(exc))
    show = request.GET.get("show", "open")
    rows = list(SalaryAdvance.objects.for_company(company).select_related("employee").prefetch_related("recoveries"))
    if show == "open":
        rows = [a for a in rows if a.outstanding > 0]
    return render(request, "webapp/hr/advances.html", {
        "form": form, "rows": rows, "show": show, "today": timezone.localdate(), "methods": METHODS,
        "total_outstanding": sum((a.outstanding for a in rows if a.outstanding > 0), Decimal("0")),
        "given_month": SalaryAdvance.objects.for_company(company).filter(
            date__year=timezone.localdate().year, date__month=timezone.localdate().month).aggregate(t=Sum("amount"))["t"] or 0,
    })


# ------------------------------------------------------------------ payroll

@login_required
@require_permission(PAYROLL)
def payroll(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    key = _month_key(request.GET.get("m") or request.POST.get("m"))
    period = hr.month_period(company, key)
    run = PayrollRun.objects.for_company(company).filter(period=period).first()
    here = f"{request.path}?m={key}"
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action in ("create", "recalculate"):
                if run and action == "recalculate":
                    hr.delete_draft_run(company=company, payroll_run=run)
                hr.ensure_salary_structures(company)
                run = hr.create_payroll_run(company=company, user=request.user, period=period)
                messages.success(request, _("Payroll calculated for %(count)s staff.") % {"count": run.lines.count()})
            elif action == "post" and run:
                hr.post_payroll(company=company, user=request.user, payroll_run=run, date=period.end_date)
                messages.success(request, _("Payroll approved. Salaries can now be paid."))
            elif action == "pay" and run:
                method = request.POST.get("method") or "cash"
                ids = request.POST.getlist("line") if request.POST.get("line") else list(
                    run.lines.filter(payment_status="unpaid").values_list("id", flat=True))
                paid = 0
                for line in PayrollLine.objects.for_company(company).filter(payroll_run=run, id__in=ids, payment_status="unpaid"):
                    hr.pay_payslip(company=company, user=request.user, payroll_line=line, method=method)
                    paid += 1
                messages.success(request, _("%(count)s salaries paid.") % {"count": paid})
            elif action == "reverse" and run:
                hr.reverse_payroll(company=company, user=request.user, payroll_run=run, date=timezone.localdate())
                messages.success(request, _("Payroll reversed."))
            elif action == "reopen" and run and run.status == "reversed":
                run.delete()
                messages.success(request, _("Reversed payroll removed. You can calculate it again."))
        except (ValidationError, ArithmeticError, ValueError) as exc:
            messages.error(request, _error(exc))
        return redirect(here)
    lines = list(run.lines.select_related("employee").order_by("employee__name")) if run else []
    hr.ensure_salary_structures(company)
    missing = _staff(company).filter(salary_structure__isnull=True)
    return render(request, "webapp/hr/payroll.html", {
        "key": key, "month": period.start_date, "prev": _shift_month(key, -1), "next": _shift_month(key, 1),
        "run": run, "lines": lines, "missing": missing, "staff_count": _staff(company).count(),
        "unpaid": [line for line in lines if line.payment_status == "unpaid"], "methods": METHODS,
        "recent": PayrollRun.objects.for_company(company).select_related("period").order_by("-period__start_date")[:12],
        "totals": {
            "absence": sum((line.absence_deduction for line in lines), Decimal("0")),
            "overtime": sum((line.overtime_amount for line in lines), Decimal("0")),
            "paid": sum((line.net_pay for line in lines if line.payment_status == "paid"), Decimal("0")),
        },
    })


@login_required
@require_permission(PAYROLL)
def payslip(request, line_id):
    company = request.company
    line = get_object_or_404(PayrollLine.objects.for_company(company).select_related(
        "employee", "payroll_run__period"), id=line_id)
    currency = getattr(company, "default_currency", "") or ""
    text = "\n".join([
        f"{_('Payslip')} {line.payroll_run.period.name}", line.employee.name,
        f"{_('Gross pay')}: {currency} {line.gross_pay}", f"{_('Deductions')}: {currency} {line.deductions}",
        f"{_('Salary advance recovered')}: {currency} {line.advance_deduction}",
        f"{_('Net pay')}: {currency} {line.net_pay}"])
    phone = "".join(ch for ch in (line.employee.phone or "") if ch.isdigit())
    return render(request, "webapp/hr/payslip.html", {
        "line": line, "period": line.payroll_run.period,
        "advance_balance": hr.employee_advance_balance(company=company, employee=line.employee),
        "whatsapp": f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}",
    })


# ------------------------------------------------------------------ documents & settings

@login_required
@require_permission(MANAGE)
def documents(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    form = DocumentForm(company=company, initial={"employee": request.GET.get("employee")})
    if request.method == "POST":
        if request.POST.get("action") == "delete":
            EmployeeDocument.objects.for_company(company).filter(id=request.POST.get("id")).delete()
            messages.success(request, _("Document removed."))
            return redirect("webapp:hr_documents")
        form = DocumentForm(request.POST, company=company)
        if form.is_valid():
            document = form.save(commit=False)
            document.company = company
            document.save()
            messages.success(request, _("Document saved."))
            return redirect(_next(request, "webapp:hr_documents"))
    today = timezone.localdate()
    docs = list(EmployeeDocument.objects.for_company(company).filter(employee__is_active=True)
                .select_related("employee").order_by("expiry_date", "employee__name"))
    for doc in docs:
        doc.days_left = (doc.expiry_date - today).days if doc.expiry_date else None
    return render(request, "webapp/hr/documents.html", {"form": form, "docs": docs, "today": today})


@login_required
@require_permission(MANAGE)
def hr_settings(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    settings = HRSettings.load(company)
    if request.method == "POST":
        settings.weekly_off_days = sorted({int(d) for d in request.POST.getlist("off") if d.isdigit() and int(d) < 7})
        settings.deduct_absence = bool(request.POST.get("deduct_absence"))
        settings.save(update_fields=["weekly_off_days", "deduct_absence"])
        messages.success(request, _("HR settings saved."))
        return redirect("webapp:hr_settings")
    return render(request, "webapp/hr/settings.html", {"settings": settings, "weekdays": WEEKDAYS})

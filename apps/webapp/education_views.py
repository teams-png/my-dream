"""Education: courses/classes, enrolments, monthly fees, dues and attendance."""
from datetime import date

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.customers.models import Customer
from apps.industry import education as svc
from apps.industry.models import AttendanceSession, Course, Enrollment, FeeCharge
from apps.modules.catalog import EDUCATION_TERMS

from .industry_access import require_industry

education_view = require_industry("education")
DATE = forms.DateInput(attrs={"type": "date"})


def _terms(company):
    return dict(zip(("course", "courses", "student", "students"),
                    EDUCATION_TERMS.get(company.business_type.code, ("Course", "Courses", "Student", "Students"))))


def _msgids():  # labels above, for the translation catalogue
    return [_("Course"), _("Courses"), _("Batch"), _("Batches"), _("Class"), _("Classes"), _("Package"), _("Packages"),
            _("Student"), _("Students"), _("Child"), _("Children"), _("Learner"), _("Learners")]


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["name", "fee", "billing", "schedule", "teacher", "capacity", "is_active"]


class EnrollForm(forms.Form):
    course = forms.ModelChoiceField(queryset=Course.objects.none())
    student = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    new_student_name = forms.CharField(max_length=255, required=False)
    new_student_phone = forms.CharField(max_length=20, required=False)
    start_date = forms.DateField(widget=DATE)
    discount_percent = forms.DecimalField(min_value=0, max_value=100, decimal_places=2, required=False, initial=0)
    guardian_name = forms.CharField(max_length=120, required=False)
    guardian_phone = forms.CharField(max_length=20, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    bill_now = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["course"].queryset = Course.objects.for_company(company).filter(is_active=True)
        self.fields["student"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("student") and not (cleaned.get("new_student_name") or "").strip():
            self.add_error("student", _("Choose a student or type a new student's name."))
        return cleaned

    def get_student(self):
        if self.cleaned_data.get("student"):
            return self.cleaned_data["student"]
        return Customer.objects.create(company=self.company, name=self.cleaned_data["new_student_name"].strip(),
                                       phone=(self.cleaned_data.get("new_student_phone") or
                                              self.cleaned_data.get("guardian_phone") or "").strip())


def _month(request):
    raw = request.GET.get("month") or request.POST.get("month") or ""
    try:
        svc.month_bounds(raw)
        return raw
    except (ValueError, TypeError):
        return svc.month_key(timezone.localdate())


@education_view
def education_home(request):
    company = request.company
    key = svc.month_key(timezone.localdate())
    courses = (Course.objects.for_company(company)
               .annotate(active_count=Count("enrollments", filter=Q(enrollments__status="active"))))
    dues = svc.dues(company)
    return render(request, "webapp/industry/education_home.html", {
        "terms": _terms(company), "courses": courses, "month": key, "summary": svc.month_summary(company, key),
        "not_billed": len(svc.due_for_month(company, key)),
        "active_students": Enrollment.objects.for_company(company).filter(status="active").values("student").distinct().count(),
        "dues_total": sum((d["due"] for d in dues), 0), "dues_count": len(dues),
    })


@education_view
def course_form(request, course_id=None):
    company = request.company
    obj = get_object_or_404(Course.objects.for_company(company), pk=course_id) if course_id else None
    form = CourseForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.company = company
        course.save()
        svc.course_product(course)
        messages.success(request, _("%(name)s saved.") % {"name": course.name})
        return redirect("webapp:education_course", course_id=course.pk)
    return render(request, "webapp/industry/course_form.html", {"form": form, "obj": obj, "terms": _terms(company)})


@education_view
def course_detail(request, course_id):
    company = request.company
    course = get_object_or_404(Course.objects.for_company(company), pk=course_id)
    day = parse_date(request.POST.get("date") or request.GET.get("date") or "") or timezone.localdate()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "attendance":
            svc.take_attendance(company=company, user=request.user, course=course, day=day,
                                present_ids=request.POST.getlist("present"))
            messages.success(request, _("Attendance saved for %(day)s.") % {"day": day.strftime("%d %b %Y")})
        elif action in ("withdraw", "complete"):
            enrollment = get_object_or_404(Enrollment.objects.for_company(company), pk=request.POST.get("enrollment"),
                                           course=course)
            try:
                svc.withdraw(enrollment, end_date=timezone.localdate(),
                             status="withdrawn" if action == "withdraw" else "completed")
                messages.success(request, _("%(name)s updated.") % {"name": enrollment.student.name})
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        return redirect(f"{request.path}?date={day.isoformat()}")
    enrollments = course.enrollments.select_related("student").order_by("status", "student__name")
    session = AttendanceSession.objects.filter(course=course, date=day).first()
    marked = {m.enrollment_id: m.present for m in session.marks.all()} if session else {}
    rates = svc.attendance_rates(course)
    rows = [{"e": e, "rate": rates.get(e.pk), "present": marked.get(e.pk, True)} for e in enrollments]
    return render(request, "webapp/industry/course_detail.html", {
        "terms": _terms(company), "course": course, "rows": rows, "day": day, "session": session,
        "active_rows": [r for r in rows if r["e"].status == "active" and r["e"].start_date <= day],
        "sessions": course.sessions.all()[:10]})


@education_view
def enroll(request):
    company = request.company
    form = EnrollForm(request.POST or None, company=company,
                      initial={"course": request.GET.get("course"), "start_date": timezone.localdate(), "bill_now": True})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            enrollment = svc.enroll(company=company, user=request.user, course=d["course"], student=form.get_student(),
                                    start_date=d["start_date"], discount_percent=d.get("discount_percent") or 0,
                                    guardian_name=d.get("guardian_name", ""), guardian_phone=d.get("guardian_phone", ""),
                                    notes=d.get("notes", ""), bill_now=d.get("bill_now"))
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, _("%(name)s enrolled in %(course)s.") % {
                "name": enrollment.student.name, "course": enrollment.course.name})
            return redirect("webapp:education_course", course_id=enrollment.course_id)
    return render(request, "webapp/industry/enroll_form.html", {"form": form, "terms": _terms(company)})


@education_view
def fees(request):
    company = request.company
    key = _month(request)
    if request.method == "POST":
        try:
            invoices = svc.generate_month(company=company, user=request.user, key=key)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("%(count)s fee invoices created for %(month)s.") % {"count": len(invoices), "month": key})
        return redirect(f"{request.path}?month={key}")
    pending = svc.due_for_month(company, key)
    charges = (FeeCharge.objects.for_company(company).filter(period=key)
               .select_related("enrollment__student", "enrollment__course", "invoice").order_by("enrollment__student__name"))
    first, _last = svc.month_bounds(key)
    prev_first = date(first.year - (first.month == 1), 12 if first.month == 1 else first.month - 1, 1)
    next_first = date(first.year + (first.month == 12), 1 if first.month == 12 else first.month + 1, 1)
    return render(request, "webapp/industry/fees.html", {
        "terms": _terms(company), "month": key, "month_date": first, "pending": pending,
        "pending_total": sum((e.fee for e in pending), 0), "charges": charges,
        "summary": svc.month_summary(company, key),
        "prev": svc.month_key(prev_first), "next": svc.month_key(next_first)})


@education_view
def dues(request):
    return render(request, "webapp/industry/dues.html", {"terms": _terms(request.company), "rows": svc.dues(request.company)})

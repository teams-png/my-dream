"""Job cards and appointments for service businesses: the job board, a job card (parts, labour, bill,
WhatsApp, print), the day calendar per staff member, each staff member's phone page and the customer's
status page."""
from datetime import datetime, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _, gettext_lazy as _l
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.industry import jobs as svc
from apps.inventory.models import Product
from apps.verticals.saloon.models import ServiceCase, ServiceCaseNote, TechnicianLink

from .views import require_business_group

SUBJECT_LABELS = {"person": (_l("Patient / person"), _l("File no. / ID")), "student": (_l("Student"), _l("Student ID")),
                  "pet": (_l("Pet name"), _l("Microchip / reg. no.")), "vehicle": (_l("Vehicle"), _l("Plate / VIN")),
                  "asset": (_l("Item (e.g. laptop, AC)"), _l("Serial / model no.")),
                  "organization": (_l("Site / item"), _l("Reference"))}


def staff_view(view):
    return login_required(require_business_group("service", "saloon")(view))


def _pk(value):
    return int(value) if str(value or "").isdigit() else 0


def _labels(company):
    return SUBJECT_LABELS.get(svc.profile_type(company), SUBJECT_LABELS["person"])


class JobForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label=_l("Customer"))
    new_name = forms.CharField(max_length=150, required=False, label=_l("…or new customer name"))
    new_phone = forms.CharField(max_length=20, required=False, label=_l("Phone (WhatsApp)"))
    subject_name = forms.CharField(max_length=200, required=False)
    identifier = forms.CharField(max_length=100, required=False)
    title = forms.CharField(max_length=200, label=_l("Job / complaint"),
                            widget=forms.TextInput(attrs={"placeholder": _l("e.g. Oil change + brake check")}))
    description = forms.CharField(required=False, label=_l("Details"), widget=forms.Textarea(attrs={"rows": 2}))
    staff = forms.ModelChoiceField(queryset=Employee.objects.none(), required=False, label=_l("Staff"))
    scheduled_at = forms.DateTimeField(required=False, label=_l("Appointment"),
                                       widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                       input_formats=["%Y-%m-%dT%H:%M"])
    duration = forms.IntegerField(min_value=5, max_value=1440, initial=30, label=_l("Minutes"))
    ready_by = forms.DateTimeField(required=False, label=_l("Ready by (promised)"),
                                   widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                   input_formats=["%Y-%m-%dT%H:%M"])
    priority = forms.ChoiceField(choices=[("normal", _l("Normal")), ("urgent", _l("Urgent"))], initial="normal",
                                 label=_l("Priority"))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
        self.fields["staff"].queryset = Employee.objects.for_company(company).filter(is_active=True).order_by("name")
        subject, ident = _labels(company)
        self.fields["subject_name"].label, self.fields["identifier"].label = subject, ident

    def clean(self):
        data = super().clean()
        if not data.get("customer") and len((data.get("new_name") or "").strip()) < 2:
            raise ValidationError(_("Choose a customer or type a new customer's name."))
        return data

    def customer_obj(self):
        data = self.cleaned_data
        if data.get("customer"):
            return data["customer"]
        phone = (data.get("new_phone") or "").strip()
        if phone:
            found = Customer.objects.for_company(self.company).filter(phone=phone).first()
            if found:
                return found
        return Customer.objects.create(company=self.company, name=data["new_name"].strip(), phone=phone)


@staff_view
def board(request):
    company = request.company
    show = request.GET.get("show", "open")
    q = (request.GET.get("q") or "").strip()
    staff_id = _pk(request.GET.get("staff"))
    qs = (ServiceCase.objects.for_company(company)
          .select_related("profile", "profile__customer", "assigned_staff").prefetch_related("lines"))
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(profile__subject_name__icontains=q) |
                       Q(profile__identifier__icontains=q) | Q(profile__customer__name__icontains=q) |
                       Q(profile__customer__phone__icontains=q))
    if staff_id:
        qs = qs.filter(assigned_staff_id=staff_id)
    today = timezone.localdate()
    if show == "done":
        jobs = list(qs.filter(status__in=("completed", "cancelled")).order_by("-closed_date", "-id")[:100])
        columns = [("done", _("Completed / cancelled"), jobs)]
    else:
        jobs = list(qs.filter(status__in=svc.OPEN).order_by("scheduled_at", "id")[:300])
        if show == "today":
            jobs = [j for j in jobs if (j.scheduled_at and timezone.localtime(j.scheduled_at).date() == today)
                    or j.status in ("in_progress", "ready")]
        columns = [("open", _("Booked / to start"), [j for j in jobs if j.status == "open"]),
                   ("in_progress", _("In progress"), [j for j in jobs if j.status == "in_progress"]),
                   ("waiting", _("Waiting (parts / approval)"), [j for j in jobs if j.status == "waiting"]),
                   ("ready", _("Ready for the customer"), [j for j in jobs if j.status == "ready"])]
    for j in jobs:
        j.amount = svc.total(j)
        j.late = svc.overdue(j)
    return render(request, "webapp/jobs/board.html", {
        "columns": columns, "show": show, "q": q, "staff_id": staff_id, "currency": company.default_currency,
        "staff": Employee.objects.for_company(company).filter(is_active=True).order_by("name"),
        "form": JobForm(company=company), "today": today,
    })


@staff_view
def job_new(request):
    company = request.company
    initial = {}
    if request.GET.get("staff"):
        initial["staff"] = _pk(request.GET["staff"])
    if request.GET.get("at"):
        initial["scheduled_at"] = request.GET["at"]
    if request.GET.get("customer"):
        initial["customer"] = _pk(request.GET["customer"])
    form = JobForm(request.POST or None, company=company, initial=initial)
    clash = []
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        clash = svc.clashes(company, d.get("staff"), d.get("scheduled_at"), d.get("duration"))
        if clash and not request.POST.get("confirm_clash"):
            messages.warning(request, _("%(name)s already has %(job)s at that time. Press Save again to book anyway.") % {
                "name": d["staff"].name, "job": clash[0].number or clash[0].title})
        else:
            try:
                job = svc.create_job(company, customer=form.customer_obj(), title=d["title"],
                                     subject_name=d.get("subject_name"), identifier=d.get("identifier"),
                                     staff=d.get("staff"), scheduled_at=d.get("scheduled_at"), duration=d.get("duration"),
                                     ready_by=d.get("ready_by"), description=d.get("description"),
                                     priority=d.get("priority"))
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, _("Job %(number)s saved.") % {"number": job.number})
                return redirect("webapp:service_case_detail", case_id=job.id)
    return render(request, "webapp/jobs/new.html", {"form": form, "clash": bool(clash)})


@staff_view
def job_detail(request, case_id):
    company = request.company
    job = get_object_or_404(ServiceCase.objects.for_company(company)
                            .select_related("profile", "profile__customer", "assigned_staff", "invoice"), id=case_id)
    svc.ensure_number(job)
    link = svc.status_url(request, job)
    lines = list(job.lines.select_related("product"))
    return render(request, "webapp/jobs/detail.html", {
        "job": job, "lines": lines, "amount": svc.total(job), "currency": company.default_currency,
        "notes": job.case_notes.order_by("-date", "-id"), "status_link": link,
        "whatsapp": svc.whatsapp_url(job, link), "late": svc.overdue(job),
        "products": Product.objects.for_company(company).filter(is_active=True).order_by("name")[:1500],
        "staff": Employee.objects.for_company(company).filter(is_active=True).order_by("name"),
        "labels": _labels(company), "closed": job.status in ("completed", "cancelled") or bool(job.invoice_id),
    })


@staff_view
@require_POST
def job_action(request, case_id):
    company = request.company
    job = get_object_or_404(ServiceCase.objects.for_company(company), id=case_id)
    what = request.POST.get("do", "")
    try:
        if what == "status":
            svc.set_status(job, request.POST.get("status", ""))
            messages.success(request, _("Status: %(status)s") % {"status": job.get_status_display()})
        elif what == "line":
            pid = _pk(request.POST.get("product_id"))
            product = get_object_or_404(Product.objects.for_company(company), id=pid) if pid else None
            svc.add_line(job, kind=request.POST.get("kind", ""), product=product,
                         description=request.POST.get("description", ""), quantity=request.POST.get("quantity") or 1,
                         unit_price=request.POST.get("unit_price"))
        elif what == "remove_line":
            svc.remove_line(job, _pk(request.POST.get("line_id")))
        elif what == "staff":
            sid = _pk(request.POST.get("staff_id"))
            job.assigned_staff = get_object_or_404(Employee.objects.for_company(company), id=sid) if sid else None
            job.save(update_fields=["assigned_staff"])
            messages.success(request, _("Saved."))
        elif what == "bill":
            invoice = svc.bill(job, request.user, method=request.POST.get("method", ""),
                               discount=request.POST.get("discount") or 0)
            messages.success(request, _("Bill %(number)s made.") % {"number": invoice.invoice_number})
        elif what == "close_free":
            svc.close_without_bill(job)
            messages.success(request, _("Job closed without a bill."))
        elif what == "note":
            text = (request.POST.get("notes") or "").strip()
            if not text:
                raise ValidationError(_("Write the note first."))
            ServiceCaseNote.objects.create(company=company, case=job, date=timezone.localdate(), notes=text[:5000],
                                           note_type=(request.POST.get("note_type") or "")[:50],
                                           next_follow_up=parse_date(request.POST.get("next_follow_up") or ""),
                                           created_by=request.user)
            messages.success(request, _("Note added."))
        else:
            raise Http404
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("webapp:service_case_detail", case_id=job.id)


@staff_view
def job_print(request, case_id):
    company = request.company
    job = get_object_or_404(ServiceCase.objects.for_company(company)
                            .select_related("profile", "profile__customer", "assigned_staff", "invoice"), id=case_id)
    svc.ensure_number(job)
    return render(request, "webapp/jobs/print.html", {
        "job": job, "lines": job.lines.all(), "amount": svc.total(job), "currency": company.default_currency,
        "company": company, "labels": _labels(company), "status_link": svc.status_url(request, job)})


@staff_view
def calendar(request):
    company = request.company
    day = parse_date(request.GET.get("day") or "") or timezone.localdate()
    columns, count = svc.day_plan(company, day)
    links = []
    for emp in Employee.objects.for_company(company).filter(is_active=True).order_by("name"):
        link = TechnicianLink.objects.filter(employee=emp, is_active=True).first()
        url = request.build_absolute_uri(reverse("webapp:technician_page", args=[link.token])) if link else ""
        wa = ""
        if link and emp.phone:
            from urllib.parse import quote
            from apps.sales.sharing import normalise_phone
            number = normalise_phone(emp.phone, company.country)
            if number:
                wa = f"https://wa.me/{number}?text=" + quote(_("Your jobs page (keep this link private): %(url)s") % {"url": url})
        links.append({"emp": emp, "url": url, "wa": wa})
    hours = [f"{h:02d}:00" for h in range(8, 22)]
    return render(request, "webapp/jobs/calendar.html", {
        "day": day, "prev": day - timedelta(days=1), "next": day + timedelta(days=1), "columns": columns,
        "count": count, "links": links, "hours": hours, "today": timezone.localdate()})


@staff_view
@require_POST
def technician_link_action(request, employee_id):
    emp = get_object_or_404(Employee.objects.for_company(request.company), id=employee_id)
    link = svc.technician_link(emp)
    if request.POST.get("do") == "new":
        import uuid
        link.token = uuid.uuid4()
        link.is_active = True
        link.save(update_fields=["token", "is_active"])
        messages.success(request, _("New link made for %(name)s — the old one no longer works.") % {"name": emp.name})
    elif request.POST.get("do") == "off":
        link.is_active = False
        link.save(update_fields=["is_active"])
        messages.success(request, _("Link turned off."))
    else:
        if not link.is_active:
            link.is_active = True
            link.save(update_fields=["is_active"])
        messages.success(request, _("Link ready for %(name)s.") % {"name": emp.name})
    return redirect(reverse("webapp:job_calendar") + "#links")


def technician_page(request, token):
    """A staff member's jobs on their phone. The private link is the key; only their own jobs."""
    link = TechnicianLink.objects.select_related("employee", "company").filter(token=token, is_active=True).first()
    if link is None or not link.employee.is_active or not link.company.is_active:
        raise Http404
    emp = link.employee
    if request.method == "POST":
        job = get_object_or_404(ServiceCase.objects.for_company(link.company), id=_pk(request.POST.get("job_id")),
                                assigned_staff=emp)
        try:
            what = request.POST.get("do")
            if what in ("in_progress", "waiting", "ready"):
                svc.set_status(job, what)
            elif what == "note":
                text = (request.POST.get("notes") or "").strip()
                if not text:
                    raise ValidationError(_("Write the note first."))
                ServiceCaseNote.objects.create(company=link.company, case=job, date=timezone.localdate(),
                                               notes=text[:2000], note_type=_("From %(name)s") % {"name": emp.name})
            else:
                raise Http404
            messages.success(request, _("Saved."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("webapp:technician_page", token=link.token)
    open_jobs, done = svc.technician_jobs(emp)
    for j in open_jobs:
        j.late = svc.overdue(j)
    return render(request, "webapp/jobs/technician.html", {
        "emp": emp, "company": link.company, "open": open_jobs, "done": done, "labels": _labels(link.company)})


def status_page(request, token):
    """What the customer sees from the link we send: the job's progress."""
    job = ServiceCase.objects.select_related("company", "profile", "profile__customer").filter(token=token).first()
    if job is None or not job.company.is_active:
        raise Http404
    steps = [("open", _("Received")), ("in_progress", _("In progress")), ("ready", _("Ready")), ("completed", _("Done"))]
    order = {"open": 0, "waiting": 1, "in_progress": 1, "ready": 2, "completed": 3}
    return render(request, "webapp/jobs/status.html", {
        "job": job, "company": job.company, "steps": steps, "at": order.get(job.status, 0),
        "amount": svc.total(job), "currency": job.company.default_currency})


def from_online_booking(req, user):
    """An online appointment request for a service business becomes a booked job."""
    from datetime import time as dtime
    from apps.industry.online_booking import customer_for
    when = None
    if req.date:
        when = timezone.make_aware(datetime.combine(req.date, req.time or dtime(9, 0)))
    job = svc.create_job(req.company, customer=customer_for(req), title=req.item_name or _("Appointment"),
                         scheduled_at=when, description=f"{req.number} {req.notes}".strip())
    req.linked = f"job:{job.pk}"
    req.save(update_fields=["linked"])
    return job

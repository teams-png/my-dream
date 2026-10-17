"""Site workers (manpower supply): workers at clients' sites, their IDs and expiry dates, the site's daily
timesheet, pay and the monthly client bill per site."""
import calendar
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.customers.models import Customer
from apps.employees import services as hr
from apps.employees import site_workers as sw
from apps.employees.models import Attendance, Employee, HRSettings, SalaryStructure, SiteInvoice, SiteShift, WorkSite
from apps.common.ids import pick_id

from . import xlsx
from .industry_access import require_industry
from .views import require_permission

DATE = forms.DateInput(attrs={"type": "date"})
MANAGE = "employees.manage"


def manpower_view(view):
    return require_industry("manpower")(require_permission(MANAGE)(view))


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))


def _wa(phone, text):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


# ------------------------------------------------------------------ forms

class WorkerForm(forms.ModelForm):
    basic_pay = forms.DecimalField(label=_l("Salary / pay rate"), max_digits=12, decimal_places=2, min_value=0, initial=0,
                                   help_text=_l("Per month, per day or per hour — as chosen in “How we pay”."))
    allowance = forms.DecimalField(label=_l("Allowances per month (food, transport…)"), max_digits=12, decimal_places=2,
                                   min_value=0, required=False)
    deduction = forms.DecimalField(label=_l("Fixed deductions per month"), max_digits=12, decimal_places=2,
                                   min_value=0, required=False)
    overtime_rate = forms.DecimalField(label=_l("Overtime pay per hour"), max_digits=12, decimal_places=2,
                                       min_value=0, required=False)

    class Meta:
        model = Employee
        fields = ["name", "phone", "trade", "nationality", "site", "accommodation", "joined_date", "employment_status",
                  "pay_basis", "bill_rate"]
        labels = {"name": _l("Full name"), "phone": _l("Phone / WhatsApp"), "trade": _l("Trade / skill"),
                  "nationality": _l("Nationality"), "site": _l("Working at site"),
                  "accommodation": _l("Accommodation / camp"), "joined_date": _l("Joined on"),
                  "employment_status": _l("Status"), "pay_basis": _l("How we pay"),
                  "bill_rate": _l("Client rate for this worker (optional)")}
        help_texts = {"bill_rate": _l("Leave empty to use the site's rate.")}
        widgets = {"joined_date": DATE}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["site"].queryset = WorkSite.objects.for_company(company).filter(is_active=True)
        self.fields["pay_basis"].choices = [(k, _(v)) for k, v in Employee.PAY_BASIS]
        self.fields["employment_status"].choices = [(k, _(v)) for k, v in self.fields["employment_status"].choices]
        self.fields["trade"].widget.attrs["placeholder"] = _("e.g. Electrician, Cleaner, Security guard")
        for kind, name in sw.DOCS:
            self.fields[f"{kind}_no"] = forms.CharField(label=_("%(doc)s number") % {"doc": _(name)}, max_length=120, required=False)
            self.fields[f"{kind}_exp"] = forms.DateField(label=_("%(doc)s expiry") % {"doc": _(name)}, required=False, widget=DATE)
        structure = getattr(self.instance, "salary_structure", None) if self.instance.pk else None
        if structure:
            self.fields["basic_pay"].initial = structure.basic_pay
            self.fields["allowance"].initial = hr._money_total(structure.allowances) or None
            self.fields["deduction"].initial = hr._money_total(structure.deductions) or None
            self.fields["overtime_rate"].initial = structure.overtime_hourly_rate or None
        if self.instance.pk:
            for kind, doc in sw.documents(self.instance).items():
                if doc:
                    self.fields[f"{kind}_no"].initial = doc.document_number
                    self.fields[f"{kind}_exp"].initial = doc.expiry_date

    def doc_fields(self):
        return [(_(name), self[f"{kind}_no"], self[f"{kind}_exp"]) for kind, name in sw.DOCS]

    @transaction.atomic
    def save(self, commit=True):
        worker = super().save(commit=False)
        data = self.cleaned_data
        worker.company = self.company
        worker.worker_type = "site"
        worker.role_title = worker.role_title or (worker.trade or "")[:100]
        worker.salary = data["basic_pay"]
        worker.is_active = worker.employment_status not in ("inactive", "terminated")
        worker.save()
        SalaryStructure.objects.update_or_create(company=self.company, employee=worker, defaults={
            "basic_pay": data["basic_pay"],
            "allowances": {"Allowances": str(data["allowance"])} if data.get("allowance") else {},
            "deductions": {"Deductions": str(data["deduction"])} if data.get("deduction") else {},
            "overtime_hourly_rate": data.get("overtime_rate") or 0, "is_active": True})
        sw.save_documents(worker, {kind: (data.get(f"{kind}_no"), data.get(f"{kind}_exp")) for kind, _n in sw.DOCS})
        return worker


class SiteForm(forms.ModelForm):
    new_client = forms.CharField(label=_l("…or new client name"), max_length=255, required=False)

    class Meta:
        model = WorkSite
        fields = ["name", "client", "location", "supervisor", "supervisor_phone", "bill_basis", "bill_rate",
                  "ot_bill_rate", "hours_per_day", "is_active", "notes"]
        labels = {"name": _l("Site name"), "client": _l("Client"), "location": _l("Location"),
                  "supervisor": _l("Site supervisor"), "supervisor_phone": _l("Supervisor phone"),
                  "bill_basis": _l("Bill the client"), "bill_rate": _l("Rate per worker"),
                  "ot_bill_rate": _l("Overtime rate per hour"), "hours_per_day": _l("Normal hours per day"),
                  "is_active": _l("Site is active"), "notes": _l("Notes")}
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["client"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
        self.fields["client"].required = False
        self.fields["bill_basis"].choices = [(k, _(v)) for k, v in WorkSite.BILL_BASIS]
        self.fields["name"].widget.attrs["placeholder"] = _("e.g. Al Wakra Mall – cleaning")
        if not self.instance.pk:
            self.fields.pop("is_active")  # a new site is active

    def clean_hours_per_day(self):
        value = self.cleaned_data["hours_per_day"]
        if not Decimal("1") <= value <= Decimal("24"):
            raise ValidationError(_("Hours must be between 0 and 24."))
        return value

    @transaction.atomic
    def save(self, commit=True):
        site = super().save(commit=False)
        site.company = self.company
        name = (self.cleaned_data.get("new_client") or "").strip()
        if not site.client_id and name:
            site.client = Customer.objects.create(company=self.company, name=name[:255])
        site.save()
        return site


# ------------------------------------------------------------------ workers

@manpower_view
def mp_home(request):
    company = request.company
    today = timezone.localdate()
    staff = sw.workers(company)
    site_id = request.GET.get("site") or ""
    query = (request.GET.get("q") or "").strip()
    if site_id == "none":
        staff = staff.filter(site__isnull=True)
    elif site_id:
        staff = staff.filter(site_id=pick_id(site_id))
    if query:
        staff = staff.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(trade__icontains=query)
                             | Q(nationality__icontains=query) | Q(documents__document_number__icontains=query)).distinct()
    staff = list(staff[:500])
    marks = dict(Attendance.objects.for_company(company).filter(date=today, employee__in=staff).values_list("employee_id", "status"))
    docs = {}
    from apps.employees.models import EmployeeDocument
    for d in EmployeeDocument.objects.for_company(company).filter(employee__in=staff):
        docs.setdefault(d.employee_id, {})[d.document_type] = d
    for w in staff:
        mine = docs.get(w.id, {})
        w.docs = []
        for kind, name in sw.DOCS[:3]:
            d = mine.get(name)
            w.docs.append({"label": _(name), "date": d.expiry_date if d else None,
                           "state": sw.expiry_state(d.expiry_date, today) if d else "missing"})
        w.today = marks.get(w.id, "")
    expiring = sw.expiring(company, days=60, today=today)
    for d in expiring:
        d.when = (_("expired %(n)s days ago") % {"n": -d.days_left}) if d.days_left < 0 else \
            (_("%(n)s days left") % {"n": d.days_left})
        d.whatsapp = _wa(d.employee.phone, _("Hello %(name)s, your %(doc)s expires on %(date)s. Please bring it for renewal.") % {
            "name": d.employee.name, "doc": _(d.document_type), "date": d.expiry_date.strftime("%d %b %Y")})
    return render(request, "webapp/manpower/home.html", {
        "workers": staff, "stats": sw.overview(company, today), "expiring": expiring[:100],
        "sites": WorkSite.objects.for_company(company).filter(is_active=True), "site_id": site_id, "q": query,
        "doc_heads": [_(name) for _k, name in sw.DOCS[:3]], "today": today})


@manpower_view
def mp_worker_add(request):
    return _worker_form(request, None)


@manpower_view
def mp_worker_edit(request, staff_id):
    return _worker_form(request, get_object_or_404(Employee.objects.for_company(request.company), id=staff_id))


def _worker_form(request, worker):
    company = request.company
    initial = {}
    if worker is None and request.GET.get("site"):
        initial["site"] = pick_id(request.GET.get("site"))
    form = WorkerForm(request.POST or None, instance=worker, company=company, initial=initial)
    if request.method == "POST" and form.is_valid():
        worker = form.save()
        messages.success(request, _("%(name)s saved.") % {"name": worker.name})
        return redirect("webapp:staff_detail", worker.id)
    return render(request, "webapp/manpower/worker_form.html", {"form": form, "worker": worker})


# ------------------------------------------------------------------ sites

@manpower_view
def mp_sites(request):
    company = request.company
    form = SiteForm(request.POST or None, company=company, initial={"bill_basis": "hour", "hours_per_day": 8, "is_active": True})
    if request.method == "POST" and form.is_valid():
        site = form.save()
        messages.success(request, _("%(name)s saved.") % {"name": site.name})
        return redirect("webapp:mp_site", site.id)
    show = request.GET.get("show", "active")
    sites = list(WorkSite.objects.for_company(company).filter(is_active=(show != "closed")).select_related("client"))
    counts = {}
    for site_id in Employee.objects.for_company(company).filter(worker_type="site", is_active=True, site__isnull=False).values_list("site_id", flat=True):
        counts[site_id] = counts.get(site_id, 0) + 1
    for s in sites:
        s.count = counts.get(s.id, 0)
    return render(request, "webapp/manpower/sites.html", {"sites": sites, "form": form, "show": show})


@manpower_view
def mp_site(request, site_id):
    company = request.company
    site = get_object_or_404(WorkSite.objects.for_company(company).select_related("client"), id=site_id)
    form = SiteForm(request.POST or None, instance=site, company=company) if request.POST.get("action") == "save" else \
        SiteForm(instance=site, company=company)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            if form.is_valid():
                form.save()
                messages.success(request, _("%(name)s saved.") % {"name": site.name})
                return redirect("webapp:mp_site", site.id)
        elif action in ("assign", "remove"):
            ids = [pick_id(x) for x in request.POST.getlist("worker")]
            picked = list(Employee.objects.for_company(company).filter(id__in=[i for i in ids if i]))
            try:
                count = sw.assign(company, picked, site if action == "assign" else None)
                messages.success(request, _("%(count)s workers moved.") % {"count": count})
            except ValidationError as exc:
                _err(request, exc)
            return redirect("webapp:mp_site", site.id)
    here = list(sw.workers(company, site))
    others = Employee.objects.for_company(company).filter(is_active=True).exclude(site=site).select_related("site").order_by("name")[:500]
    start = sw.month_start()
    return render(request, "webapp/manpower/site.html", {
        "site": site, "form": form, "workers": here, "others": others,
        "month": sw.site_month(site, start), "month_start": start,
        "supervisor_wa": _wa(site.supervisor_phone, _("Hello %(name)s,") % {"name": site.supervisor}) if site.supervisor_phone else ""})


# ------------------------------------------------------------------ site timesheet

@manpower_view
def mp_attendance(request):
    company = request.company
    sites = list(WorkSite.objects.for_company(company).filter(is_active=True))
    site = None
    wanted = pick_id(request.GET.get("site") or request.POST.get("site"))
    if wanted:
        site = next((s for s in sites if s.id == wanted), None)
    if site is None and sites:
        site = sites[0]
    day = parse_date(request.GET.get("date") or request.POST.get("date") or "") or timezone.localdate()
    if site is None:
        return render(request, "webapp/manpower/attendance.html", {"sites": sites, "site": None, "day": day})
    people = list(sw.workers(company, site).select_related("duty_shift"))
    marks = {a.employee_id: a for a in Attendance.objects.for_company(company).filter(date=day, employee__in=people)}
    if request.method == "POST":
        rows = []
        for w in people:
            status = request.POST.get(f"s_{w.id}", "")
            if status == "" and w.id not in marks:
                continue
            rows.append((w, status, request.POST.get(f"h_{w.id}"), request.POST.get(f"ot_{w.id}")))
        try:
            saved = sw.save_day(company, site, day, rows)
            messages.success(request, _("Attendance saved for %(count)s staff on %(day)s.") % {"count": saved, "day": day})
        except ValidationError as exc:
            _err(request, exc)
        return redirect(f"{request.path}?site={site.id}&date={day.isoformat()}")
    company_off = HRSettings.load(company).weekly_off_days or []
    for w in people:
        w.mark = marks.get(w.id)
        w.elsewhere = w.mark and w.mark.site_id not in (None, site.id)
        w.normal_hours = sw.day_hours(w, site)
        w.off_today = sw.is_off(w, day, company_off)
    return render(request, "webapp/manpower/attendance.html", {
        "sites": sites, "site": site, "day": day, "workers": people, "today": timezone.localdate(),
        "prev": day - timedelta(days=1), "next": day + timedelta(days=1), "statuses": Attendance.STATUS})


# ------------------------------------------------------------------ client billing

@manpower_view
def mp_billing(request):
    company = request.company
    start = sw.parse_month(request.GET.get("m") or request.POST.get("m"))
    if request.method == "POST":
        site = get_object_or_404(WorkSite.objects.for_company(company), id=pick_id(request.POST.get("site")))
        try:
            inv = sw.bill_site(company, request.user, site, start)
            messages.success(request, _("Invoice %(number)s made for %(site)s.") % {"number": inv.invoice_number, "site": site.name})
        except ValidationError as exc:
            _err(request, exc)
        return redirect(f"{request.path}?m={start:%Y-%m}")
    billed = {b.site_id: b for b in SiteInvoice.objects.for_company(company).filter(month=start).select_related("invoice")}
    sites = []
    for site in WorkSite.objects.for_company(company).select_related("client"):
        rows = sw.site_month(site, start)
        if not rows and not site.is_active and site.id not in billed:
            continue
        site.rows = rows
        site.total = sum((r["amount"] for r in rows), Decimal("0"))
        site.bill = billed.get(site.id)
        sites.append(site)
    prev = (start - timedelta(days=1)).replace(day=1)
    nxt = start.replace(day=calendar.monthrange(start.year, start.month)[1]) + timedelta(days=1)
    return render(request, "webapp/manpower/billing.html", {
        "sites": sites, "month": start, "prev": prev, "next": nxt, "is_future": start > sw.month_start(),
        "grand": sum((s.total for s in sites if not s.bill), Decimal("0"))})


def _msgids():  # choice and document names shown with {% translate %}, for the translation catalogue
    return [_("Per hour"), _("Per day"), _("Per month"), _("Monthly salary"), _("Per day worked"), _("Per hour worked"),
            _("ID / residence card"), _("Passport"), _("Health card"), _("Driving licence"), _("Work visa"),
            _("Office staff"), _("Site worker")]


# ------------------------------------------------------------------ duty roster

def _time(value):
    from django.utils.dateparse import parse_time
    return parse_time(value or "")


@manpower_view
def mp_duty(request):
    company = request.company
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "shift":
                site = get_object_or_404(WorkSite.objects.for_company(company), id=pick_id(request.POST.get("site")))
                shift = None
                if request.POST.get("shift"):
                    shift = get_object_or_404(SiteShift.objects.for_company(company), id=pick_id(request.POST.get("shift")), site=site)
                sw.save_shift(site, request.POST.get("name"), _time(request.POST.get("start")), _time(request.POST.get("end")),
                              request.POST.get("needed") or 1, shift=shift)
                messages.success(request, _("Shift saved."))
            elif action == "delete_shift":
                SiteShift.objects.for_company(company).filter(id=pick_id(request.POST.get("shift"))).delete()
                messages.success(request, _("Shift removed."))
            elif action in ("assign", "unassign"):
                ids = [i for i in (pick_id(x) for x in request.POST.getlist("worker")) if i]
                picked = list(Employee.objects.for_company(company).filter(id__in=ids))
                shift = None
                if action == "assign":
                    shift = get_object_or_404(SiteShift.objects.for_company(company), id=pick_id(request.POST.get("shift")))
                count = sw.assign_duty(company, picked, shift, request.POST.get("weekly_off", ""))
                messages.success(request, _("%(count)s workers moved.") % {"count": count})
        except ValidationError as exc:
            _err(request, exc)
        return redirect(request.path + (f"#site-{request.POST.get('site')}" if request.POST.get("site") else ""))
    sites, unassigned = sw.duty_board(company)
    from .hr_views import WEEKDAYS
    names = dict(WEEKDAYS)
    for site in sites:
        for r in site.shift_rows:
            for w in r["workers"]:
                w.off_name = names.get(w.weekly_off, "") if w.weekly_off is not None else ""
    return render(request, "webapp/manpower/duty.html", {
        "sites": sites, "unassigned": unassigned, "weekdays": WEEKDAYS,
        "all_workers": sw.workers(company).select_related("duty_shift", "site"),
        "short": sum(s.short for s in sites), "print": request.GET.get("print") == "1"})


# ------------------------------------------------------------------ profit

@manpower_view
def mp_profit(request):
    company = request.company
    start = sw.parse_month(request.GET.get("m"))
    sites, total = sw.profit_report(company, start)
    if xlsx.wants(request):
        data = [[_("Site"), _("Name"), _("Trade"), _("Days"), _("Hours"), _("OT hours"), _("Billed to client"),
                 _("Pay"), _("Overtime pay"), _("Cost"), _("Profit")]]
        for s in sites:
            for r in s.rows:
                data.append([s.name, r["employee"].name, r["employee"].trade, r["days"], r["hours"], r["ot"], r["amount"],
                             r["pay"], r["ot_pay"], r["cost"], r["profit"]])
        data.append([xlsx.Bold(_("Total")), "", "", "", "", total["ot"], total["billed"], "", total["ot_pay"],
                     total["cost"], total["profit"]])
        return xlsx.response(f"site-profit-{start:%Y-%m}", [(_("Site profit") + f" {start:%Y-%m}", data)])
    return render(request, "webapp/manpower/profit.html", {
        "sites": sites, "total": total, "month": start,
        "prev": (start - timedelta(days=1)).replace(day=1),
        "next": start.replace(day=calendar.monthrange(start.year, start.month)[1]) + timedelta(days=1)})


# ------------------------------------------------------------------ timesheet

@manpower_view
def mp_timesheet(request, site_id):
    company = request.company
    site = get_object_or_404(WorkSite.objects.for_company(company).select_related("client"), id=site_id)
    start = sw.parse_month(request.GET.get("m"))
    days, rows = sw.timesheet(site, start)
    if xlsx.wants(request):
        head = [_("Name"), _("Trade")] + [d.day for d in days] + [_("Days"), _("Hours"), _("OT hours")]
        data = [head]
        for r in rows:
            cells = [(f"{c['code']} {c['hours']:g}" if c["hours"] is not None else c["code"]) +
                     (f" +{c['ot']:g}" if c["ot"] else "") for c in r["cells"]]
            data.append([r["employee"].name, r["employee"].trade, *cells, r["days"], r["hours"], r["ot"]])
        return xlsx.response(f"timesheet-{site.name[:20]}-{start:%Y-%m}", [(f"{start:%Y-%m}", data)])
    return render(request, "webapp/manpower/timesheet.html", {
        "site": site, "month": start, "days": days, "rows": rows, "company": company,
        "off_days": HRSettings.load(company).weekly_off_days or [],
        "totals": {"days": sum((r["days"] for r in rows), Decimal("0")),
                   "hours": sum((r["hours"] for r in rows), Decimal("0")),
                   "ot": sum((r["ot"] for r in rows), Decimal("0"))}})

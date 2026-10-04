"""Recruitment / manpower agency: clients, job orders, candidates and the placement pipeline."""
import mimetypes
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.customers.models import Customer
from apps.industry import recruitment as svc
from apps.industry.models import Candidate, JobOrder, Placement, PlacementCost
from apps.industry.common import PAYMENT_METHODS
from apps.suppliers.models import Supplier

from . import xlsx
from .industry_access import require_industry
from apps.common.ids import pick_id

recruitment_view = require_industry("recruitment")
DATE = forms.DateInput(attrs={"type": "date"})


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))


def _wa(phone, text):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


# ------------------------------------------------------------------ forms

class ClientForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address", "payment_terms_days"]
        labels = {"name": _l("Company / client name"), "address": _l("Address & contact person")}
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


class JobOrderForm(forms.ModelForm):
    new_client_name = forms.CharField(max_length=255, required=False, label=_l("…or new client name"))
    new_client_phone = forms.CharField(max_length=20, required=False, label=_l("New client phone"))

    class Meta:
        model = JobOrder
        fields = ["client", "position", "vacancies", "work_location", "nationality", "gender", "salary", "benefits",
                  "contract_months", "fee_per_placement", "guarantee_days", "deadline", "requirements", "publish_online",
                  "public_summary", "status"]
        labels = {"client": _l("Client"), "position": _l("Position / job title"), "vacancies": _l("Number of people"),
                  "work_location": _l("Work location"), "nationality": _l("Preferred nationality"),
                  "salary": _l("Salary (per month)"), "benefits": _l("Benefits"),
                  "contract_months": _l("Contract (months)"), "fee_per_placement": _l("Our fee per person (charged to client)"),
                  "guarantee_days": _l("Replacement guarantee (days)"), "deadline": _l("Needed by"),
                  "requirements": _l("Requirements"), "gender": _l("Gender"), "status": _l("Status"),
                  "publish_online": _l("Show on our careers website"), "public_summary": _l("Job description for the website")}
        widgets = {"deadline": DATE, "requirements": forms.Textarea(attrs={"rows": 3}),
                   "public_summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
        self.fields["client"].required = False
        if not self.instance.pk:
            self.fields.pop("status")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("client") and not (cleaned.get("new_client_name") or "").strip():
            self.add_error("client", _("Choose a client or type a new client's name."))
        return cleaned


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ["name", "phone", "email", "trade", "nationality", "gender", "date_of_birth", "passport_no",
                  "passport_expiry", "experience_years", "gulf_experience", "current_location", "expected_salary",
                  "languages", "education", "agent", "cv", "notes", "status"]
        labels = {"name": _l("Full name"), "phone": _l("Phone / WhatsApp"), "trade": _l("Position / skill"),
                  "nationality": _l("Nationality"), "gender": _l("Gender"), "date_of_birth": _l("Date of birth"),
                  "passport_no": _l("Passport number"), "passport_expiry": _l("Passport expiry"),
                  "experience_years": _l("Experience (years)"), "gulf_experience": _l("Has Gulf experience"),
                  "current_location": _l("Current location"), "expected_salary": _l("Expected salary"),
                  "languages": _l("Languages"), "education": _l("Education"), "agent": _l("Sub-agent (if any)"),
                  "cv": _l("CV / documents (PDF, Word or photo)"), "notes": _l("Notes"), "status": _l("Status")}
        widgets = {"date_of_birth": DATE, "passport_expiry": DATE, "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agent"].queryset = Supplier.objects.for_company(company).filter(is_active=True).order_by("name")
        if not self.instance.pk:
            self.fields.pop("status")

    def clean_cv(self):
        cv = self.cleaned_data.get("cv")
        if cv and hasattr(cv, "size"):
            if cv.size > 8 * 1024 * 1024:
                raise ValidationError(_("The file is too large (max 8 MB)."))
            ext = (cv.name.rsplit(".", 1)[-1] if "." in cv.name else "").lower()
            if ext not in {"pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"}:
                raise ValidationError(_("Upload a PDF, Word file or photo."))
        return cv


# ------------------------------------------------------------------ overview

@recruitment_view
def rec_home(request):
    company = request.company
    return render(request, "webapp/recruitment/home.html", {
        "o": svc.overview(company), "pipeline": svc.pipeline_counts(company),
        "applied": Placement.objects.for_company(company).filter(stage="applied").select_related("candidate", "job_order")
        .order_by("-created_at")[:10],
        "general": Candidate.objects.for_company(company).filter(source="website", placements__isnull=True,
                                                                 status="available").order_by("-created_at")[:10],
        "jobs": JobOrder.objects.for_company(company).filter(status="open").select_related("client")
        .annotate(done=Count("placements", filter=Q(placements__stage="deployed")),
                  active=Count("placements", filter=Q(placements__stage__in=Placement.ACTIVE)))[:8],
        "today": timezone.localdate()})


# ------------------------------------------------------------------ clients

@recruitment_view
def rec_clients(request):
    company = request.company
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save(commit=False)
        client.company = company
        client.save()
        messages.success(request, _("Client %(name)s added.") % {"name": client.name})
        if request.POST.get("then") == "job":
            return redirect(f"{_url('webapp:rec_job_add')}?client={client.id}")
        return redirect("webapp:rec_clients")
    query = (request.GET.get("q") or "").strip()
    clients = Customer.objects.for_company(company).filter(is_active=True).annotate(
        jobs=Count("job_orders", distinct=True),
        open_jobs=Count("job_orders", filter=Q(job_orders__status="open"), distinct=True),
        placed=Count("job_orders__placements", filter=Q(job_orders__placements__stage="deployed"), distinct=True))
    # candidates who were billed a fee also have a customer record; they are not clients
    clients = clients.exclude(id__in=Candidate.objects.for_company(company).filter(customer__isnull=False).values("customer_id"))
    if query:
        clients = clients.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    return render(request, "webapp/recruitment/clients.html", {
        "clients": clients.order_by("-open_jobs", "name")[:300], "form": form, "q": query})


def _url(name, *args):
    from django.urls import reverse
    return reverse(name, args=args)


# ------------------------------------------------------------------ job orders

@recruitment_view
def rec_jobs(request):
    company = request.company
    status = request.GET.get("status", "open")
    jobs = JobOrder.objects.for_company(company).select_related("client").annotate(
        done=Count("placements", filter=Q(placements__stage="deployed")),
        active=Count("placements", filter=Q(placements__stage__in=Placement.ACTIVE))).order_by("-id")
    if status in dict(JobOrder.STATUS):
        jobs = jobs.filter(status=status)
    if request.GET.get("client"):
        jobs = jobs.filter(client_id=request.GET["client"])
    query = (request.GET.get("q") or "").strip()
    if query:
        jobs = jobs.filter(Q(position__icontains=query) | Q(number__icontains=query) | Q(client__name__icontains=query))
    return render(request, "webapp/recruitment/jobs.html", {
        "page": Paginator(jobs, 40).get_page(request.GET.get("page")), "status": status, "q": query,
        "statuses": JobOrder.STATUS})


def _job_form_save(request, form, job=None):
    data = form.cleaned_data
    client = data.get("client")
    if not client:
        client = Customer.objects.create(company=request.company, name=data["new_client_name"].strip()[:255],
                                         phone=(data.get("new_client_phone") or "")[:20])
    fields = {k: v for k, v in data.items() if k not in ("client", "new_client_name", "new_client_phone")}
    if job is None:
        return svc.create_job_order(company=request.company, user=request.user, client=client, **fields)
    for k, v in fields.items():
        setattr(job, k, v)
    job.client = client
    job.save()
    return job


@recruitment_view
def rec_job_add(request):
    company = request.company
    form = JobOrderForm(request.POST or None, company=company,
                        initial={"client": request.GET.get("client"), "vacancies": 1, "guarantee_days": 90})
    if request.method == "POST" and form.is_valid():
        try:
            job = _job_form_save(request, form)
            messages.success(request, _("Job order %(number)s created.") % {"number": job.number})
            return redirect("webapp:rec_job_detail", job.id)
        except ValidationError as exc:
            _err(request, exc)
    return render(request, "webapp/recruitment/job_form.html", {"form": form, "title": _("New job order")})


@recruitment_view
def rec_job_edit(request, job_id):
    job = get_object_or_404(JobOrder.objects.for_company(request.company), id=job_id)
    form = JobOrderForm(request.POST or None, instance=job, company=request.company)
    if request.method == "POST" and form.is_valid():
        _job_form_save(request, form, job)
        messages.success(request, _("Job order saved."))
        return redirect("webapp:rec_job_detail", job.id)
    return render(request, "webapp/recruitment/job_form.html", {"form": form, "title": job.number, "job": job})


@recruitment_view
def rec_job_detail(request, job_id):
    company = request.company
    job = get_object_or_404(JobOrder.objects.for_company(company).select_related("client"), id=job_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "submit":
                ids = request.POST.getlist("candidate")
                picked = list(Candidate.objects.for_company(company).filter(id__in=ids))
                name = (request.POST.get("new_name") or "").strip()
                if name:
                    picked.append(svc.create_candidate(company=company, name=name, phone=(request.POST.get("new_phone") or "")[:30],
                                                       trade=job.position, passport_no=(request.POST.get("new_passport") or "")[:30]))
                if not picked:
                    raise ValidationError(_("Choose candidates or type a new candidate's name."))
                added, skipped = svc.submit(company=company, job=job, candidates=picked)
                if added:
                    messages.success(request, _("%(count)s candidates added to this job.") % {"count": len(added)})
                if skipped:
                    messages.warning(request, _("Already added or not suitable: %(names)s") % {"names": ", ".join(skipped)})
            elif action == "move":
                placement = get_object_or_404(Placement.objects.for_company(company), id=pick_id(request.POST.get("placement")), job_order=job)
                svc.move(placement, request.POST.get("stage") or "")
            elif action in ("close", "reopen", "hold"):
                job.status = {"close": "closed", "reopen": "open", "hold": "on_hold"}[action]
                job.save(update_fields=["status"])
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:rec_job_detail", job.id)
    placements = list(job.placements.select_related("candidate", "invoice").order_by("created_at"))
    columns = [{"code": code, "label": label, "items": [p for p in placements if p.stage == code]}
               for code, label in Placement.STAGES if code not in ("rejected", "withdrawn")]
    dropped = [p for p in placements if p.stage in ("rejected", "withdrawn")]
    in_job = {p.candidate_id for p in placements}
    suggest = Candidate.objects.for_company(company).filter(status__in=["available", "in_process"]).exclude(id__in=in_job)
    if request.GET.get("all") != "1":
        terms = [w for w in job.position.split() if len(w) > 2]
        if terms:
            match = Q()
            for w in terms:
                match |= Q(trade__icontains=w)
            matched = suggest.filter(match)
            suggest = matched if matched.exists() else suggest
    share = [f"*{_('Job opening')}: {job.position}*", f"{_('Location')}: {job.work_location or '—'}",
             f"{_('Vacancies')}: {job.vacancies}"]
    if job.salary:
        share.append(f"{_('Salary')}: {company.default_currency} {job.salary:,.0f}")
    if job.benefits:
        share.append(f"{_('Benefits')}: {job.benefits}")
    if job.requirements:
        share.append(job.requirements[:500])
    share.append(f"{company.name} {company.phone or ''}".strip())
    return render(request, "webapp/recruitment/job_detail.html", {
        "job": job, "columns": columns, "dropped": dropped, "deployed": svc.deployed_count(job),
        "suggest": suggest.order_by("name")[:200], "stages": Placement.STAGES,
        "share": f"https://wa.me/?text={quote(chr(10).join(share))}",
        "client_update": _wa(job.client.phone, _client_update(job, placements))})


def _client_update(job, placements):
    lines = [f"{job.client.name} — {job.number} {job.position}"]
    for p in placements:
        if p.stage not in ("rejected", "withdrawn"):
            lines.append(f"• {p.candidate.name}: {p.get_stage_display()}")
    return "\n".join(lines)


# ------------------------------------------------------------------ candidates

@recruitment_view
def rec_candidates(request):
    company = request.company
    qs = Candidate.objects.for_company(company).select_related("agent")
    status = request.GET.get("status") or ""
    if status in dict(Candidate.STATUS):
        qs = qs.filter(status=status)
    source = request.GET.get("source") or ""
    if source in dict(Candidate.SOURCES):
        qs = qs.filter(source=source)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(passport_no__icontains=query)
                       | Q(trade__icontains=query) | Q(nationality__icontains=query) | Q(number__icontains=query))
    if xlsx.wants(request):
        data = [[_("Number"), _("Name"), _("Position / skill"), _("Nationality"), _("Phone"), _("Passport number"),
                 _("Passport expiry"), _("Experience (years)"), _("Expected salary"), _("Sub-agent"), _("Status")]]
        data += [[c.number, c.name, c.trade, c.nationality, c.phone, c.passport_no, c.passport_expiry, c.experience_years,
                  c.expected_salary, c.agent.name if c.agent else "", c.get_status_display()] for c in qs[:20000]]
        return xlsx.response(f"candidates-{timezone.localdate()}", [(_("Candidates"), data)])
    return render(request, "webapp/recruitment/candidates.html", {
        "page": Paginator(qs, 40).get_page(request.GET.get("page")), "status": status, "q": query,
        "statuses": Candidate.STATUS, "today": timezone.localdate(), "source": source})


@recruitment_view
def rec_candidate_add(request):
    company = request.company
    form = CandidateForm(request.POST or None, request.FILES or None, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            data = {k: v for k, v in form.cleaned_data.items()}
            candidate = svc.create_candidate(company=company, **data)
            messages.success(request, _("Candidate %(name)s added.") % {"name": candidate.name})
            if request.GET.get("job"):
                job = JobOrder.objects.for_company(company).filter(id=request.GET["job"]).first()
                if job:
                    svc.submit(company=company, job=job, candidates=[candidate])
                    return redirect("webapp:rec_job_detail", job.id)
            return redirect("webapp:rec_candidate_detail", candidate.id)
        except ValidationError as exc:
            _err(request, exc)
    return render(request, "webapp/recruitment/candidate_form.html", {"form": form, "title": _("New candidate")})


@recruitment_view
def rec_candidate_edit(request, candidate_id):
    candidate = get_object_or_404(Candidate.objects.for_company(request.company), id=candidate_id)
    form = CandidateForm(request.POST or None, request.FILES or None, instance=candidate, company=request.company)
    if request.method == "POST" and form.is_valid():
        passport = (form.cleaned_data.get("passport_no") or "").strip().upper()
        if passport and Candidate.objects.for_company(request.company).filter(passport_no__iexact=passport).exclude(id=candidate.id).exists():
            form.add_error("passport_no", _("Another candidate has this passport number."))
        else:
            obj = form.save(commit=False)
            obj.passport_no = passport
            obj.save()
            messages.success(request, _("Candidate saved."))
            return redirect("webapp:rec_candidate_detail", candidate.id)
    return render(request, "webapp/recruitment/candidate_form.html", {"form": form, "title": candidate.name, "candidate": candidate})


@recruitment_view
def rec_candidate_detail(request, candidate_id):
    company = request.company
    candidate = get_object_or_404(Candidate.objects.for_company(company).select_related("agent"), id=candidate_id)
    if request.method == "POST" and request.POST.get("action") == "submit":
        job = get_object_or_404(JobOrder.objects.for_company(company), id=pick_id(request.POST.get("job")))
        try:
            added, skipped = svc.submit(company=company, job=job, candidates=[candidate])
            if added:
                messages.success(request, _("Added to %(job)s.") % {"job": f"{job.number} {job.position}"})
            else:
                messages.warning(request, _("Already added or not suitable: %(names)s") % {"names": candidate.name})
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:rec_candidate_detail", candidate.id)
    placements = candidate.placements.select_related("job_order__client").order_by("-updated_at")
    today = timezone.localdate()
    days = (candidate.passport_expiry - today).days if candidate.passport_expiry else None
    return render(request, "webapp/recruitment/candidate_detail.html", {
        "c": candidate, "placements": placements, "today": today, "passport_days": days,
        "passport_note": _("Passport expires in %(d)s days.") % {"d": days} if days is not None else "",
        "open_jobs": JobOrder.objects.for_company(company).filter(status="open").exclude(placements__candidate=candidate)
        .select_related("client").order_by("-created_at")[:100],
        "whatsapp": _wa(candidate.phone, _("Hello %(name)s, this is %(company)s.") % {"name": candidate.name, "company": company.name})})


@recruitment_view
def rec_candidate_cv(request, candidate_id):
    candidate = get_object_or_404(Candidate.objects.for_company(request.company), id=candidate_id)
    if not candidate.cv:
        raise Http404
    try:
        handle = candidate.cv.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("The file is no longer stored on the server. Upload it again.")
    name = candidate.cv.name.rsplit("/", 1)[-1]
    return FileResponse(handle, filename=name, as_attachment=request.GET.get("download") == "1",
                        content_type=mimetypes.guess_type(name)[0] or "application/octet-stream")


# ------------------------------------------------------------------ placement

STAGE_FIELDS = {
    "interview": ["interview_at"], "selected": ["offered_salary"], "medical": ["medical_date", "medical_result"],
    "visa": ["visa_number", "visa_expiry"], "ticket": ["ticket_date"], "deployed": ["joining_date"],
}


def _parse_stage_fields(request):
    from django.utils.dateparse import parse_date, parse_datetime
    from apps.industry.common import money
    values = {}
    for name in ("medical_date", "visa_expiry", "ticket_date", "joining_date"):
        if request.POST.get(name):
            values[name] = parse_date(request.POST[name])
    if request.POST.get("interview_at"):
        moment = parse_datetime(request.POST["interview_at"])
        if moment is not None and timezone.is_naive(moment):
            moment = timezone.make_aware(moment)
        values["interview_at"] = moment
    if request.POST.get("medical_result") in dict(Placement.MEDICAL):
        values["medical_result"] = request.POST["medical_result"]
    if request.POST.get("visa_number") is not None:
        values["visa_number"] = request.POST.get("visa_number", "")[:50]
    if request.POST.get("offered_salary"):
        values["offered_salary"] = money(request.POST["offered_salary"], "salary")
    if request.POST.get("fee"):
        values["fee"] = money(request.POST["fee"], "fee")
    if request.POST.get("notes") is not None:
        values["notes"] = request.POST.get("notes", "")[:4000]
    return values


@recruitment_view
def rec_placement(request, placement_id):
    company = request.company
    placement = get_object_or_404(Placement.objects.for_company(company).select_related(
        "job_order__client", "candidate", "invoice", "candidate_invoice"), id=placement_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "update":
                svc.move(placement, request.POST.get("stage") or placement.stage, **_parse_stage_fields(request))
                messages.success(request, _("Saved."))
            elif action == "bill_client":
                inv = svc.bill_client(company=company, user=request.user, placement=placement, amount=request.POST.get("amount"))
                messages.success(request, _("Invoice %(number)s created for the client.") % {"number": inv.invoice_number})
            elif action == "bill_candidate":
                inv = svc.bill_candidate(company=company, user=request.user, placement=placement, amount=request.POST.get("amount"))
                messages.success(request, _("Invoice %(number)s created for the candidate.") % {"number": inv.invoice_number})
            elif action == "cost":
                method = request.POST.get("method") if request.POST.get("method") in dict(PAYMENT_METHODS) else "cash"
                svc.add_cost(company=company, user=request.user, placement=placement, cost_type=request.POST.get("cost_type"),
                             amount=request.POST.get("amount"), paid_to=request.POST.get("paid_to") or "",
                             payment_method="bank" if method == "bank" else method)
                messages.success(request, _("Cost recorded in expenses."))
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:rec_placement", placement.id)
    c, job = placement.candidate, placement.job_order
    texts = {
        "interview": _("Dear %(name)s, your interview for %(position)s (%(client)s) is on %(when)s. Please bring your passport and CV.") % {
            "name": c.name, "position": job.position, "client": job.client.name,
            "when": timezone.localtime(placement.interview_at).strftime("%d %b %Y %H:%M") if placement.interview_at else "—"},
        "selected": _("Congratulations %(name)s! You are selected for %(position)s with %(client)s.") % {
            "name": c.name, "position": job.position, "client": job.client.name},
        "ticket": _("Dear %(name)s, your travel date is %(date)s. Please be ready with your passport.") % {
            "name": c.name, "date": placement.ticket_date.strftime("%d %b %Y") if placement.ticket_date else "—"},
    }
    flow = [code for code, _label in Placement.STAGES if code not in ("rejected", "withdrawn")]
    here = flow.index(placement.stage) if placement.stage in flow else -1
    steps = [(label, "now" if i == here else "done" if i < here else "")
             for i, (code, label) in enumerate((c, l) for c, l in Placement.STAGES if c in flow)]
    return render(request, "webapp/recruitment/placement.html", {
        "p": placement, "steps": steps, "c": c, "job": job, "stages": Placement.STAGES, "medical": Placement.MEDICAL,
        "money": svc.placement_money(placement), "costs": placement.costs.select_related("expense").order_by("-date"),
        "cost_types": PlacementCost.TYPES, "methods": PAYMENT_METHODS,
        "wa": {k: _wa(c.phone, v) for k, v in texts.items()},
        "wa_client": _wa(job.client.phone, f"{job.number} {job.position}: {c.name} — {placement.get_stage_display()}"),
    })


def _msgids():  # choice labels shown with {% translate %}, for the translation catalogue
    return [_("Open"), _("On hold"), _("Filled"), _("Closed"), _("Available"), _("In process"), _("Placed"),
            _("Not suitable"), _("CV sent"), _("Shortlisted"), _("Interview"), _("Selected"), _("Medical"), _("Visa"),
            _("Ticket"), _("Joined / deployed"), _("Rejected"), _("Withdrawn"), _("Pending"), _("Fit"), _("Unfit"),
            _("Air ticket"), _("Agent commission"), _("Documents / attestation"), _("Other"), _("Any"), _("Male"),
            _("Female"), _("Cash"), _("Card"), _("Bank transfer"),
            _("Free replacement period after joining."), _("Preferred nationality, if any."),
            _("Accommodation, food, transport…")]

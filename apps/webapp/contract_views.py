"""Maintenance / service contracts (AMC): list, new contract, contract page (visits, billing, renew, pause)."""
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy as _l
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.industry import contracts as svc
from apps.verticals.saloon.models import ServiceCase, ServiceContract

from .views import require_business_group


def staff_view(view):
    """Service and project businesses — and shops that run contracts (a computer shop's printer AMC)."""
    from functools import wraps
    from apps.modules.catalog import business_features
    guarded = require_business_group("service", "project")(view)

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        company = getattr(request, "company", None)
        if company is not None and company.business_type_id and \
                "contracts" in business_features(company.business_type.code):
            return view(request, *args, **kwargs)
        return guarded(request, *args, **kwargs)
    return login_required(wrapped)


class ContractForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label=_l("Customer"))
    new_name = forms.CharField(max_length=150, required=False, label=_l("…or new customer name"))
    new_phone = forms.CharField(max_length=20, required=False, label=_l("Phone (WhatsApp)"))
    title = forms.CharField(max_length=200, label=_l("Contract name"),
                            widget=forms.TextInput(attrs={"placeholder": _l("e.g. AC maintenance – 4 split units")}))
    site_name = forms.CharField(max_length=200, required=False, label=_l("Site / equipment"),
                                widget=forms.TextInput(attrs={"placeholder": _l("e.g. Villa 12 / Office 3rd floor")}))
    identifier = forms.CharField(max_length=100, required=False, label=_l("Reference / serial no."))
    site_address = forms.CharField(required=False, label=_l("Address"), widget=forms.Textarea(attrs={"rows": 2}))
    start_date = forms.DateField(label=_l("Starts"), widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label=_l("Ends"), widget=forms.DateInput(attrs={"type": "date"}))
    visit_every = forms.ChoiceField(choices=ServiceContract.EVERY, initial="quarterly", label=_l("Visit"))
    first_visit = forms.DateField(required=False, label=_l("First visit"), widget=forms.DateInput(attrs={"type": "date"}))
    preferred_time = forms.TimeField(required=False, label=_l("Usual time"), widget=forms.TimeInput(attrs={"type": "time"}))
    visit_minutes = forms.IntegerField(min_value=5, max_value=1440, initial=60, label=_l("Minutes per visit"))
    staff = forms.ModelChoiceField(queryset=Employee.objects.none(), required=False, label=_l("Usual staff"))
    visit_task = forms.CharField(required=False, label=_l("What to do on every visit"),
                                 widget=forms.Textarea(attrs={"rows": 3, "placeholder": _l("Clean filters, check gas, test cooling…")}))
    contract_value = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, label=_l("Contract value (total)"))
    billing = forms.ChoiceField(choices=ServiceContract.BILLING, initial="upfront", label=_l("Billing"))
    bill_amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False,
                                     label=_l("Amount per bill / visit"),
                                     help_text=_l("Leave empty to split the contract value."))
    notes = forms.CharField(required=False, label=_l("Notes"), widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
        self.fields["staff"].queryset = Employee.objects.for_company(company).filter(is_active=True).order_by("name")

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
        found = Customer.objects.for_company(self.company).filter(phone=phone).first() if phone else None
        return found or Customer.objects.create(company=self.company, name=data["new_name"].strip(), phone=phone,
                                                address=(data.get("site_address") or "")[:500])


@staff_view
def contract_list(request):
    company = request.company
    show = request.GET.get("show", "active")
    q = (request.GET.get("q") or "").strip()
    qs = ServiceContract.objects.for_company(company).select_related("customer", "staff").annotate(
        visit_count=Count("visits"), done_count=Count("visits", filter=Q(visits__status="completed")))
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(customer__name__icontains=q) |
                       Q(customer__phone__icontains=q))
    today = timezone.localdate()
    if show == "ending":
        ids = list(svc.expiring(company).values_list("id", flat=True))
        rows = list(qs.filter(id__in=ids))
    elif show == "closed":
        rows = list(qs.filter(status__in=("ended", "cancelled")).order_by("-end_date")[:200])
    else:
        rows = list(qs.filter(status__in=("active", "paused")))
    for c in rows:
        c.days_left = (c.end_date - today).days
    active = ServiceContract.objects.for_company(company).filter(status="active")
    return render(request, "webapp/contracts/list.html", {
        "rows": rows, "show": show, "q": q, "currency": company.default_currency,
        "stats": {"active": active.count(), "ending": svc.expiring(company).count(),
                  "value": sum((c.contract_value for c in active), Decimal("0")),
                  "visits_week": ServiceCase.objects.for_company(company).filter(
                      contract__isnull=False, scheduled_at__date__gte=today,
                      scheduled_at__date__lte=today + timedelta(days=7), status__in=("open", "in_progress", "waiting")).count()},
    })


@staff_view
def contract_new(request):
    company = request.company
    today = timezone.localdate()
    initial = {"start_date": today, "end_date": today.replace(year=today.year + 1) - timedelta(days=1)}
    if request.GET.get("customer", "").isdigit():
        initial["customer"] = int(request.GET["customer"])
    form = ContractForm(request.POST or None, company=company, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            contract = svc.create_contract(
                company, request.user, customer=form.customer_obj(), title=d["title"], start_date=d["start_date"],
                end_date=d["end_date"], visit_every=d["visit_every"], first_visit=d.get("first_visit"),
                preferred_time=d.get("preferred_time"), visit_minutes=d.get("visit_minutes"), staff=d.get("staff"),
                visit_task=d.get("visit_task"), contract_value=d["contract_value"], billing=d["billing"],
                bill_amount=d.get("bill_amount"), site_name=d.get("site_name"), identifier=d.get("identifier"),
                site_address=d.get("site_address"), notes=d.get("notes"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("Contract %(number)s saved. Visits are planned by themselves.") % {
                "number": contract.number})
            return redirect("webapp:contract_detail", contract_id=contract.id)
    return render(request, "webapp/contracts/new.html", {"form": form})


@staff_view
def contract_detail(request, contract_id):
    company = request.company
    contract = get_object_or_404(ServiceContract.objects.for_company(company)
                                 .select_related("customer", "staff", "profile", "recurring", "upfront_invoice",
                                                 "renewed_from"), id=contract_id)
    visits = list(contract.visits.select_related("assigned_staff", "invoice").order_by("scheduled_at", "id"))
    renewal = contract.renewals.exclude(status="cancelled").first()
    return render(request, "webapp/contracts/detail.html", {
        "c": contract, "visits": visits, "upcoming": svc.upcoming_dates(contract), "renewal": renewal,
        "currency": company.default_currency, "wa_renew": svc.renewal_whatsapp(contract),
        "days_left": (contract.end_date - timezone.localdate()).days,
        "done": sum(1 for v in visits if v.status == "completed"),
        "total_visits": len(visits) + len(svc.visit_dates(contract.next_visit_date, contract.end_date, contract.visit_every))
        if contract.next_visit_date else len(visits),
    })


@staff_view
@require_POST
def contract_action(request, contract_id):
    company = request.company
    contract = get_object_or_404(ServiceContract.objects.for_company(company), id=contract_id)
    what = request.POST.get("do")
    try:
        if what == "plan":
            n = svc.plan_visits(contract, ahead=int(request.POST.get("days") or 7) if str(request.POST.get("days") or "").isdigit() else 7)
            messages.success(request, _("%(n)s visit(s) added to the job cards.") % {"n": n})
        elif what == "pause":
            svc.pause(contract)
            messages.success(request, _("Contract paused — no visits or bills until you resume it."))
        elif what == "resume":
            svc.resume(contract)
            messages.success(request, _("Contract resumed."))
        elif what == "cancel":
            svc.cancel(contract)
            messages.success(request, _("Contract cancelled. Future visits were cancelled too."))
        elif what == "renew":
            new = svc.renew(contract, request.user, contract_value=request.POST.get("contract_value"))
            messages.success(request, _("Renewed as %(number)s.") % {"number": new.number})
            return redirect("webapp:contract_detail", contract_id=new.id)
        else:
            raise Http404
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("webapp:contract_detail", contract_id=contract.id)

"""Property management: properties, units, leases, monthly rent and overdue rent."""
from datetime import date

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.models import Customer
from apps.industry import property as svc
from apps.industry.education import month_bounds, month_key
from apps.industry.models import Lease, Property, RentalUnit, RentCharge

from .industry_access import require_industry

property_view = require_industry("leases")
DATE = forms.DateInput(attrs={"type": "date"})


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ["name", "kind", "address", "owner_name"]


class UnitForm(forms.ModelForm):
    class Meta:
        model = RentalUnit
        fields = ["property", "name", "kind", "bedrooms", "size", "monthly_rent", "is_active"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = Property.objects.for_company(company)


class LeaseForm(forms.Form):
    unit = forms.ModelChoiceField(queryset=RentalUnit.objects.none())
    tenant = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    new_tenant_name = forms.CharField(max_length=255, required=False)
    new_tenant_phone = forms.CharField(max_length=20, required=False)
    start_date = forms.DateField(widget=DATE)
    end_date = forms.DateField(widget=DATE)
    monthly_rent = forms.DecimalField(min_value=0, decimal_places=2)
    due_day = forms.IntegerField(min_value=1, max_value=28, initial=1)
    security_deposit = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    bill_first_month = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["unit"].queryset = RentalUnit.objects.for_company(company).filter(is_active=True).select_related("property")
        self.fields["tenant"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("tenant") and not (cleaned.get("new_tenant_name") or "").strip():
            self.add_error("tenant", _("Choose a tenant or type a new tenant's name."))
        return cleaned

    def get_tenant(self):
        if self.cleaned_data.get("tenant"):
            return self.cleaned_data["tenant"]
        return Customer.objects.create(company=self.company, name=self.cleaned_data["new_tenant_name"].strip(),
                                       phone=(self.cleaned_data.get("new_tenant_phone") or "").strip())


@property_view
def property_home(request):
    company = request.company
    summary = svc.summary(company)
    properties = Property.objects.for_company(company).prefetch_related("units")
    active = {l.unit_id: l for l in Lease.objects.for_company(company).filter(status="active", start_date__lte=timezone.localdate(),
                                                                                end_date__gte=timezone.localdate()).select_related("tenant")}
    return render(request, "webapp/industry/property_home.html", {
        "summary": summary, "overdue": svc.overdue(company)[:20],
        "properties": [{"p": p, "units": [(u, active.get(u.pk)) for u in p.units.all()]} for p in properties]})


@property_view
def property_form(request, property_id=None):
    company = request.company
    obj = get_object_or_404(Property.objects.for_company(company), pk=property_id) if property_id else None
    form = PropertyForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        prop = form.save(commit=False)
        prop.company = company
        prop.save()
        messages.success(request, _("%(name)s saved.") % {"name": prop.name})
        return redirect("webapp:property_home")
    return render(request, "webapp/industry/simple_form.html", {
        "form": form, "title": obj.name if obj else _("New property"), "back": "webapp:property_home"})


@property_view
def unit_form(request, unit_id=None):
    company = request.company
    obj = get_object_or_404(RentalUnit.objects.for_company(company), pk=unit_id) if unit_id else None
    form = UnitForm(request.POST or None, instance=obj, company=company,
                    initial={"property": request.GET.get("property")} if not obj else None)
    if request.method == "POST" and form.is_valid():
        unit = form.save(commit=False)
        unit.company = company
        unit.save()
        svc.unit_product(unit)
        messages.success(request, _("%(name)s saved.") % {"name": unit.name})
        return redirect("webapp:property_home")
    return render(request, "webapp/industry/simple_form.html", {
        "form": form, "title": str(obj) if obj else _("New unit"), "back": "webapp:property_home"})


@property_view
def lease_add(request):
    company = request.company
    initial = {"start_date": timezone.localdate(), "due_day": 1, "bill_first_month": True, "security_deposit": 0}
    unit = RentalUnit.objects.for_company(company).filter(pk=request.GET.get("unit") or 0).first()
    if unit:
        today = timezone.localdate()
        initial.update(unit=unit.pk, monthly_rent=unit.monthly_rent,
                       end_date=date(today.year + 1, today.month, min(today.day, 28)))
    form = LeaseForm(request.POST or None, company=company, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            lease = svc.create_lease(company=company, user=request.user, unit=d["unit"], tenant=form.get_tenant(),
                                     start_date=d["start_date"], end_date=d["end_date"], monthly_rent=d["monthly_rent"],
                                     due_day=d["due_day"], security_deposit=d.get("security_deposit") or 0,
                                     notes=d.get("notes", ""), bill_first_month=d.get("bill_first_month"))
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, _("Lease %(number)s created.") % {"number": lease.number})
            return redirect("webapp:lease_detail", lease_id=lease.pk)
    return render(request, "webapp/industry/lease_form.html", {"form": form})


@property_view
def lease_detail(request, lease_id):
    company = request.company
    lease = get_object_or_404(Lease.objects.for_company(company).select_related("unit__property", "tenant"), pk=lease_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action in ("end", "terminate"):
                svc.end_lease(lease, on=timezone.localdate(), early=action == "terminate")
                messages.success(request, _("Lease closed."))
            elif action == "deposit_returned" and lease.security_deposit:
                lease.deposit_returned = True
                lease.save(update_fields=["deposit_returned"])
                messages.success(request, _("Security deposit marked as returned."))
            elif action == "bill_month":
                invoices = svc.bill(company=company, user=request.user, leases=[lease], key=month_key(timezone.localdate()))
                messages.success(request, _("Rent billed.") if invoices else _("This month's rent is already billed."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("webapp:lease_detail", lease_id=lease.pk)
    charges = lease.charges.select_related("invoice")
    today = timezone.localdate()
    return render(request, "webapp/industry/lease_detail.html", {
        "lease": lease, "charges": charges, "today": today,
        "days_left": (lease.end_date - today).days,
        "balance": sum(((c.invoice.total - c.invoice.amount_paid) for c in charges if c.invoice_id), 0)})


@property_view
def rent_run(request):
    company = request.company
    raw = request.GET.get("month") or request.POST.get("month") or ""
    try:
        month_bounds(raw)
        key = raw
    except (ValueError, TypeError):
        key = month_key(timezone.localdate())
    if request.method == "POST":
        try:
            invoices = svc.generate_month(company=company, user=request.user, key=key)
            messages.success(request, _("%(count)s rent invoices created for %(month)s.") % {"count": len(invoices), "month": key})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(f"{request.path}?month={key}")
    first, _last = month_bounds(key)
    prev_first = date(first.year - (first.month == 1), 12 if first.month == 1 else first.month - 1, 1)
    next_first = date(first.year + (first.month == 12), 1 if first.month == 12 else first.month + 1, 1)
    pending = svc.leases_for_month(company, key)
    return render(request, "webapp/industry/rent_run.html", {
        "month": key, "month_date": first, "pending": pending,
        "pending_total": sum((l.monthly_rent for l in pending), 0),
        "charges": RentCharge.objects.for_company(company).filter(period=key)
                   .select_related("lease__tenant", "lease__unit__property", "invoice"),
        "prev": month_key(prev_first), "next": month_key(next_first)})


@property_view
def lease_list(request):
    status = request.GET.get("status") or "active"
    qs = Lease.objects.for_company(request.company).select_related("unit__property", "tenant")
    if status in dict(Lease.STATUS):
        qs = qs.filter(status=status)
    return render(request, "webapp/industry/lease_list.html", {"leases": qs, "status": status, "statuses": Lease.STATUS,
                                                               "today": timezone.localdate()})

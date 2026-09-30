"""Bookings: calendar board, rooms/vehicles/halls, reservations, check-in/out."""
from datetime import datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.customers.models import Customer
from apps.industry import bookings as svc
from apps.industry.common import PAYMENT_METHODS
from apps.industry.models import BookableResource, Booking
from apps.modules.catalog import BOOKING_TERMS

from .industry_access import require_industry

bookings_view = require_industry("bookings")
DT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


def _terms(company):
    return dict(zip(("resource", "resources", "booking", "unit"),
                    BOOKING_TERMS.get(company.business_type.code, ("Resource", "Resources", "Booking", "day"))))


class ResourceForm(forms.ModelForm):
    class Meta:
        model = BookableResource
        fields = ["name", "kind", "rate", "rate_unit", "capacity", "details", "sort_order", "is_active"]


class BookingForm(forms.Form):
    resource = forms.ModelChoiceField(queryset=BookableResource.objects.none())
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    new_customer_name = forms.CharField(max_length=255, required=False)
    new_customer_phone = forms.CharField(max_length=20, required=False)
    start = forms.DateTimeField(widget=DT, input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    end = forms.DateTimeField(widget=DT, input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    guests = forms.IntegerField(min_value=1, max_value=5000, initial=1)
    advance = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    advance_method = forms.ChoiceField(choices=PAYMENT_METHODS, initial="cash")
    security_deposit = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, company=None, editing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["resource"].queryset = BookableResource.objects.for_company(company).filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
        if editing:
            for name in ("customer", "new_customer_name", "new_customer_phone", "advance", "advance_method",
                         "security_deposit", "notes"):
                del self.fields[name]

    def clean(self):
        cleaned = super().clean()
        if "customer" in self.fields and not cleaned.get("customer") and not (cleaned.get("new_customer_name") or "").strip():
            self.add_error("customer", _("Choose a customer or type a new customer's name."))
        return cleaned

    def get_customer(self):
        if self.cleaned_data.get("customer"):
            return self.cleaned_data["customer"]
        return Customer.objects.create(company=self.company, name=self.cleaned_data["new_customer_name"].strip(),
                                       phone=(self.cleaned_data.get("new_customer_phone") or "").strip())


class CheckoutForm(forms.Form):
    extras = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    extras_note = forms.CharField(max_length=255, required=False)
    discount = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    paid_now = forms.DecimalField(min_value=0, decimal_places=2, required=False, initial=0)
    method = forms.ChoiceField(choices=PAYMENT_METHODS, initial="cash")


@bookings_view
def booking_board(request):
    company = request.company
    start = parse_date(request.GET.get("start") or "") or timezone.localdate()
    days = 14 if request.GET.get("days") not in ("7", "30") else int(request.GET["days"])
    rows, window_start, window_end = svc.board(company, start, days)
    today = timezone.localdate()
    now = timezone.now()
    day_start = timezone.make_aware(datetime.combine(today, time.min))
    day_end = day_start + timedelta(days=1)
    active = Booking.objects.for_company(company).select_related("resource", "customer")
    arrivals = active.filter(status="reserved", start__lt=day_end).order_by("start")[:30]
    departures = active.filter(status="checked_in", end__lt=day_end).order_by("end")[:30]
    in_use = active.filter(status="checked_in").count()
    resource_count = len(rows)
    return render(request, "webapp/industry/booking_board.html", {
        "terms": _terms(company), "rows": rows, "window_start": window_start, "days": days,
        "day_labels": [start + timedelta(days=i) for i in range(days)],
        "prev_start": start - timedelta(days=days), "next_start": start + timedelta(days=days),
        "today": today, "now": now, "now_left": (now - window_start).total_seconds() / (window_end - window_start).total_seconds() * 100,
        "arrivals": arrivals, "departures": departures, "in_use": in_use, "resource_count": resource_count,
        "occupancy": round(in_use * 100 / resource_count) if resource_count else 0,
        "overdue": active.filter(status="checked_in", end__lt=now).count(),
    })


@bookings_view
def booking_list(request):
    qs = Booking.objects.for_company(request.company).select_related("resource", "customer", "invoice")
    status = request.GET.get("status") or ""
    if status in dict(Booking.STATUS):
        qs = qs.filter(status=status)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(customer__name__icontains=q) | Q(customer__phone__icontains=q)
                       | Q(resource__name__icontains=q))
    return render(request, "webapp/industry/booking_list.html", {
        "terms": _terms(request.company), "bookings": qs[:300], "status": status, "q": q,
        "statuses": Booking.STATUS})


@bookings_view
def resource_list(request):
    return render(request, "webapp/industry/resource_list.html", {
        "terms": _terms(request.company),
        "resources": BookableResource.objects.for_company(request.company)})


@bookings_view
def resource_form(request, resource_id=None):
    company = request.company
    obj = get_object_or_404(BookableResource.objects.for_company(company), pk=resource_id) if resource_id else None
    terms = _terms(company)
    initial = {} if obj else {"rate_unit": terms["unit"], "kind": {"Room": "room", "Vehicle": "vehicle", "Equipment": "equipment",
                                                                   "Hall": "hall", "Space": "space"}.get(terms["resource"], "other")}
    form = ResourceForm(request.POST or None, instance=obj, initial=initial)
    if request.method == "POST" and form.is_valid():
        resource = form.save(commit=False)
        resource.company = company
        resource.save()
        svc.resource_product(resource)
        messages.success(request, _("%(name)s saved.") % {"name": resource.name})
        return redirect("webapp:booking_resources")
    return render(request, "webapp/industry/resource_form.html", {"form": form, "terms": terms, "obj": obj})


def _rates(company):
    return {str(r.pk): {"rate": float(r.rate), "unit": r.rate_unit, "label": r.get_rate_unit_display().lower()}
            for r in BookableResource.objects.for_company(company).filter(is_active=True)}


def _parse_initial(request, company):
    initial = {"guests": 1, "advance": 0, "security_deposit": 0}
    if request.GET.get("resource"):
        initial["resource"] = request.GET["resource"]
    day = parse_date(request.GET.get("date") or "")
    if day:
        unit = _terms(company)["unit"]
        start_time = {"night": time(14, 0), "hour": time(9, 0), "event": time(18, 0)}.get(unit, time(10, 0))
        start = datetime.combine(day, start_time)
        end = {"night": start.replace(hour=12) + timedelta(days=1), "hour": start + timedelta(hours=1),
               "event": start + timedelta(hours=6)}.get(unit, start + timedelta(days=1))
        initial.update(start=start, end=end)
    return initial


@bookings_view
def booking_add(request):
    company = request.company
    form = BookingForm(request.POST or None, company=company, initial=_parse_initial(request, company))
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            booking = svc.create_booking(
                company=company, user=request.user, resource=d["resource"], customer=form.get_customer(),
                start=d["start"], end=d["end"], guests=d["guests"], advance=d.get("advance") or 0,
                advance_method=d["advance_method"], security_deposit=d.get("security_deposit") or 0,
                notes=d.get("notes", ""))
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, _("%(number)s booked.") % {"number": booking.number})
            return redirect("webapp:booking_detail", booking_id=booking.pk)
    return render(request, "webapp/industry/booking_form.html", {"form": form, "terms": _terms(company),
                                                                "rates": _rates(company)})


@bookings_view
def booking_edit(request, booking_id):
    company = request.company
    booking = get_object_or_404(Booking.objects.for_company(company), pk=booking_id)
    form = BookingForm(request.POST or None, company=company, editing=True, initial={
        "resource": booking.resource_id, "start": timezone.localtime(booking.start),
        "end": timezone.localtime(booking.end), "guests": booking.guests})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            svc.reschedule(booking, resource=d["resource"], start=d["start"], end=d["end"], guests=d["guests"])
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, _("Booking updated."))
            return redirect("webapp:booking_detail", booking_id=booking.pk)
    return render(request, "webapp/industry/booking_form.html", {"form": form, "terms": _terms(company), "booking": booking,
                                                                "rates": _rates(company)})


@bookings_view
def booking_detail(request, booking_id):
    company = request.company
    booking = get_object_or_404(Booking.objects.for_company(company).select_related("resource", "customer", "invoice"),
                                pk=booking_id)
    checkout = CheckoutForm(request.POST if request.POST.get("action") == "check_out" else None)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "check_in":
                svc.check_in(booking)
                messages.success(request, _("Checked in."))
            elif action == "cancel":
                svc.cancel(booking)
                messages.success(request, _("Booking cancelled."))
            elif action == "no_show":
                svc.cancel(booking, status="no_show")
                messages.success(request, _("Marked as no-show."))
            elif action == "deposit_returned" and booking.security_deposit:
                booking.deposit_returned = True
                booking.save(update_fields=["deposit_returned"])
                messages.success(request, _("Security deposit marked as returned."))
            elif action == "check_out" and checkout.is_valid():
                d = checkout.cleaned_data
                booking = svc.check_out(booking, user=request.user, extras=d.get("extras") or 0,
                                        extras_note=d.get("extras_note", ""), discount=d.get("discount") or 0,
                                        paid_now=d.get("paid_now") or 0, method=d["method"])
                messages.success(request, _("Checked out. Invoice %(number)s created.") % {"number": booking.invoice.invoice_number})
            if action != "check_out" or checkout.is_valid():
                return redirect("webapp:booking_detail", booking_id=booking.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("webapp:booking_detail", booking_id=booking.pk)
    preview = svc.charge_preview(booking) if booking.status == "checked_in" else None
    if preview:
        preview["due"] = max(preview["rent"] - booking.advance, 0)
        if not checkout.is_bound:
            checkout = CheckoutForm(initial={"paid_now": preview["due"], "extras": 0, "discount": 0})
    return render(request, "webapp/industry/booking_detail.html", {
        "booking": booking, "terms": _terms(company), "preview": preview, "checkout": checkout,
        "overdue": booking.status == "checked_in" and booking.end < timezone.now(),
        "balance": (booking.invoice.total - booking.invoice.amount_paid) if booking.invoice else None})

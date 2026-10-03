"""Online booking: public form (widget / WordPress / BookPilot page) and the business's request inbox."""
import io
import json
import zipfile
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt

from apps.industry import online_booking as svc
from apps.industry.models import BookableResource, BookingSite, OnlineBooking
from apps.modules.catalog import BOOKING_TERMS

RATE_LIMIT = 10


def _origin(request):
    from urllib.parse import urlsplit
    for header in ("Origin", "Referer"):
        value = request.headers.get(header) or ""
        if value:
            parts = urlsplit(value)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
    return ""


def _ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "?"


def _too_many(request, site):
    key = f"online-booking:{site.pk}:{_ip(request)}"
    if cache.add(key, 1, 3600):
        return False
    try:
        return cache.incr(key) > RATE_LIMIT
    except ValueError:
        cache.set(key, 1, 3600)
        return False


def _site_or_404(slug):
    site = svc.public_site(slug)
    if site is None:
        raise Http404("Online booking is not available.")
    return site


def _labels(company, kind):
    code = company.business_type.code
    resource, resources, booking, unit = BOOKING_TERMS.get(code, ("Item", "Items", "Booking", "day"))
    start, end = {"hotel_apartment": ("Check-in", "Check-out"), "car_rental": ("Pick-up", "Return"),
                  "equipment_rental": ("From", "Until"), "wedding_party_hall": ("Event date", "Ends"),
                  "coworking_space": ("Date", "Until")}.get(code, ("Date", "Until"))
    if kind == "appointment":
        item = {"gym": "Membership / trial", "vehicle_wash": "Wash package"}.get(code, "Service")
    else:
        item = resource
    return {"item": item, "start": start, "end": end, "booking": booking}


def _config(request, site):
    company = site.company
    kind = svc.booking_kind(company)
    return {
        "kind": kind, "company": company.name, "color": site.accent_color or "#0f766e",
        "headline": site.headline, "note": site.note, "currency": company.default_currency,
        "items": svc.items(company, kind), "labels": _labels(company, kind),
        "endpoint": request.build_absolute_uri(reverse("webapp:book_submit", args=[site.slug])) + "?format=json",
        "min_date": timezone.localdate().isoformat(),
        "max_date": (timezone.localdate() + timezone.timedelta(days=site.max_days_ahead)).isoformat(),
        "whatsapp": "".join(ch for ch in (site.whatsapp or "") if ch.isdigit()),
    }


# ------------------------------------------------------------------ public

@xframe_options_exempt
def book_page(request, slug):
    site = _site_or_404(slug)
    form_js = reverse("webapp:book_form_js", args=[slug])
    return render(request, "webapp/online_booking/public.html", {"site": site, "company": site.company, "form_js": form_js})


def book_options(request, slug):
    site = _site_or_404(slug)
    response = JsonResponse(_config(request, site))
    response["Access-Control-Allow-Origin"] = "*"
    return response


def book_form_js(request, slug):
    site = svc.public_site(slug)
    if site is None:
        return HttpResponse("/* BookPilot: online booking is not set up */", content_type="application/javascript")
    cfg = json.dumps(_config(request, site)).replace("</", "<\\/")
    response = HttpResponse(render_to_string("webapp/online_booking/form.js", {"cfg": cfg}),
                            content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "public, max-age=120"
    response["Access-Control-Allow-Origin"] = "*"
    return response


@xframe_options_exempt
@csrf_exempt  # posted from other websites; honeypot + rate limit
def book_submit(request, slug):
    site = _site_or_404(slug)
    origin = _origin(request)
    if request.method == "OPTIONS":
        response = HttpResponse()
    elif request.method != "POST":
        return redirect("webapp:book_page", slug)
    else:
        response = None
    if response is None:
        if request.POST.get("company_website"):
            body, status = {"ok": True}, 201
        elif _too_many(request, site):
            body, status = {"ok": False, "error": _("Too many requests from this connection. Please call or WhatsApp us.")}, 429
        else:
            own = origin == f"{request.scheme}://{request.get_host()}"
            try:
                req = svc.create_request(site, request.POST, source="" if own or not origin else origin.split("://", 1)[-1])
                body, status = {"ok": True, "reference": req.number}, 201
            except ValidationError as exc:
                body, status = {"ok": False, "error": " ".join(_(m) for m in exc.messages)}, 400
        response = JsonResponse(body, status=status)
    if origin:
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
        response["Access-Control-Allow-Headers"] = "Content-Type"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


# ------------------------------------------------------------------ staff side

def _booking_view(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.company is None:
            return render(request, "webapp/no_company.html")
        if svc.booking_kind(request.company) is None:
            messages.error(request, _("Online booking isn't available for this business type."))
            return redirect("webapp:dashboard")
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def owner_only(view):
    """Website form, WordPress plugin and careers-site settings are for the business owner only."""
    from functools import wraps

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if getattr(getattr(request, "role", None), "name", None) != "Owner":
            messages.error(request, _("Only the business owner can open this page."))
            return redirect("webapp:dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def _wa(phone, text):
    return f"https://wa.me/{''.join(ch for ch in (phone or '') if ch.isdigit())}?text={quote(text)}"


@_booking_view
def ob_inbox(request):
    company = request.company
    status = request.GET.get("status", "new")
    qs = OnlineBooking.objects.for_company(company)
    counts = {s: qs.filter(status=s).count() for s, _x in OnlineBooking.STATUS}
    if status in dict(OnlineBooking.STATUS):
        qs = qs.filter(status=status)
    return render(request, "webapp/online_booking/inbox.html", {
        "requests": qs.order_by("date", "time")[:300] if status == "new" else qs[:300], "status": status,
        "tabs": [(code, label, counts.get(code, 0)) for code, label in OnlineBooking.STATUS], "site": svc.site_for(company),
        "kind": svc.booking_kind(company)})


APPOINTMENT_FORMS = {"spa": "webapp:appointment_book", "beauty_parlour": "webapp:beauty_appointment_book",
                     "vehicle_wash": "webapp:wash_order_book", "gym": "webapp:member_enroll"}


@_booking_view
def ob_detail(request, request_id):
    company = request.company
    req = get_object_or_404(OnlineBooking.objects.for_company(company), id=request_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "confirm":
                table = resource = None
                if req.kind == "table" and request.POST.get("table"):
                    from apps.verticals.restaurant.models import DiningTable
                    table = DiningTable.objects.for_company(company).filter(id=request.POST["table"]).first()
                if req.kind == "resource" and request.POST.get("resource"):
                    resource = BookableResource.objects.for_company(company).filter(id=request.POST["resource"]).first()
                svc.confirm(req, request.user, table=table, resource=resource)
                req.refresh_from_db()
                messages.success(request, _("Booking confirmed. Send the confirmation on WhatsApp."))
                if req.kind == "appointment":
                    code = company.business_type.code
                    url = reverse(APPOINTMENT_FORMS.get(code, "webapp:saloon_appointment_book"))
                    params = {"customer": req.customer_id}
                    if req.item_id and code not in ("vehicle_wash", "gym"):
                        params["service"] = req.item_id
                    if req.time:
                        params["scheduled_at"] = f"{req.date:%Y-%m-%d}T{req.time:%H:%M}"
                    messages.info(request, _("Choose the staff member and save to finish the appointment."))
                    return redirect(url + "?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items()))
            elif action == "decline":
                svc.decline(req, request.user, request.POST.get("reason") or "")
                messages.success(request, _("Request declined. Let the customer know on WhatsApp."))
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("webapp:ob_detail", req.id)
    extra = {}
    if req.kind == "resource":
        from apps.industry.bookings import conflicts
        resources = list(BookableResource.objects.for_company(company).filter(is_active=True))
        for r in resources:
            start, end = svc.resource_times(req, r)
            r.busy = conflicts(r, start, end).exists()
        extra["resources"] = resources
        chosen = next((r for r in resources if r.id == req.item_id), None)
        if chosen:
            extra["window"] = svc.resource_times(req, chosen)
    if req.kind == "table":
        from apps.verticals.restaurant.models import DiningTable
        extra["tables"] = DiningTable.objects.for_company(company).filter(is_active=True)
    return render(request, "webapp/online_booking/detail.html", {
        "r": req, **extra,
        "wa_ok": _wa(req.phone, svc.reply_text(req, company, True)),
        "wa_no": _wa(req.phone, svc.reply_text(req, company, False)),
        "linked_url": _linked_url(req)})


def _linked_url(req):
    kind, _sep, pk = req.linked.partition(":")
    if kind == "booking" and pk:
        return reverse("webapp:booking_detail", args=[int(pk)])
    if kind == "reservation":
        return reverse("webapp:restaurant_reservations")
    return ""


class SiteForm(forms.ModelForm):
    slug = forms.CharField(max_length=80, label=_l("Web address name"))
    accent_color = forms.CharField(required=False, max_length=50, label=_l("Brand colour"),
                                   widget=forms.TextInput(attrs={"type": "color"}))

    class Meta:
        model = BookingSite
        fields = ["enabled", "slug", "headline", "note", "whatsapp", "accent_color", "min_notice_hours", "max_days_ahead"]
        labels = {"enabled": _l("Online booking is on"), "headline": _l("Headline"), "note": _l("Note above the form"),
                  "whatsapp": _l("WhatsApp number"), "min_notice_hours": _l("Minimum notice (hours)"),
                  "max_days_ahead": _l("How many days ahead people can book")}

    def clean_slug(self):
        from django.utils.text import slugify
        slug = slugify(self.cleaned_data["slug"])[:60]
        if not slug:
            raise ValidationError(_("Enter a short name for the address, e.g. gulf-manpower."))
        if BookingSite.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("This name is taken. Try another one."))
        return slug

    def clean_accent_color(self):
        import re
        color = (self.cleaned_data.get("accent_color") or "").strip()
        return color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "#0f766e"


@_booking_view
@owner_only
def ob_settings(request):
    company = request.company
    site = svc.site_for(company)
    form = SiteForm(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Online booking settings saved."))
        return redirect("webapp:ob_settings")
    page = request.build_absolute_uri(reverse("webapp:book_page", args=[site.slug]))
    form_js = request.build_absolute_uri(reverse("webapp:book_form_js", args=[site.slug]))
    kind = svc.booking_kind(company)
    return render(request, "webapp/online_booking/settings.html", {
        "site": site, "form": form, "page": page, "kind": kind, "items": svc.items(company, kind),
        "form_tag": f'<div class="bookpilot-booking"></div>\n<script src="{form_js}" defer></script>',
        "share": f"https://wa.me/?text={quote((site.headline or company.name) + chr(10) + page)}",
        "items_url": {"resource": "webapp:booking_resources", "appointment": _services_url(company)}.get(kind),
    })


def _services_url(company):
    code = company.business_type.code
    return {"spa": "webapp:spa_service_list", "beauty_parlour": "webapp:beauty_service_list", "gym": "webapp:plan_list",
            "vehicle_wash": "webapp:wash_package_list"}.get(code, "webapp:saloon_service_list")


@_booking_view
@owner_only
def ob_wp_plugin(request):
    site = svc.site_for(request.company)
    form_js = request.build_absolute_uri(reverse("webapp:book_form_js", args=[site.slug]))
    php = render_to_string("webapp/online_booking/wp_plugin.php.txt", {"form_js": form_js, "company": site.company.name})
    readme = render_to_string("webapp/online_booking/wp_readme.txt", {"company": site.company.name})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bookpilot-booking-form/bookpilot-booking-form.php", php)
        z.writestr("bookpilot-booking-form/readme.txt", readme)
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="bookpilot-booking-form.zip"'
    return response


def _msgids():
    return [_("Appointment"), _("Booking"), _("Table reservation"), _("Event enquiry"), _("New"), _("Confirmed"),
            _("Declined"), _("Enter your name and a phone / WhatsApp number."), _("Choose a date."),
            _("Choose a date from today onwards."), _("Choose a time."), _("Choose what you want to book."),
            _("Choose the check-out / return date."), _("The end date must be after the start date."),
            _("Online booking is not available."), _("Shown above the form, e.g. opening hours.")]

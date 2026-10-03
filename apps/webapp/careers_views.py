"""Public careers website for a recruitment agency, plus the agency's settings page for it."""
import json

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt

from apps.industry import careers as svc
from apps.industry.models import CareersSite, JobOrder

from .recruitment_views import recruitment_view

RATE_LIMIT = 8  # applications per hour per IP and site
LANGS = {"en", "ar", "ml"}


# ------------------------------------------------------------------ helpers

def _site_or_404(slug):
    site = svc.public_site(slug)
    if site is None:
        raise Http404("This careers page is not available.")
    return site


def _lang(request, response=None):
    code = request.GET.get("lang")
    if code in LANGS:
        translation.activate(code)
        request.LANGUAGE_CODE = code
        if response is not None:
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, code, max_age=365 * 86400, samesite="Lax")
    return response


def _public(request, template, context, status=200):
    _lang(request)
    response = render(request, template, context, status=status)
    response["X-Robots-Tag"] = "index, follow" if status == 200 else "noindex"
    return _lang(request, response)


def _ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")) or "?"


def _too_many(request, site):
    key = f"careers-apply:{site.pk}:{_ip(request)}"
    added = cache.add(key, 1, 3600)
    if added:
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3600)
        return False
    return count > RATE_LIMIT


def _cors(request, site, response):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin and origin in svc.origins(site):
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Key"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _wa(site):
    return "".join(ch for ch in (site.whatsapp or "") if ch.isdigit())


def _base(site):
    jobs = svc.public_jobs(site)
    return {"site": site, "company": site.company, "wa": _wa(site),
            "services": [s.strip() for s in site.services.splitlines() if s.strip()],
            "countries": [c.strip() for c in site.countries.split(",") if c.strip()],
            "job_count": jobs.count()}


# ------------------------------------------------------------------ public pages

@xframe_options_exempt
def careers_home(request, slug):
    site = _site_or_404(slug)
    jobs = svc.public_jobs(site)
    query = (request.GET.get("q") or "").strip()
    if query:
        jobs = jobs.filter(Q(position__icontains=query) | Q(work_location__icontains=query) | Q(public_summary__icontains=query))
    place = (request.GET.get("where") or "").strip()
    if place:
        jobs = jobs.filter(work_location__icontains=place)
    places = sorted({j.work_location.strip() for j in svc.public_jobs(site) if j.work_location.strip()})
    return _public(request, "webapp/careers/home.html", {**_base(site), "jobs": jobs[:200], "q": query, "where": place,
                                                         "places": places, "embed": request.GET.get("embed") == "1"})


@xframe_options_exempt
def careers_job(request, slug, job_id):
    site = _site_or_404(slug)
    job = svc.public_job(site, job_id)
    if job is None:
        return _public(request, "webapp/careers/closed.html", _base(site), status=404)
    return _public(request, "webapp/careers/apply.html", {**_base(site), "no_float": True, "job": job, "post": {},
                                                          "embed": request.GET.get("embed") == "1"})


def _origin(request):
    from urllib.parse import urlsplit
    for header in ("Origin", "Referer"):
        value = request.headers.get(header) or ""
        if value:
            parts = urlsplit(value)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
    return ""


@xframe_options_exempt
@csrf_exempt  # opened from other websites and inside iframes; protected by a honeypot, origin check and rate limit
def careers_apply(request, slug):
    site = svc.receiving_site(slug)
    if site is None:
        raise Http404("This careers page is not available.")
    if request.method == "OPTIONS":
        return _cors(request, site, HttpResponse())
    origin = _origin(request)
    own_page = origin == f"{request.scheme}://{request.get_host()}"
    from_connected_site = origin in svc.origins(site)
    trusted = bool(request.headers.get("X-Api-Key")) and request.headers.get("X-Api-Key") == site.api_key
    if not site.enabled and not (from_connected_site or trusted):
        raise Http404("This careers page is not available.")
    job_value = request.POST.get("job") or request.GET.get("job")
    job = svc.match_job(site, job_value) if (from_connected_site or trusted) else (
        svc.public_job(site, job_value) if job_value else None)
    if job is None and (from_connected_site or trusted) and request.POST.get("trade"):
        job = svc.match_job(site, request.POST.get("trade"))
    wants_json = "application/json" in request.headers.get("Accept", "") or request.GET.get("format") == "json"
    if request.method != "POST":
        if not site.enabled:
            raise Http404
        return _public(request, "webapp/careers/apply.html", {**_base(site), "job": job, "post": {}, "no_float": True,
                                                              "embed": request.GET.get("embed") == "1"})
    if request.POST.get("company_website"):  # honeypot: people never see this field
        if wants_json:
            return _cors(request, site, JsonResponse({"ok": True}, status=201))
        return redirect(reverse("webapp:careers_thanks", args=[slug]))
    error = None
    if not trusted and _too_many(request, site):
        error = _("Too many applications from this connection. Please try again later or contact us on WhatsApp.")
    else:
        note = "" if own_page or not origin else origin.split("://", 1)[-1]
        try:
            candidate, placement, _new = svc.apply(site, request.POST, cv=request.FILES.get("cv"), job=job, source_note=note)
        except ValidationError as exc:
            error = " ".join(_(m) for m in exc.messages)
    if wants_json:
        body = {"ok": False, "error": error} if error else {"ok": True, "reference": candidate.number}
        return _cors(request, site, JsonResponse(body, status=400 if error else 201))
    if error:
        return _public(request, "webapp/careers/apply.html", {**_base(site), "job": job, "post": request.POST, "error": error,
                                                              "no_float": True, "embed": request.POST.get("embed") == "1"},
                       status=400)
    nxt = (request.POST.get("next") or "").strip()
    if nxt and any(nxt == o or nxt.startswith(o + "/") for o in svc.origins(site)):
        return redirect(f"{nxt}{'&' if '?' in nxt else '?'}applied=1")
    if not site.enabled and origin:
        return redirect(f"{origin}/?applied=1")
    url = reverse("webapp:careers_thanks", args=[slug]) + f"?ref={candidate.number}"
    if request.POST.get("embed") == "1":
        url += "&embed=1"
    return redirect(url)


def careers_connect_js(request, slug):
    """One-line connector for the agency's existing career page: it sends each submitted application here too."""
    site = svc.receiving_site(slug)
    if site is None:
        return HttpResponse("/* BookPilot: careers connector is not set up */", content_type="application/javascript")
    endpoint = request.build_absolute_uri(reverse("webapp:careers_apply", args=[slug])) + "?format=json"
    from django.template.loader import render_to_string
    body = render_to_string("webapp/careers/connect.js", {"endpoint": json.dumps(endpoint)})
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "public, max-age=300"
    response["Access-Control-Allow-Origin"] = "*"
    return response


@xframe_options_exempt
def careers_thanks(request, slug):
    site = _site_or_404(slug)
    return _public(request, "webapp/careers/thanks.html", {**_base(site), "ref": request.GET.get("ref", "")[:20],
                                                           "embed": request.GET.get("embed") == "1"})


def careers_jobs_json(request, slug):
    site = _site_or_404(slug)
    base = request.build_absolute_uri(reverse("webapp:careers_home", args=[slug]))
    jobs = [{"id": j.id, "position": j.position, "location": j.work_location, "vacancies": j.vacancies,
             "salary": f"{j.salary:.0f}" if j.salary else None, "currency": site.company.default_currency,
             "benefits": j.benefits, "nationality": j.nationality, "gender": j.gender,
             "summary": j.public_summary or j.requirements, "deadline": j.deadline.isoformat() if j.deadline else None,
             "posted": j.created_at.date().isoformat(),
             "url": request.build_absolute_uri(reverse("webapp:careers_job", args=[slug, j.id])),
             "apply_url": request.build_absolute_uri(reverse("webapp:careers_apply", args=[slug])) + f"?job={j.id}"}
            for j in svc.public_jobs(site)[:500]]
    response = JsonResponse({"agency": site.company.name, "careers_page": base, "jobs": jobs})
    response["Access-Control-Allow-Origin"] = "*"  # job listings are public
    return response


# ------------------------------------------------------------------ the agency's settings

class SiteForm(forms.ModelForm):
    slug = forms.CharField(max_length=80, label=_l("Web address name"))
    accent_color = forms.CharField(required=False, max_length=50, label=_l("Brand colour"),
                                   widget=forms.TextInput(attrs={"type": "color"}))

    class Meta:
        model = CareersSite
        fields = ["enabled", "slug", "headline", "about", "services", "countries", "whatsapp", "email", "address",
                  "licence", "accent_color", "ask_passport", "allowed_origins"]
        labels = {"enabled": _l("Website is live"), "slug": _l("Web address name"), "headline": _l("Headline"),
                  "about": _l("About your agency"), "services": _l("Services (one per line)"),
                  "countries": _l("Countries you recruit for"), "whatsapp": _l("WhatsApp number"), "email": _l("Email"),
                  "address": _l("Office address"), "licence": _l("Licence number"), "accent_color": _l("Brand colour"),
                  "ask_passport": _l("Ask for passport number"),
                  "allowed_origins": _l("Your own website address (optional, one per line)")}
        widgets = {"about": forms.Textarea(attrs={"rows": 4}), "services": forms.Textarea(attrs={"rows": 4}),
                   "allowed_origins": forms.Textarea(attrs={"rows": 2, "placeholder": "https://www.youragency.com"}),
                   "accent_color": forms.TextInput(attrs={"type": "color"})}

    def clean_slug(self):
        from django.utils.text import slugify
        slug = slugify(self.cleaned_data["slug"])[:60]
        if not slug:
            raise ValidationError(_("Enter a short name for the address, e.g. gulf-manpower."))
        if CareersSite.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("This name is taken. Try another one."))
        return slug

    def clean_accent_color(self):
        import re
        color = (self.cleaned_data.get("accent_color") or "").strip()
        return color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "#0f766e"

    def clean_allowed_origins(self):
        from urllib.parse import urlsplit
        lines = []
        for line in self.cleaned_data["allowed_origins"].replace(",", "\n").splitlines():
            line = line.strip()
            if not line:
                continue
            if "://" not in line:
                line = "https://" + line
            parts = urlsplit(line)
            if parts.scheme not in ("https", "http") or not parts.netloc or "." not in parts.netloc:
                raise ValidationError(_("Website addresses must start with https://"))
            for origin in {f"{parts.scheme}://{parts.netloc.lower()}"}:
                if origin not in lines:
                    lines.append(origin)
            host = parts.netloc.lower()
            twin = host[4:] if host.startswith("www.") else f"www.{host}" if host.count(".") == 1 else None
            if twin and f"{parts.scheme}://{twin}" not in lines:
                lines.append(f"{parts.scheme}://{twin}")
        return "\n".join(lines)


@recruitment_view
def rec_website(request):
    company = request.company
    site = svc.site_for(company)
    if request.method == "POST" and request.POST.get("action") == "jobs":
        chosen = set(request.POST.getlist("publish"))
        for job in JobOrder.objects.for_company(company).filter(status__in=["open", "on_hold"]):
            want = str(job.id) in chosen
            if job.publish_online != want:
                job.publish_online = want
                job.save(update_fields=["publish_online"])
        messages.success(request, _("Jobs on the website updated."))
        return redirect("webapp:rec_website")
    if request.method == "POST" and request.POST.get("action") == "connect":
        form = SiteForm({**{f: getattr(site, f) for f in SiteForm.Meta.fields}, "enabled": site.enabled,
                         "ask_passport": site.ask_passport, "allowed_origins": request.POST.get("allowed_origins", "")},
                        instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, _("Website connected. Applications from it will come here."))
        else:
            for error in form.errors.get("allowed_origins", []):
                messages.error(request, error)
        return redirect("webapp:rec_website")
    if request.method == "POST" and request.POST.get("action") == "new_key":
        import secrets
        site.api_key = secrets.token_urlsafe(30)[:40]
        site.save(update_fields=["api_key"])
        messages.success(request, _("New API key created. Update it on your own website."))
        return redirect("webapp:rec_website")
    form = SiteForm(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Website saved."))
        return redirect("webapp:rec_website")
    url = request.build_absolute_uri(reverse("webapp:careers_home", args=[site.slug]))
    apply_url = request.build_absolute_uri(reverse("webapp:careers_apply", args=[site.slug]))
    jobs_json = request.build_absolute_uri(reverse("webapp:careers_jobs_json", args=[site.slug]))
    connect_js = request.build_absolute_uri(reverse("webapp:careers_connect_js", args=[site.slug]))
    from apps.industry.models import Placement
    return render(request, "webapp/careers/settings.html", {
        "site": site, "form": form, "url": url, "connect_tag": f'<script src="{connect_js}" defer></script>',
        "connected": sorted(svc.origins(site)), "apply_url": apply_url, "jobs_json": jobs_json,
        "embed": f'<iframe src="{url}?embed=1" style="width:100%;min-height:900px;border:0" title="Careers"></iframe>',
        "form_snippet": _form_snippet(apply_url, site),
        "jobs": JobOrder.objects.for_company(company).filter(status__in=["open", "on_hold"]).select_related("client").order_by("-created_at"),
        "applications": Placement.objects.for_company(company).filter(stage="applied").count(),
        "share": f"https://wa.me/?text={_share_text(site, url)}",
    })


def _share_text(site, url):
    from urllib.parse import quote
    return quote(f"{site.headline or site.company.name}\n{url}")


def _form_snippet(apply_url, site):
    return (f'<form action="{apply_url}" method="post" enctype="multipart/form-data">\n'
            f'  <input type="hidden" name="next" value="https://www.your-website.com/careers">\n'
            f'  <input type="hidden" name="job" value="JOB_ID (optional)">\n'
            f'  <input name="name" required placeholder="Full name">\n'
            f'  <input name="phone" required placeholder="Phone / WhatsApp">\n'
            f'  <input name="email" type="email" placeholder="Email">\n'
            f'  <input name="passport_no" {"required " if site.ask_passport else ""}placeholder="Passport number">\n'
            f'  <input name="trade" placeholder="Position / skill">\n'
            f'  <input name="cv" type="file" accept=".pdf,.doc,.docx,image/*">\n'
            f'  <button>Apply</button>\n</form>')


def _msgids():
    return [_("Upload your CV as PDF, Word or a photo."), _("The CV file is too large (max 8 MB)."),
            _("Enter your full name and a phone / WhatsApp number."), _("Enter your passport number."),
            _("Applied online"), _("Office"), _("Website"), _("Referral"),
            _("Show this job on the careers website."), _("What job seekers see. The client's name is never shown."),
            _("Countries you recruit for, e.g. Qatar, UAE, Saudi Arabia."),
            _("Your own website addresses that may send applications, one per line."),
            _("Recruitment licence number, shown in the footer."), _("One per line.")]

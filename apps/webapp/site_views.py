"""Hosted business website: the public site, the owner's design area and the platform admin's domain / custom code."""
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.industry import site_builder as svc
from apps.industry import website_kit
from apps.industry.models import SiteDesign
from apps.tenants.models import Company

from .online_booking_views import owner_only
from .views import superuser_required

COLOR = re.compile(r"#[0-9a-fA-F]{6}")


# ------------------------------------------------------------------ public website

def _render_site(request, design, preview=False):
    ctx = svc.content(design, request.build_absolute_uri)
    ctx["preview"] = preview
    response = render(request, "webapp/site/page.html", ctx)
    response["Cache-Control"] = "no-store" if preview else "public, max-age=60"
    response["X-Frame-Options"] = "SAMEORIGIN"  # the design area shows it in a preview frame
    return response


def _can_preview(request, company):
    user = request.user
    if not user.is_authenticated:
        return False
    if getattr(user, "is_platform_admin", False):
        return True
    return company.memberships.filter(user=user, is_active=True).exists()


def site_public(request, public_id):
    kit = website_kit.by_public_id(public_id)
    if kit is None:
        raise Http404
    design = SiteDesign._base_manager.select_related("company", "company__business_type").filter(company=kit.company).first()
    preview = request.GET.get("preview") == "1" and _can_preview(request, kit.company)
    if design is None or not (preview or (design.enabled and design.published)):
        raise Http404("This website is not published.")
    return _render_site(request, design, preview)


def site_domain_home(request):
    """The site on the business's own domain (see CustomDomainMiddleware)."""
    design = getattr(request, "site_design", None)
    if design is None or not design.published:
        raise Http404("This website is not published yet.")
    return _render_site(request, design)


# ------------------------------------------------------------------ design area

class DesignForm(forms.ModelForm):
    primary_color = forms.CharField(max_length=7, label=_l("Main colour"), widget=forms.TextInput(attrs={"type": "color"}))
    accent_color = forms.CharField(max_length=7, label=_l("Highlight colour"), widget=forms.TextInput(attrs={"type": "color"}))

    class Meta:
        model = SiteDesign
        fields = ["published", "theme", "font", "primary_color", "accent_color", "logo", "hero_image", "hero_title",
                  "hero_subtitle", "about", "opening_hours", "whatsapp", "instagram", "facebook", "tiktok", "map_url",
                  "show_catalogue", "show_offers", "show_booking", "show_careers", "show_contact"]
        labels = {"published": _l("Website is live"), "theme": _l("Design"), "font": _l("Font"), "logo": _l("Logo"),
                  "hero_image": _l("Cover photo"), "hero_title": _l("Big title"), "hero_subtitle": _l("Line under the title"),
                  "about": _l("About us"), "opening_hours": _l("Opening hours"), "whatsapp": _l("WhatsApp number"),
                  "map_url": _l("Google Maps link"), "show_catalogue": _l("Show menu / services / products"),
                  "show_offers": _l("Show offers"), "show_booking": _l("Show booking form"),
                  "show_careers": _l("Show jobs"), "show_contact": _l("Show contact form")}
        help_texts = {"logo": _l("Leave empty to use the company logo."),
                      "opening_hours": _l("One line each, e.g. Sat–Thu 10am–11pm")}
        widgets = {"about": forms.Textarea(attrs={"rows": 4}), "opening_hours": forms.Textarea(attrs={"rows": 3})}

    def _color(self, name, default):
        value = (self.cleaned_data.get(name) or "").strip()
        return value if COLOR.fullmatch(value) else default

    def clean_primary_color(self):
        return self._color("primary_color", "#0f766e")

    def clean_accent_color(self):
        return self._color("accent_color", "#f59e0b")


class AdminSiteForm(forms.ModelForm):
    """Only the platform admin: switch the add-on on, own domain and custom code."""
    custom_domain = forms.CharField(required=False, max_length=253, label="Own domain",
                                    widget=forms.TextInput(attrs={"placeholder": "www.client.com"}))

    class Meta:
        model = SiteDesign
        fields = ["enabled", "custom_domain", "domain_status", "custom_css", "custom_html"]
        labels = {"enabled": "Website add-on is on for this client", "domain_status": "Domain status",
                  "custom_css": "Custom CSS", "custom_html": "Custom HTML section"}
        widgets = {"custom_css": forms.Textarea(attrs={"rows": 6, "style": "font-family:monospace"}),
                   "custom_html": forms.Textarea(attrs={"rows": 6, "style": "font-family:monospace"})}

    def clean_custom_domain(self):
        host = svc.normalise_domain(self.cleaned_data.get("custom_domain"))
        if not host:
            return None
        twins = svc.domain_twins(host)
        if SiteDesign._base_manager.filter(custom_domain__in=twins).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This domain is already used by another client.")
        return host

    def clean(self):
        data = super().clean()
        if not data.get("custom_domain"):
            data["domain_status"] = ""
        elif not data.get("domain_status"):
            data["domain_status"] = "pending"
        return data


def _editor(request, company, admin):
    design = svc.design_for(company)
    kit = website_kit.kit_for(company)
    action = request.POST.get("action") if request.method == "POST" else None
    form = DesignForm(request.POST if action == "design" else None, request.FILES if action == "design" else None,
                      instance=design, prefix="d")
    aform = AdminSiteForm(request.POST if action == "admin" else None, instance=design, prefix="a") if admin else None
    target = {"design": form, "admin": aform}.get(action)
    if target is not None and (action != "design" or design.enabled or admin) and target.is_valid():
        saved = target.save()
        if action == "admin":
            svc.forget_domains()
            if saved.custom_domain:  # forms on the client's domain post back here
                origins = website_kit.origins(kit) | {f"https://{h}" for h in svc.domain_twins(saved.custom_domain)}
                kit.allowed_origins = "\n".join(sorted(origins))
                kit.save(update_fields=["allowed_origins"])
        messages.success(request, _("Website saved."))
        return redirect(request.path)
    public = request.build_absolute_uri(reverse("webapp:site_public", args=[kit.public_id]))
    links = []
    caps = website_kit.capabilities(company)
    if company.business_type.code in ("restaurant", "cafe_juice_shop", "catering_company"):
        links.append((_("Menu"), reverse("webapp:restaurant_setup")))
    elif caps["catalogue"] == "products":
        links.append((_("Products"), reverse("webapp:product_list")))
    links.append((_("Offers"), reverse("webapp:pricing")))
    links.append((_("Phone, address & logo"), reverse("webapp:company_settings")))
    ctx = {"company": company, "design": design, "form": form, "aform": aform, "admin": admin, "kit": kit,
           "public": public, "preview": f"{public}?preview=1", "links": links,
           "own": f"https://{design.custom_domain}" if design.custom_domain else "",
           "base_template": "webapp/admin_base.html" if admin else "base.html",
           "host": request.get_host().split(":")[0]}
    return render(request, "webapp/site/editor.html", ctx)


@login_required
@owner_only
def site_editor(request):
    if request.company is None:
        return render(request, "webapp/no_company.html")
    return _editor(request, request.company, admin=False)


@login_required
@superuser_required
def site_admin_editor(request, company_id):
    return _editor(request, get_object_or_404(Company, id=company_id), admin=True)

"""Hosted business website: the public site, the owner's design area and the platform admin's domain / custom code."""
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.industry import site_builder as svc
from apps.industry import website_kit
from apps.industry.models import SiteDesign, SitePage
from apps.tenants.models import Company

from .online_booking_views import owner_only
from .views import superuser_required

COLOR = re.compile(r"#[0-9a-fA-F]{6}")


# ------------------------------------------------------------------ public website

PAGE_CACHE_SECONDS = 60


def _page_cache_key(request, design):
    import hashlib
    raw = f"{design.company_id}|{design.updated_at.timestamp() if design.updated_at else 0}|{request.get_host()}|{request.get_full_path()}"
    return "site-page:" + hashlib.sha256(raw.encode()).hexdigest()


def _render_site(request, design, preview=False, base=None, kind="home", **extra):
    """Public website pages are the same for every visitor, so each is built once a minute at most
    (saving the owner's design clears it at once); the owner's preview is never cached."""
    from django.core.cache import cache
    from django.http import HttpResponse
    key = None if preview or request.method != "GET" else _page_cache_key(request, design)
    if key:
        hit = cache.get(key)
        if hit is not None:
            response = HttpResponse(hit)
            response["Cache-Control"] = f"public, max-age={PAGE_CACHE_SECONDS}"
            response["X-Frame-Options"] = "SAMEORIGIN"
            return response
    response = _build_site(request, design, preview, base, kind, **extra)
    if key and response.status_code == 200:
        cache.set(key, response.content, PAGE_CACHE_SECONDS)
    return response


def _build_site(request, design, preview=False, base=None, kind="home", **extra):
    from django.utils import translation
    lang = svc.pick_language(design, request.GET.get("lang"))
    base = base or "/"
    with translation.override(lang):
        ctx = svc.content(design, request.build_absolute_uri)
        ctx.update(preview=preview, lang=lang, lang_bidi=translation.get_language_bidi(),
                   switch=svc.language_links(design, lang, preview), page_kind=kind,
                   has_catalogue=bool(ctx["groups"]), **svc.layout(design, base, lang, preview))
        template = "webapp/site/page.html"
        if kind == "home" and ctx["shop_url"]:  # a shop's home shows a few products; the Shop page has them all
            items = [i for g in ctx["groups"] for i in g["items"]]
            items.sort(key=lambda i: not i.get("available", True))
            for i in items:
                i["url"] = f"{base}shop/{i['id']}/{ctx['q']}"
            ctx["groups"] = [{"name": "", "items": items[:8]}] if items else []
        elif kind == "shop":
            ctx.update(svc.shop_page(design, request.build_absolute_uri, base, lang, preview, **extra))
            template = "webapp/site/shop.html"
        elif kind == "product":
            data = svc.product_page(design, request.build_absolute_uri, base, lang, preview, extra["product_id"])
            if data is None:
                raise Http404
            ctx.update(data)
            ctx["wa_text"] = f"{data['item']['name']} — {ctx['currency']} {data['item']['price']}\n{request.build_absolute_uri()}"
            ctx["page_url"] = request.build_absolute_uri(request.path)
            ctx["review_url"] = f"{base}shop/{extra['product_id']}/review/" + ctx["q"]
            ctx["reviewed"] = request.GET.get("reviewed") == "1"
            template = "webapp/site/product.html"
        elif kind == "page":
            page = next((p for p in ctx["menu_pages"] + ctx["footer_pages"] if p.slug == extra["slug"]), None)
            if page is None:
                raise Http404
            from apps.industry.site_html import clean_html
            ctx.update(current_page=page, body=clean_html(page.body))
            template = "webapp/site/custom_page.html"
        if design.custom_header or design.custom_footer or design.custom_home or design.custom_head:
            _custom_design(request, design, ctx)
        response = render(request, template, ctx)
    response["Cache-Control"] = "no-store" if preview else "public, max-age=60"
    response["X-Frame-Options"] = "SAMEORIGIN"  # the design area shows it in a preview frame
    return response


# [[name]] placeholders the platform admin can put in a custom header, footer or home page (Bootstrap / own HTML).
PLACEHOLDER_BLOCKS = ("products", "categories", "menu", "menu_items", "offers", "contact", "booking", "search", "hours",
                      "lang_switch")


PLACEHOLDERS_LIST = ("company_name", "logo", "logo_url", "home_url", "shop_url", "menu", "menu_items", "search", "cart_button",
                     "lang_switch", "hero_title", "hero_subtitle", "hero_image", "products", "categories", "offers", "about",
                     "hours", "contact", "booking", "phone", "email", "address", "whatsapp_url", "currency", "year")

BOOTSTRAP_STARTER = {
    "custom_head": '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">\n'
                   '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>\n'
                   '<style>.hero-bp{background:linear-gradient(135deg,var(--p),#0b1220);color:#fff}</style>',
    "custom_header": '<nav class="navbar navbar-expand-lg bg-white border-bottom sticky-top">\n'
                     '  <div class="container">\n'
                     '    <a class="navbar-brand fw-bold d-flex align-items-center gap-2" href="[[home_url]]">[[logo]] [[company_name]]</a>\n'
                     '    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#bpNav"><span class="navbar-toggler-icon"></span></button>\n'
                     '    <div class="collapse navbar-collapse" id="bpNav">\n'
                     '      <ul class="navbar-nav ms-auto">[[menu_items]]</ul>\n'
                     '      <div class="ms-lg-3 my-2 my-lg-0">[[search]]</div>\n'
                     '    </div>\n  </div>\n</nav>',
    "custom_home": '<section class="hero-bp py-5">\n  <div class="container py-5">\n'
                   '    <h1 class="display-5 fw-bold">[[hero_title]]</h1>\n    <p class="lead opacity-75">[[hero_subtitle]]</p>\n'
                   '    <a class="btn btn-light btn-lg" href="[[shop_url]]">Shop now</a>\n  </div>\n</section>\n'
                   '<main class="container py-5">\n  [[categories]]\n  <h2 class="my-4">Popular products</h2>\n  [[products]]\n'
                   '  [[offers]]\n'
                   '  <div class="row g-4 mt-4">\n    <div class="col-md-6"><h2>About us</h2><p>[[about]]</p>[[hours]]</div>\n'
                   '    <div class="col-md-6"><h2>Contact us</h2>[[contact]]</div>\n  </div>\n</main>',
    "custom_footer": '<footer class="bg-dark text-light py-5 mt-5">\n  <div class="container d-flex flex-wrap justify-content-between gap-3">\n'
                     '    <div><b>[[company_name]]</b><div class="small opacity-75">[[address]]</div></div>\n'
                     '    <div class="small">📞 [[phone]]<br>✉️ [[email]]</div>\n  </div>\n'
                     '  <div class="container small opacity-50 mt-3">© [[year]] [[company_name]]</div>\n</footer>',
}


def _custom_design(request, design, ctx):
    """Fills the admin's custom HTML with live BookPilot parts: [[products]], [[menu_items]], [[contact]]…"""
    import re
    from django.template.loader import render_to_string
    from django.utils.html import escape
    company = design.company
    if ctx.get("shop_url"):
        from apps.inventory.models import ProductCategory
        from apps.industry import shop_orders
        cats = ProductCategory.objects.filter(company=company, id__in=shop_orders.sellable(company).values("category_id")).order_by("name")
        ctx["nav_categories"] = [{"name": c.name, "url": f"{ctx['base']}shop/" + svc.query(ctx["lang"], design, ctx["preview"], cat=c.id)} for c in cats]
    simple = {
        "company_name": escape(company.name), "phone": escape(company.phone or ""), "email": escape(company.email or ""),
        "address": escape(company.address or ""), "home_url": escape(ctx["home"]), "shop_url": escape(ctx.get("shop_url") or ctx["home"]),
        "logo_url": escape(ctx.get("logo") or ""), "logo": f'<img src="{escape(ctx["logo"])}" alt="{escape(company.name)}" style="max-height:44px">' if ctx.get("logo") else "",
        "whatsapp_url": f"https://wa.me/{ctx['whatsapp']}" if ctx.get("whatsapp") else "", "year": str(ctx.get("year") or ""),
        "about": escape(design.about or "").replace("\n", "<br>"), "hero_title": escape(design.hero_title or company.name),
        "hero_subtitle": escape(design.hero_subtitle or ""), "hero_image": escape(ctx.get("hero") or ""),
        "currency": escape(company.default_currency),
        "cart_button": '<button type="button" class="btn btn-outline-dark" onclick="var b=document.querySelector(\'.bpo-bar\');b&&b.click()">🛒</button>',
    }
    cache = {}

    def fill(text):
        def sub(m):
            key = m.group(1).strip().lower()
            if key in simple:
                return simple[key]
            if key in PLACEHOLDER_BLOCKS:
                if key not in cache:
                    cache[key] = render_to_string(f"webapp/site/blocks/{key}.html", ctx, request=request)
                return cache[key]
            return m.group(0)
        return re.sub(r"\[\[\s*([a-zA-Z_]+)\s*\]\]", sub, text or "")
    ctx.update(custom_head_html=fill(design.custom_head), custom_header_html=fill(design.custom_header),
               custom_footer_html=fill(design.custom_footer), custom_home_html=fill(design.custom_home))


def _can_preview(request, company):
    user = request.user
    if not user.is_authenticated:
        return False
    if getattr(user, "is_platform_admin", False):
        return True
    return company.memberships.filter(user=user, is_active=True).exists()


def _shop_args(request):
    return {"params": request.GET}


def _public(request, public_id, kind="home", **extra):
    kit = website_kit.by_public_id(public_id)
    if kit is None:
        raise Http404
    design = SiteDesign._base_manager.select_related("company", "company__business_type").filter(company=kit.company).first()
    preview = request.GET.get("preview") == "1" and _can_preview(request, kit.company)
    if design is None or not (preview or (design.enabled and design.published)):
        raise Http404("This website is not published.")
    if kind == "shop":
        extra = _shop_args(request)
    return _render_site(request, design, preview, base=f"/site/{public_id}/", kind=kind, **extra)


def site_public(request, public_id):
    return _public(request, public_id)


def site_public_shop(request, public_id):
    return _public(request, public_id, "shop")


def site_public_product(request, public_id, product_id):
    return _public(request, public_id, "product", product_id=product_id)


def site_public_page(request, public_id, slug):
    return _public(request, public_id, "page", slug=slug)


def _domain(request, kind="home", **extra):
    """The site on the business's own domain (see CustomDomainMiddleware)."""
    design = getattr(request, "site_design", None)
    if design is None or not design.published:
        raise Http404("This website is not published yet.")
    if kind == "shop":
        extra = _shop_args(request)
    return _render_site(request, design, base="/", kind=kind, **extra)


def site_domain_home(request):
    return _domain(request)


def site_domain_shop(request):
    return _domain(request, "shop")


def site_domain_product(request, product_id):
    return _domain(request, "product", product_id=product_id)


def site_domain_page(request, slug):
    return _domain(request, "page", slug=slug)


def _review(request, design, base, product_id):
    """A visitor's review from the product page; it waits for the shop to approve it."""
    from django.core.cache import cache
    from django.http import HttpResponseRedirect
    from apps.industry import shop_orders
    from apps.industry.models import ProductReview
    if request.method != "POST" or not design.shop_reviews:
        raise Http404
    product = shop_orders.sellable(design.company).filter(id=product_id).first()
    if product is None:
        raise Http404
    q = request.META.get("QUERY_STRING", "")
    back = f"{base}shop/{product_id}/" + (f"?{q}&" if q else "?") + "reviewed=1#reviews"
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "?"
    key = f"site-review:{design.company_id}:{ip}"
    count = cache.get(key, 0)
    name = (request.POST.get("name") or "").strip()[:80]
    if request.POST.get("company_website") or count >= 5 or len(name) < 2:  # bots and floods get the same thank-you
        return HttpResponseRedirect(back)
    cache.set(key, count + 1, 3600)
    try:
        rating = min(5, max(1, int(request.POST.get("rating") or 5)))
    except ValueError:
        rating = 5
    ProductReview.objects.create(company=design.company, product=product, name=name, rating=rating,
                                 text=(request.POST.get("text") or "").strip()[:2000])
    return HttpResponseRedirect(back)


@csrf_exempt
def site_public_review(request, public_id, product_id):
    kit = website_kit.by_public_id(public_id)
    design = SiteDesign._base_manager.filter(company=kit.company).first() if kit else None
    if design is None or not (design.enabled and design.published):
        raise Http404
    return _review(request, design, f"/site/{public_id}/", product_id)


@csrf_exempt
def site_domain_review(request, product_id):
    design = getattr(request, "site_design", None)
    if design is None or not design.published:
        raise Http404
    return _review(request, design, "/", product_id)


def site_domain_sitemap(request):
    from django.http import HttpResponse
    from apps.industry import shop_orders
    design = getattr(request, "site_design", None)
    if design is None or not design.published:
        raise Http404
    root = request.build_absolute_uri("/")
    urls = [root]
    if svc.is_shop(design.company):
        urls.append(root + "shop/")
        urls += [f"{root}shop/{pid}/" for pid in shop_orders.sellable(design.company).values_list("id", flat=True)[:2000]]
    urls += [f"{root}p/{p.slug}/" for p in svc.pages_for(design.company, "/", "")]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + \
        "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    return HttpResponse(body, content_type="application/xml")


def site_domain_robots(request):
    from django.http import HttpResponse
    return HttpResponse(f"User-agent: *\nAllow: /\nSitemap: {request.build_absolute_uri('/sitemap.xml')}\n", content_type="text/plain")


# ------------------------------------------------------------------ design area

class DesignForm(forms.ModelForm):
    primary_color = forms.CharField(max_length=7, label=_l("Main colour"), widget=forms.TextInput(attrs={"type": "color"}))
    accent_color = forms.CharField(max_length=7, label=_l("Highlight colour"), widget=forms.TextInput(attrs={"type": "color"}))

    class Meta:
        model = SiteDesign
        fields = ["published", "language", "extra_languages", "theme", "font", "primary_color", "accent_color", "logo",
                  "hero_image", "hero_title", "hero_subtitle", "about", "opening_hours", "whatsapp", "instagram", "facebook",
                  "tiktok", "map_url", "show_catalogue", "show_offers", "show_booking", "show_careers", "show_contact", "custom_css"]
        labels = {"language": _l("Website language"), "published": _l("Website is live"), "theme": _l("Design"), "font": _l("Font"), "logo": _l("Logo"),
                  "hero_image": _l("Cover photo"), "hero_title": _l("Big title"), "hero_subtitle": _l("Line under the title"),
                  "about": _l("About us"), "opening_hours": _l("Opening hours"), "whatsapp": _l("WhatsApp number"),
                  "map_url": _l("Google Maps link"), "show_catalogue": _l("Show menu / services / products"),
                  "show_offers": _l("Show offers"), "show_booking": _l("Show booking form"),
                  "show_careers": _l("Show jobs"), "show_contact": _l("Show contact form"), "custom_css": _l("My own CSS")}
        help_texts = {"logo": _l("Leave empty to use the company logo."),
                      "opening_hours": _l("One line each, e.g. Sat–Thu 10am–11pm")}
        widgets = {"about": forms.Textarea(attrs={"rows": 4}), "opening_hours": forms.Textarea(attrs={"rows": 3}),
                   "custom_css": forms.Textarea(attrs={"rows": 8, "spellcheck": "false", "style": "font-family:monospace",
                                                       "placeholder": ".hero{background:#111}\n.card{border-radius:4px}\n.btn{background:#e11d48}"})}

    extra_languages = forms.MultipleChoiceField(required=False, label=_l("Visitors can also switch to"),
                                                widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(svc.site_languages())
        self.fields["language"] = forms.ChoiceField(choices=choices, label=_l("Website language"), required=False)
        self.fields["extra_languages"].choices = choices
        self.initial["extra_languages"] = svc.extra_languages(self.instance)

    def clean_language(self):
        return self.cleaned_data.get("language") or self.instance.language or "en"

    def clean_extra_languages(self):
        main = self.cleaned_data.get("language")
        return ",".join(code for code in self.cleaned_data["extra_languages"] if code != main)

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
        fields = ["enabled", "package", "custom_domain", "domain_status", "custom_html", "custom_head", "custom_header",
                  "custom_footer", "custom_home"]
        labels = {"enabled": "Website add-on is on for this client", "domain_status": "Domain status",
                  "package": "Package (billed yearly: Website QAR 399 · E-commerce QAR 699)",
                  "custom_head": "Custom <head> code", "custom_header": "Custom header", "custom_footer": "Custom footer",
                  "custom_home": "Custom home page",
                  "custom_html": "Custom HTML section"}
        widgets = {k: forms.Textarea(attrs={"rows": 8, "style": "font-family:monospace", "spellcheck": "false"})
                   for k in ("custom_html", "custom_head", "custom_header", "custom_footer", "custom_home")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].required = False

    def clean_package(self):
        return self.cleaned_data.get("package") or self.instance.package or "website"

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
    if action in ("page_save", "page_delete") and not admin:
        return _page_action(request, company, action)
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
           "host": request.get_host().split(":")[0], "pages": SitePage.objects.filter(company=company),
           "is_shop": svc.is_shop(company), "page_form": SitePageForm(prefix="pg") if not admin else None,
           "placeholders": PLACEHOLDERS_LIST, "starter": BOOTSTRAP_STARTER if admin else None}
    return render(request, "webapp/site/editor.html", ctx)


class SitePageForm(forms.ModelForm):
    slug = forms.CharField(required=False, max_length=80)

    class Meta:
        model = SitePage
        fields = ["title", "slug", "body", "show_in_menu", "published", "sort_order"]
        labels = {"title": _l("Page title"), "slug": _l("Web address"), "body": _l("Page text"),
                  "show_in_menu": _l("Show in the top menu (off: footer only)"), "published": _l("Page is live"),
                  "sort_order": _l("Order")}
        help_texts = {"slug": _l("e.g. warranty → yoursite.com/p/warranty/"),
                      "body": _l("Plain text, or HTML (headings, lists, pictures, tables, YouTube / Google Maps embeds). Scripts are removed.")}
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["sort_order"].required = False
        self.fields["slug"].label = _l("Web address")
        self.fields["slug"].help_text = _l("e.g. warranty → yoursite.com/p/warranty/")

    def clean_sort_order(self):
        return self.cleaned_data.get("sort_order") or 0

    def clean_slug(self):
        from django.utils.text import slugify
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("title") or "")[:80] or "page"
        if self.company and SitePage.objects.filter(company=self.company, slug=slug).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("Another page already uses this address."))
        return slug


def _page_action(request, company, action):
    page = None
    if request.POST.get("page_id"):
        page = get_object_or_404(SitePage.objects.filter(company=company), id=request.POST["page_id"])
    if action == "page_delete" and page:
        page.delete()
        messages.success(request, _("Page deleted."))
        return redirect(request.path + "#pages")
    form = SitePageForm(request.POST, instance=page, prefix="pg", company=company)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.company = company
        obj.save()
        messages.success(request, _("Page saved."))
    else:
        messages.error(request, " ".join(str(e) for errs in form.errors.values() for e in errs))
    return redirect(request.path + "#pages")


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

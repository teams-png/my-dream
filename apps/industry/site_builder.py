"""
Hosted business website: a ready-made site per business, served at /site/<public id>/ or on the business's own
domain. Menu / services / rooms / courses / jobs, offers, phone and address are read live from BookPilot, so a
change in POS or settings shows on the website straight away.
"""
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _l

from .models import SiteDesign
from . import website_kit

DOMAIN_CACHE_KEY = "site-builder:domains"


def design_for(company):
    design = SiteDesign.objects.filter(company=company).first()
    if design is None:
        design = SiteDesign.objects.create(company=company, hero_title=company.name[:150], whatsapp=company.phone or "")
    return design


# ------------------------------------------------------------------ own domains

def normalise_domain(value):
    from urllib.parse import urlsplit
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    host = (urlsplit(value).hostname or "").strip(".")
    if "." not in host or len(host) > 253 or not all(part and len(part) < 64 for part in host.split(".")):
        raise ValidationError("Enter a domain like www.client.com")
    return host


def domain_twins(host):
    if host.startswith("www."):
        return [host, host[4:]]
    return [host, f"www.{host}"] if host.count(".") == 1 else [host]


def domain_map():
    """{host: company_id} for every live own domain (www and bare both point to the site)."""
    data = cache.get(DOMAIN_CACHE_KEY)
    if data is None:
        data = {}
        for company_id, domain in SiteDesign._base_manager.filter(
                enabled=True, domain_status="live", company__is_active=True).exclude(custom_domain=None).values_list(
                "company_id", "custom_domain"):
            for host in domain_twins(domain):
                data[host] = company_id
        cache.set(DOMAIN_CACHE_KEY, data, 300)
    return data


def forget_domains():
    cache.delete(DOMAIN_CACHE_KEY)


def design_for_host(host):
    company_id = domain_map().get((host or "").split(":")[0].lower())
    if not company_id:
        return None
    return SiteDesign._base_manager.select_related("company", "company__business_type").filter(
        company_id=company_id, enabled=True).first()


# ------------------------------------------------------------------ live content

def offers(company):
    from apps.sales.models import Promotion
    today = timezone.localdate()
    out = []
    for p in Promotion.objects.for_company(company).filter(is_active=True, start_date__lte=today,
                                                            end_date__gte=today).select_related("product")[:12]:
        value = f"{p.discount_value:.0f}%" if p.discount_type == "percentage" else f"{company.default_currency} {p.discount_value:.0f}"
        out.append({"name": p.name, "discount": value, "product": p.product.name if p.product else "",
                    "until": p.end_date})
    return out


def _digits(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())


def socials(design):
    out = []
    for name, base in (("Instagram", "https://instagram.com/"), ("Facebook", "https://facebook.com/"),
                       ("TikTok", "https://tiktok.com/@")):
        value = (getattr(design, name.lower()) or "").strip()
        if value:
            url = value if value.startswith(("http://", "https://")) else base + value.lstrip("@")
            out.append((name, url))
    return out


SECTION_TITLES = {"products": _l("Our menu"), "services": _l("Our services"), "resources": _l("Rooms & spaces"),
                  "courses": _l("Courses"), "jobs": _l("Open jobs")}


# rate units shown as "/ night" etc. on the website (translated in the template)
UNIT_WORDS = (_l("hour"), _l("day"), _l("night"), _l("week"), _l("month"), _l("monthly"), _l("session"), _l("term"))


# ------------------------------------------------------------------ languages

def site_languages():
    from django.conf import settings
    return settings.LANGUAGES


def extra_languages(design):
    codes = dict(site_languages())
    return [c for c in (x.strip() for x in (design.extra_languages or "").split(",")) if c in codes and c != design.language]


def pick_language(design, wanted=None):
    codes = dict(site_languages())
    allowed = {design.language} | set(extra_languages(design))
    if wanted in allowed and wanted in codes:
        return wanted
    return design.language if design.language in codes else "en"


def language_links(design, current, preview=False):
    """[(code, native name, url query, is current)] for the visitor's language switcher; empty with one language."""
    names = dict(site_languages())
    codes = [design.language] + extra_languages(design)
    if len(codes) < 2:
        return []
    extra = "&preview=1" if preview else ""
    return [(c, names[c], f"?lang={c}{extra}", c == current) for c in codes if c in names]


def grouped(items):
    groups = {}
    for item in items:
        groups.setdefault(item.get("category") or "", []).append(item)
    return [{"name": name, "items": rows} for name, rows in groups.items()]


def content(design, absolute):
    company = design.company
    caps = website_kit.capabilities(company)
    kit = website_kit.kit_for(company)
    data = website_kit.info(company, absolute)
    catalogue = website_kit.catalogue(company, absolute, limit=300) if design.show_catalogue else {"items": []}
    kind = caps["catalogue"]
    title = SECTION_TITLES.get(kind, _l("Our products"))
    if kind == "products" and company.business_type.code not in ("restaurant", "cafe_juice_shop", "catering_company", "bakery"):
        title = _l("Our products")
    ctx = {"design": design, "company": company, "info": data, "kit": kit, "caps": caps,
           "logo": absolute(design.logo.url) if design.logo else data["logo"],
           "hero": absolute(design.hero_image.url) if design.hero_image else None,
           "catalogue_title": title, "catalogue_kind": kind, "groups": grouped(catalogue["items"]),
           "ordering": catalogue.get("ordering", {}).get("enabled", False),
           "currency": company.default_currency, "offers": offers(company) if design.show_offers else [],
           "hours": [line.strip() for line in design.opening_hours.splitlines() if line.strip()],
           "socials": socials(design), "whatsapp": _digits(design.whatsapp or company.phone),
           "phone_link": _digits(company.phone), "booking_slug": None, "careers_slug": None, "year": timezone.localdate().year}
    if design.show_booking and caps["booking"]:
        from .online_booking import site_for
        site = site_for(company)
        if site.enabled:
            ctx["booking_slug"] = site.slug
    if design.show_careers and caps["careers"]:
        from .careers import site_for
        ctx["careers_slug"] = site_for(company).slug
    return ctx


# ------------------------------------------------------------------ shop pages (many-page website)

PAGE_SIZE = 24
HIDDEN_ATTRS = {"sold_by_weight", "sold_by_ml", "scale_code", "item_type", "wholesale_price", "carton_quantity",
                "web_description", "serial_required", "making_mode", "making_charge", "stone_value"}


def query(lang, design, preview, **params):
    """'?lang=ar&preview=1&cat=3' — keeps the visitor's language and the owner's preview on every link."""
    from urllib.parse import urlencode
    parts = {}
    if lang and lang != design.language:
        parts["lang"] = lang
    if preview:
        parts["preview"] = "1"
    parts.update({k: v for k, v in params.items() if v not in (None, "", 1) or k != "page"})
    parts = {k: v for k, v in parts.items() if v not in (None, "")}
    return ("?" + urlencode(parts)) if parts else ""


def is_shop(company):
    from . import shop_orders
    return shop_orders.applies(company)


def pages_for(company, base, q):
    from .models import SitePage
    out = []
    for p in SitePage.objects.filter(company=company, published=True):
        p.url = f"{base}p/{p.slug}/{q}"
        out.append(p)
    return out


def layout(design, base, lang, preview):
    """Links and pieces every page of the website shares (header menu, footer, the owner's CSS)."""
    from .site_html import clean_css
    q = query(lang, design, preview)
    pages = pages_for(design.company, base, q)
    shop = is_shop(design.company) and design.show_catalogue
    return {"base": base, "q": q, "home": base + q, "lang_q": lang if lang != design.language else "",
            "shop_url": f"{base}shop/{q}" if shop else "", "menu_pages": [p for p in pages if p.show_in_menu],
            "footer_pages": [p for p in pages if not p.show_in_menu], "custom_css": clean_css(design.custom_css)}


def _item(p, company, absolute, base, q, stock, ordering):
    from apps.inventory.pictures import picture_url
    in_stock = not p.is_stock_tracked or stock.get(p.id, 0) > 0
    return {"id": p.id, "name": f"{p.name} — {p.variant_label}" if p.variant_label else p.name,
            "category": p.category.name if p.category_id else "", "category_id": p.category_id,
            "price": f"{p.selling_price:.2f}", "image": absolute(picture_url(p, company.business_type.code)),
            "available": in_stock, "orderable": bool(ordering and ordering.get("open") and in_stock),
            "tracked": p.is_stock_tracked, "stock": int(stock.get(p.id, 0)), "url": f"{base}shop/{p.id}/{q}",
            "brand": p.brand.name if p.brand_id else "", "description": (p.attributes or {}).get("web_description", "")}


def shop_page(design, absolute, base, lang, preview, category_id=None, search="", sort="", page=1):
    from apps.inventory.models import ProductCategory
    from . import shop_orders
    company = design.company
    ordering = shop_orders.config(company)
    qs = shop_orders.sellable(company).select_related("category", "brand")
    cats = list(ProductCategory.objects.filter(company=company, id__in=qs.values("category_id")).order_by("name"))
    category = next((c for c in cats if c.id == category_id), None)
    if category:
        qs = qs.filter(category=category)
    search = (search or "").strip()[:80]
    if search:
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=search) | Q(brand__name__icontains=search) | Q(sku__iexact=search) |
                       Q(category__name__icontains=search))
    qs = qs.order_by({"low": "selling_price", "high": "-selling_price", "new": "-id"}.get(sort, "name"), "id")
    total = qs.count()
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    rows = list(qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE])
    q = query(lang, design, preview)
    stock = shop_orders.stock_for(company, rows)
    items = [_item(p, company, absolute, base, q, stock, ordering) for p in rows]
    for c in cats:
        c.url = f"{base}shop/" + query(lang, design, preview, cat=c.id)
    more = dict(cat=category.id if category else None, q=search, sort=sort)
    return {"items": items, "categories": cats, "category": category, "search": search, "sort": sort, "total": total,
            "page": page, "pages": pages, "ordering": ordering,
            "prev_url": f"{base}shop/" + query(lang, design, preview, page=page - 1, **more) if page > 1 else "",
            "next_url": f"{base}shop/" + query(lang, design, preview, page=page + 1, **more) if page < pages else ""}


def product_page(design, absolute, base, lang, preview, product_id):
    """None when the product is not sold on the website."""
    from apps.webapp.forms import BusinessProductForm
    from . import shop_orders
    company = design.company
    p = shop_orders.sellable(company).select_related("category", "brand", "parent").filter(id=product_id).first()
    if p is None:
        return None
    ordering = shop_orders.config(company)
    q = query(lang, design, preview)
    siblings = list(shop_orders.sellable(company).filter(parent_id=p.parent_id).order_by("id")) if p.parent_id else [p]
    related = list(shop_orders.sellable(company).filter(category_id=p.category_id).exclude(id__in=[s.id for s in siblings])
                   .select_related("category", "brand").order_by("?")[:4]) if p.category_id else []
    stock = shop_orders.stock_for(company, siblings + related)
    item = _item(p, company, absolute, base, q, stock, ordering)
    if p.category_id:
        item["category_url"] = f"{base}shop/" + query(lang, design, preview, cat=p.category_id)
    labels = BusinessProductForm.FIELD_LABELS
    specs = []
    for field, label in (("size", _l("Size")), ("colour", _l("Colour")), ("material", _l("Material"))):
        if getattr(p, field):
            specs.append((label, getattr(p, field)))
    for key, value in (p.attributes or {}).items():
        if key in HIDDEN_ATTRS or value in ("", None, False) or isinstance(value, (dict, list)):
            continue
        value = _l("Yes") if value is True else value
        specs.append((labels.get(key) or key.replace("_", " ").capitalize(), value))
    options = [{"id": s.id, "label": s.variant_label or s.name, "url": f"{base}shop/{s.id}/{q}"} for s in siblings]
    return {"item": item, "specs": specs, "options": options, "ordering": ordering,
            "related": [_item(r, company, absolute, base, q, stock, ordering) for r in related]}

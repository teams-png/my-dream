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
    parts = {k: v for k, v in parts.items() if v not in (None, "", [], ())}
    return ("?" + urlencode(parts, doseq=True)) if parts else ""


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


def _item(p, company, absolute, base, q, stock, ordering, extras=None):
    """One product for the website. `extras` = shop_extras(company, products): offer prices and review stars."""
    from apps.inventory.pictures import picture_url
    extras = extras or {}
    in_stock = not p.is_stock_tracked or stock.get(p.id, 0) > 0
    price, offer = extras["price"](p) if "price" in extras else (p.selling_price, "")
    left = int(stock.get(p.id, 0))
    stars = extras.get("stars", {}).get(p.id)
    return {"id": p.id, "name": f"{p.name} — {p.variant_label}" if p.variant_label else p.name,
            "category": p.category.name if p.category_id else "", "category_id": p.category_id,
            "price": f"{price:.2f}", "was": f"{p.selling_price:.2f}" if price < p.selling_price else "", "offer": offer,
            "image": absolute(picture_url(p, company.business_type.code)),
            "available": in_stock, "orderable": bool(ordering and ordering.get("open") and in_stock),
            "tracked": p.is_stock_tracked, "stock": left, "low": p.is_stock_tracked and 0 < left <= 3,
            "url": f"{base}shop/{p.id}/{q}", "rating": stars[0] if stars else None, "reviews": stars[1] if stars else 0,
            "brand": p.brand.name if p.brand_id else "", "description": (p.attributes or {}).get("web_description", "")}


def shop_extras(company, products):
    """Offer prices (same rules as the POS) and approved review stars for these products."""
    from django.db.models import Avg, Count
    from . import shop_orders
    from .models import ProductReview
    ids = [p.id for p in products]
    stars = {r["product_id"]: (round(float(r["avg"]), 1), r["n"]) for r in
             ProductReview.objects.filter(company=company, product_id__in=ids, is_approved=True)
             .values("product_id").annotate(avg=Avg("rating"), n=Count("id"))}
    return {"price": shop_orders.price_rules(company), "stars": stars}


# Attribute filters shown on the Shop page when the shop's products have them (labels from the product form).
FACET_ATTRS = ("gender", "fragrance_family", "concentration", "volume_ml", "flavour", "goal", "pack_size",
               "sport_category", "processor", "ram", "storage", "screen_size", "network", "material_spec", "age_group",
               "size_range", "purity", "strength")
FACET_MAX_VALUES = 30
FACET_LABELS = {"ram": _l("RAM"), "storage": _l("Storage"), "processor": _l("Processor"), "screen_size": _l("Screen size"),
                "network": _l("Network")}


def _num(value):
    from decimal import Decimal, InvalidOperation
    try:
        v = Decimal(str(value).strip())
        return v if v >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def _values(params, key):
    return [v.strip()[:80] for v in (params.getlist(key) if hasattr(params, "getlist") else params.get(key, []) or [])
            if v and v.strip()][:20]


def shop_page(design, absolute, base, lang, preview, params=None):
    """The Shop page: products with a filter side bar (category, brand, colour, size, price, stock and the
    shop type's own details such as RAM or fragrance family). Several ticks in one filter widen it (OR); filters
    together narrow it (AND). Counts are of the products matching the search and category."""
    from collections import Counter
    from django.db.models import Max, Min, Q
    from apps.inventory.models import Brand, ProductCategory
    from apps.webapp.forms import BusinessProductForm
    from . import shop_orders
    params = params or {}
    company = design.company
    ordering = shop_orders.config(company)
    all_qs = shop_orders.sellable(company).select_related("category", "brand")
    try:
        category_id = int(params.get("cat") or 0) or None
        page = int(params.get("page") or 1)
    except (TypeError, ValueError):
        category_id, page = None, 1
    cats = list(ProductCategory.objects.filter(company=company, id__in=all_qs.values("category_id")).order_by("name"))
    category = next((c for c in cats if c.id == category_id), None)
    search = (params.get("q") or "").strip()[:80]
    sort = params.get("sort") or ""
    scope = all_qs.filter(category=category) if category else all_qs
    if search:
        scope = scope.filter(Q(name__icontains=search) | Q(brand__name__icontains=search) | Q(sku__iexact=search) |
                             Q(category__name__icontains=search) | Q(variant_label__icontains=search))

    # ---- what the visitor ticked
    brands_on = {int(v) for v in _values(params, "brand") if v.isdigit()}
    colours_on, sizes_on = set(_values(params, "colour")), set(_values(params, "size"))
    attrs_on = {k: set(_values(params, f"a_{k}")) for k in FACET_ATTRS}
    attrs_on = {k: v for k, v in attrs_on.items() if v}
    pmin, pmax = _num(params.get("min") or ""), _num(params.get("max") or "")
    in_stock = params.get("stock") == "1"

    qs = scope
    wish = [int(x) for x in (params.get("ids") or "").split(",") if x.strip().isdigit()][:100]
    if wish:  # the visitor's saved list (kept in their browser)
        qs = qs.filter(id__in=wish)
    if brands_on:
        qs = qs.filter(brand_id__in=brands_on)
    if colours_on:
        qs = qs.filter(colour__in=colours_on)
    if sizes_on:
        qs = qs.filter(size__in=sizes_on)
    for key, values in attrs_on.items():
        cond = Q()
        for v in values:
            cond |= Q(**{f"attributes__{key}": v})
            n = _num(v)
            if n is not None and n == n.to_integral_value():
                cond |= Q(**{f"attributes__{key}": int(n)})
        qs = qs.filter(cond)
    if pmin is not None:
        qs = qs.filter(selling_price__gte=pmin)
    if pmax is not None:
        qs = qs.filter(selling_price__lte=pmax)
    if in_stock:
        stocked_ids = [pid for pid, q in shop_orders.stock_for(company, list(qs.filter(is_stock_tracked=True))).items() if q > 0]
        qs = qs.filter(Q(is_stock_tracked=False) | Q(id__in=stocked_ids))

    # ---- filter options with counts (from the products matching the search and category)
    rows = list(scope.values("brand_id", "colour", "size", "attributes")[:3000])
    brand_counts = Counter(r["brand_id"] for r in rows if r["brand_id"])
    brand_names = dict(Brand.objects.filter(id__in=brand_counts).values_list("id", "name"))
    colour_counts = Counter(r["colour"].strip() for r in rows if (r["colour"] or "").strip())
    size_counts = Counter(r["size"].strip() for r in rows if (r["size"] or "").strip())
    labels = BusinessProductForm.FIELD_LABELS
    attr_facets = []
    for key in FACET_ATTRS:
        counts = Counter(str(r["attributes"].get(key)).strip() for r in rows
                         if isinstance(r["attributes"], dict) and r["attributes"].get(key) not in (None, "", False, True))
        if counts and len(counts) <= FACET_MAX_VALUES and (len(counts) > 1 or key in attrs_on):
            attr_facets.append({"key": f"a_{key}", "label": FACET_LABELS.get(key) or labels.get(key) or key.replace("_", " ").capitalize(),
                                "options": [{"value": v, "label": v, "count": n, "on": v in attrs_on.get(key, ())}
                                            for v, n in sorted(counts.items(), key=lambda kv: kv[0].lower())]})
    span = scope.aggregate(lo=Min("selling_price"), hi=Max("selling_price"))

    def size_key(v):
        order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL"]
        return (0, order.index(v.upper()), 0) if v.upper() in order else (1, float(v) if _num(v) is not None else 0, v)

    facets = {
        "brands": [{"value": str(b), "label": brand_names.get(b, "?"), "count": n, "on": b in brands_on}
                   for b, n in sorted(brand_counts.items(), key=lambda kv: brand_names.get(kv[0], "").lower())],
        "colours": [{"value": c, "label": c, "count": n, "on": c in colours_on} for c, n in sorted(colour_counts.items())],
        "sizes": [{"value": z, "label": z, "count": n, "on": z in sizes_on} for z, n in sorted(size_counts.items(), key=lambda kv: size_key(kv[0]))],
        "attrs": attr_facets,
        "price_lo": int(span["lo"] or 0), "price_hi": int((span["hi"] or 0) + 1),
    }

    qs = qs.order_by({"low": "selling_price", "high": "-selling_price", "new": "-id"}.get(sort, "name"), "id")
    total = qs.count()
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    page_rows = list(qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE])
    q = query(lang, design, preview)
    stock = shop_orders.stock_for(company, page_rows)
    extras = shop_extras(company, page_rows)
    items = [_item(p, company, absolute, base, q, stock, ordering, extras) for p in page_rows]

    # the current choice, so links keep it (multi-value)
    current = {"cat": category.id if category else None, "q": search, "sort": sort, "ids": ",".join(map(str, wish)),
               "brand": sorted(str(b) for b in brands_on), "colour": sorted(colours_on), "size": sorted(sizes_on),
               "min": params.get("min") or "", "max": params.get("max") or "", "stock": "1" if in_stock else ""}
    current.update({f"a_{k}": sorted(v) for k, v in attrs_on.items()})

    def url(**change):
        state = {**current, **change}
        return f"{base}shop/" + query(lang, design, preview, **state)

    for c in cats:
        c.url = url(cat=c.id, page=None)
    chips = []
    for b in sorted(brands_on):
        chips.append({"label": brand_names.get(b, "?"), "url": url(brand=[x for x in current["brand"] if x != str(b)])})
    for key, label_key in (("colour", "colour"), ("size", "size")):
        for v in current[key]:
            chips.append({"label": v, "url": url(**{key: [x for x in current[key] if x != v]})})
    for k, values in attrs_on.items():
        for v in sorted(values):
            chips.append({"label": v, "url": url(**{f"a_{k}": [x for x in current[f"a_{k}"] if x != v]})})
    if current["min"] or current["max"]:
        chips.append({"label": f"{design.company.default_currency} {current['min'] or 0}–{current['max'] or '∞'}",
                      "url": url(min="", max="")})
    if in_stock:
        chips.append({"label": "✓", "url": url(stock=""), "stock": True})
    return {"items": items, "categories": cats, "category": category, "search": search, "sort": sort, "total": total,
            "page": page, "pages": pages, "ordering": ordering, "facets": facets, "chips": chips, "in_stock_only": in_stock,
            "wishlist": bool(wish),
            "price_min": current["min"], "price_max": current["max"],
            "clear_url": url(brand=[], colour=[], size=[], min="", max="", stock="", **{f"a_{k}": [] for k in attrs_on}),
            "all_url": url(cat=None),
            "prev_url": url(page=page - 1) if page > 1 else "",
            "next_url": url(page=page + 1) if page < pages else ""}


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
    extras = shop_extras(company, [p] + related)
    item = _item(p, company, absolute, base, q, stock, ordering, extras)
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
        specs.append((FACET_LABELS.get(key) or labels.get(key) or key.replace("_", " ").capitalize(), value))
    options = [{"id": s.id, "label": s.variant_label or s.name, "url": f"{base}shop/{s.id}/{q}"} for s in siblings]
    from .models import ProductPhoto, ProductReview
    photos = [item["image"]] + [absolute(ph.image.url) for ph in ProductPhoto.objects.filter(company=company, product=p)[:8]]
    reviews = list(ProductReview.objects.filter(company=company, product=p, is_approved=True)[:20])
    from apps.verticals.sports_shop.models import SizeChart
    chart = SizeChart.objects.filter(company=company, category_id=p.category_id).first() if p.category_id else None
    return {"item": item, "specs": specs, "options": options, "ordering": ordering, "size_chart": chart,
            "photos": photos if len(photos) > 1 else [], "product_reviews": reviews, "reviews_on": design.shop_reviews,
            "related": [_item(r, company, absolute, base, q, stock, ordering, extras) for r in related]}

"""
Website kit: what a client's own website (built by the platform admin in WordPress, plain HTML or
Python) uses to show the business's live data and send enquiries, bookings and job applications
into that client's BookPilot account only.
"""
import secrets

from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.modules.catalog import business_features, online_booking_kind

from .models import WebsiteKit


def kit_for(company):
    kit = WebsiteKit.objects.filter(company=company).first()
    if kit:
        return kit
    base = slugify(company.slug or company.name)[:50] or f"client-{company.pk}"
    slug, n = base, 2
    while WebsiteKit.objects.filter(public_id=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return WebsiteKit.objects.create(company=company, public_id=slug, api_key=secrets.token_urlsafe(32)[:48])


def by_public_id(public_id):
    return WebsiteKit.objects.select_related("company", "company__business_type").filter(
        public_id=public_id, company__is_active=True).first()


def key_ok(company, key):
    """True when a server-to-server call carries this company's kit API key."""
    if not key:
        return False
    kit = WebsiteKit.objects.filter(company=company).first()
    return bool(kit and secrets.compare_digest(kit.api_key, key))


def origins(kit):
    return {o.strip().rstrip("/") for o in kit.allowed_origins.splitlines() if o.strip()}


def capabilities(company):
    code = company.business_type.code
    return {"enquiry": True, "booking": online_booking_kind(code), "careers": "recruitment" in business_features(code),
            "catalogue": catalogue_kind(company)}


# ------------------------------------------------------------------ data the website shows

def info(company, absolute):
    """absolute(path) -> full URL. Public business details for the website header/footer/contact page."""
    return {"name": company.name, "business_type": company.business_type.name, "phone": company.phone,
            "email": company.email, "address": company.address, "country": company.country,
            "currency": company.default_currency, "logo": absolute(company.logo.url) if company.logo else None,
            "vat_number": company.vat_number}


def catalogue_kind(company):
    code = company.business_type.code
    features = business_features(code)
    if "recruitment" in features:
        return "jobs"
    if "bookings" in features:
        return "resources"
    if "education" in features:
        return "courses"
    if online_booking_kind(code) == "appointment":
        return "services"
    return "products"


def catalogue(company, absolute, limit=500):
    """Items for a menu / services / products / rooms / courses / jobs section."""
    kind = catalogue_kind(company)
    cur = company.default_currency
    items = []
    if kind == "jobs":
        from .careers import public_jobs, site_for
        site = site_for(company)
        for j in public_jobs(site)[:limit]:
            items.append({"id": j.id, "name": j.position, "location": j.work_location, "vacancies": j.vacancies,
                          "price": f"{j.salary:.0f}" if j.salary else None, "description": j.public_summary or j.requirements,
                          "benefits": j.benefits})
    elif kind == "resources":
        from .models import BookableResource
        for r in BookableResource.objects.for_company(company).filter(is_active=True)[:limit]:
            items.append({"id": r.id, "name": r.name, "category": r.get_kind_display(), "price": f"{r.rate:.2f}",
                          "unit": r.rate_unit, "capacity": r.capacity, "description": r.details})
    elif kind == "courses":
        from .models import Course
        for c in Course.objects.for_company(company).filter(is_active=True)[:limit]:
            items.append({"id": c.id, "name": c.name, "price": f"{c.fee:.2f}", "unit": c.billing,
                          "description": c.schedule, "teacher": c.teacher})
    elif kind == "services":
        from .online_booking import items as booking_items
        for s in booking_items(company, "appointment")[:limit]:
            items.append({"id": s["id"], "name": s["name"], "price": s["price"] or None, "minutes": s.get("minutes")})
    else:
        from apps.inventory.models import Product
        qs = Product.objects.for_company(company).filter(is_active=True).select_related("category").order_by("category__name", "name")
        menu = {}
        if company.business_type.code in ("restaurant", "cafe_juice_shop", "catering_company"):
            from apps.verticals.restaurant.models import RestaurantMenuItem
            menu = {m.product_id: m for m in RestaurantMenuItem.objects.for_company(company)}
            if menu:
                qs = qs.filter(id__in=menu.keys()).order_by("restaurant_menu_item__sort_order", "name")
        for p in qs[:limit]:
            m = menu.get(p.id)
            items.append({"id": p.id, "name": p.name, "category": p.category.name if p.category else "",
                          "price": f"{p.selling_price:.2f}", "description": getattr(m, "description", "") if m else "",
                          "image": absolute(m.image.url) if m and m.image else None,
                          "vegetarian": getattr(m, "is_vegetarian", None) if m else None,
                          "available": bool(m.is_available) if m else True,
                          "featured": bool(m.is_featured) if m else False})
    return {"kind": kind, "currency": cur, "items": items}


def offers(company):
    """Offers running today (POS promotions), for the website."""
    from .site_builder import offers as live_offers
    return {"currency": company.default_currency,
            "items": [{**o, "until": o["until"].isoformat()} for o in live_offers(company)]}


# ------------------------------------------------------------------ enquiries → CRM leads

def create_enquiry(kit, data, source=""):
    import re
    from apps.crm.models import Lead
    if not kit.enquiry_enabled:
        raise ValidationError("Enquiries are switched off.")
    name = (data.get("name") or "").strip()[:255]
    phone = (data.get("phone") or "").strip()[:30]
    email = (data.get("email") or "").strip()[:254]
    if not name or (len(re.sub(r"\D", "", phone)) < 7 and "@" not in email):
        raise ValidationError("Enter your name and a phone number or email.")
    company = kit.company
    owner = (company.memberships.filter(is_active=True, role__name="Owner").select_related("user").first()
             or company.memberships.select_related("user").first())
    subject = (data.get("subject") or "").strip()[:150]
    message = (data.get("message") or "").strip()[:4000]
    lead = Lead.objects.create(company=company, name=name, company_name=(data.get("company") or "")[:255], email=email,
                               phone=phone, source=f"Website{(' · ' + source) if source else ''}"[:100],
                               created_by=owner.user)
    if message or subject:
        from apps.crm.models import Activity
        Activity.objects.create(company=company, lead=lead, activity_type="note",
                                subject=(subject or "Website enquiry")[:255], notes=message, created_by=owner.user)
    try:
        from apps.notifications.services import notify
        notify(company=company, title=f"New website enquiry: {name}", message=f"{phone or email} · {subject or message[:120]}")
    except Exception:
        pass
    return lead

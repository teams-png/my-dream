"""The overview's "get started" checklist: what a new owner has done so far, with a link to each next step."""
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.modules.catalog import ALIASES, business_group

# where "add your own products / services" goes for businesses whose items live on their own screen
OWN_ITEMS_URL = {
    "saloon": "webapp:saloon_service_list", "spa": "webapp:spa_service_list",
    "beauty_parlour": "webapp:beauty_service_list", "gym": "webapp:plan_list",
    "vehicle_wash": "webapp:wash_package_list",
}


def milestones(company):
    from apps.tenants.models import CompanyOnboarding
    state, _ = CompanyOnboarding.objects.get_or_create(company=company)
    return state


def mark(company, key):
    """Records a first-time action (tour finished, receipt shared…). Safe to call often."""
    state = milestones(company)
    if key not in state.milestones:
        state.milestones = {**state.milestones, key: timezone.now().isoformat()}
        state.save(update_fields=["milestones", "updated_at"])


def _own_products(company):
    from apps.industry.models import SampleRecord
    from apps.inventory.models import Product
    sample_ids = SampleRecord.objects.filter(company=company, content_type=ContentType.objects.get_for_model(Product)) \
        .values_list("object_id", flat=True)
    return Product.objects.for_company(company).exclude(id__in=sample_ids).exclude(sku__startswith="KL-").exists()


def _team(company):
    from apps.employees.models import Employee
    from apps.industry.models import SampleRecord
    if company.memberships.count() > 1:
        return True
    sample_ids = SampleRecord.objects.filter(company=company, content_type=ContentType.objects.get_for_model(Employee)) \
        .values_list("object_id", flat=True)
    return Employee.objects.for_company(company).exclude(id__in=sample_ids).exclude(name__endswith="(sample)").exists()


def items(company):
    """[{key, label, done, url, icon, client}] — client=True items are ticked in the browser (devices live there)."""
    from apps.industry.models import SiteDesign
    from apps.sales.models import SalesInvoice
    code = ALIASES.get(company.business_type.code, company.business_type.code)
    done = milestones(company).milestones
    restaurant = business_group(code) == "restaurant"
    own_url = OWN_ITEMS_URL.get(code, "webapp:restaurant_setup" if restaurant else "webapp:product_list")
    rows = [
        ("profile", _("Add your logo and business details"), bool(company.logo), reverse("webapp:setup", args=["business"]), "🏷"),
        ("first_sale", _("Make your first sale"), SalesInvoice.objects.for_company(company).exists(),
         reverse("webapp:pos") + "?tour=1", "🧾"),
        ("own_items", _("Add your own products or services"), _own_products(company), reverse(own_url), "📦"),
        ("team", _("Add your staff"), _team(company), reverse("webapp:staff_invite"), "👥"),
        ("devices", _("Connect a printer or scanner"), "devices" in done, reverse("webapp:devices"), "🖨"),
        ("receipt", _("Send a receipt on WhatsApp"), "receipt_shared" in done, reverse("webapp:pos"), "💬"),
        ("website", _("Publish your website"), SiteDesign.objects.filter(company=company, published=True).exists(),
         reverse("webapp:site_editor"), "🌐"),
    ]
    return [{"key": k, "label": label, "done": bool(d), "url": url, "icon": icon, "client": k == "devices"}
            for k, label, d, url, icon in rows]


def summary(company):
    rows = items(company)
    finished = sum(r["done"] for r in rows)
    return {"items": rows, "done": finished, "total": len(rows), "percent": round(100 * finished / len(rows)),
            "hidden": "checklist_hidden" in milestones(company).milestones,
            "next": next((r for r in rows if not r["done"]), None)}

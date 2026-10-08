"""Sample data for every business type: a new business opens with example products, services, categories,
sizes / colours / gender, customers and (for service businesses) staff, so each screen shows how it is used.

Everything made here is recorded in SampleRecord and removed in one click (remove()). Anything already used in a
bill or booking is switched off instead of deleted, so the owner's real records are never touched.
Restaurants keep their own Kerala menu kit (apps.verticals.restaurant.starter_kit).
"""
import datetime
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.modules.catalog import ALIASES, business_group

from . import sample_catalog as data
from .models import SampleRecord

log = logging.getLogger(__name__)
SKU_PREFIX = "SMP-"
MODEL_FIELDS = ("size", "colour", "material", "design")  # stored on Product itself; everything else goes to attributes
SALON_TYPES = ("saloon", "beauty_parlour", "spa")
STAFF_TYPES = {"saloon", "beauty_parlour", "spa", "gym", "vehicle_wash", "textile", "cycle_shop", "mobile_shop"}


def enabled():
    return getattr(settings, "SAMPLE_DATA_KIT", True)


def _code(company):
    code = company.business_type.code
    return ALIASES.get(code, code)


def applies(company):
    return business_group(_code(company)) != "restaurant"


def has_samples(company):
    return SampleRecord.objects.for_company(company).exists()


def summary(company):
    """{'products': n, 'services': n, 'customers': n, 'staff': n} for the banner."""
    from apps.customers.models import Customer
    from apps.employees.models import Employee
    from apps.inventory.models import Product
    rows = SampleRecord.objects.for_company(company)
    by_model = {}
    for ct_id, obj_id in rows.values_list("content_type_id", "object_id"):
        by_model.setdefault(ct_id, set()).add(obj_id)
    ct = ContentType.objects.get_for_model
    products = Product.objects.filter(id__in=by_model.get(ct(Product).id, ()))
    return {"products": products.filter(is_stock_tracked=True, parent__isnull=True).count(),
            "services": products.filter(is_stock_tracked=False).count(),
            "customers": len(by_model.get(ct(Customer).id, ())),
            "staff": len(by_model.get(ct(Employee).id, ())),
            "total": rows.count()}


def kit_for(code):
    """What a business type starts with: its own kit, its family's, or its group's."""
    code = ALIASES.get(code, code)
    group = business_group(code)
    kit = {"products": [], "variants": [], "services": []}
    own = data.KITS.get(code) or data.KITS.get(data.RETAIL_FAMILY.get(code, ""))
    if own is None and group == "retail":
        own = data.FAMILY_KITS.get(data.RETAIL_FAMILY.get(code, ""), data.FAMILY_KITS["general"])
    for key in kit:
        kit[key] = list((own or {}).get(key, []))
    if code in data.SALON_SERVICES:
        kit["products"] += data.SALON_PRODUCTS[code]
    if code == "gym":
        kit["products"] += data.GYM_PRODUCTS
        kit["services"] += data.GYM_SERVICES
    if code == "vehicle_wash":
        kit["products"] += data.WASH_PRODUCTS
    kit["services"] += data.SERVICE_KITS.get(code, []) + data.PROJECT_SERVICES.get(code, []) + \
        data.BOOKING_SERVICES.get(code, [])
    kit["products"] += data.PROJECT_MATERIALS.get(code, [])
    if group == "service" and not kit["services"] and code not in data.COURSES:
        kit["services"] = list(data.FAMILY_KITS["general"]["services"])
    if group == "project" and not kit["services"]:
        kit["services"] = [data.S("Project fee – milestone", "Projects", 2000), data.S("Hourly consulting", "Services", 150)]
    return kit


# ------------------------------------------------------------------ install

class _Kit:
    def __init__(self, company, user):
        from apps.inventory.models import Warehouse
        self.company, self.user = company, user
        self.factor = Decimal(str(_currency_factors().get((company.default_currency or "QAR").upper(), 1)))
        if not Warehouse.objects.filter(company=company).exists():
            from apps.tenants.services import provision_company_basics
            provision_company_basics(company=company)  # sign-up makes the main branch right after; same result
        self.warehouse = Warehouse.objects.filter(company=company, is_default=True).first() or \
            Warehouse.objects.filter(company=company).first()
        self.cache = {}
        self.n = 0

    def track(self, obj):
        SampleRecord.objects.create(company=self.company, content_type=ContentType.objects.get_for_model(obj),
                                    object_id=obj.pk)
        return obj

    def money(self, qar):
        value = Decimal(str(qar)) * self.factor
        if not value:
            return Decimal("0.00")
        step = Decimal("1") if value >= 50 else (Decimal("0.5") if value >= 1 else Decimal("0.05"))
        return ((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step).quantize(Decimal("0.01"))

    def named(self, model, name, **defaults):
        """Reuse the business's own category / brand / unit of that name; make (and track) it otherwise."""
        key = (model, name)
        if key not in self.cache:
            obj = model.objects.filter(company=self.company, name=name).first()
            if obj is None:
                obj = self.track(model.objects.create(company=self.company, name=name, **defaults))
            self.cache[key] = obj
        return self.cache[key]

    def sku(self):
        from apps.inventory.models import Product
        while True:
            self.n += 1
            sku = f"{SKU_PREFIX}{self.n:03d}"
            if not Product.objects.filter(company=self.company, sku=sku).exists():
                return sku

    def product(self, row, *, name=None, stocked=True, parent=None, size="", colour="", stock=0):
        from apps.inventory.models import Brand, Product, ProductCategory, Unit
        attrs = dict(row.get("attrs") or {})
        fields = {f: str(attrs.pop(f)) for f in MODEL_FIELDS if f in attrs}
        if size:
            fields["size"] = size
        if colour:
            fields["colour"] = colour
        for special in ("fabric_type", "sport_category"):
            attrs.pop(special, None)
        attrs = {k: v for k, v in attrs.items() if v not in ("", None)}
        price = self.money(row["price"])
        product = Product.objects.create(
            company=self.company, sku=self.sku(), name=name or row["name"],
            category=self.named(ProductCategory, row["category"]),
            brand=self.named(Brand, row["brand"]) if row.get("brand") else None,
            unit=self.named(Unit, row.get("unit") or ("pcs" if stocked else "service")),
            selling_price=price, cost_price=(price * Decimal("0.6")).quantize(Decimal("0.01")) if stocked else 0,
            reorder_level=2 if stocked else 0, is_stock_tracked=stocked, tracking_type="basic" if stocked else "none",
            parent=parent, attributes=attrs, **fields)
        self.track(product)
        if stocked and stock and self.warehouse:
            self.opening_stock(product, stock)
            if attrs.get("item_type") == "handset":
                self.handsets(product, stock)
        self.details(product, row, size or fields.get("size", ""))
        return product

    def handsets(self, product, count):
        """A mobile shop sells each phone by its IMEI: one in-stock unit per phone."""
        from apps.verticals.mobile_shop.models import MobileUnit
        for i in range(int(count)):
            self.track(MobileUnit.objects.create(
                company=self.company, product=product, imei=f"35{product.pk:06d}{i + 1:07d}"[:15], condition="new",
                warranty_months=12, purchase_price=product.cost_price, warehouse=self.warehouse))

    def opening_stock(self, product, quantity):
        from apps.inventory.models import StockMovement
        self.track(StockMovement.objects.create(company=self.company, product=product, warehouse=self.warehouse,
                                                quantity=Decimal(str(quantity)), reason="adjustment",
                                                reference="Sample opening stock"))

    def details(self, product, row, size):
        attrs = row.get("attrs") or {}
        code = _code(self.company)
        if code == "textile" and attrs.get("fabric_type"):
            from apps.verticals.textile.models import FabricDetail
            self.track(FabricDetail.objects.create(company=self.company, product=product, fabric_type=attrs["fabric_type"],
                                                   color=attrs.get("colour", ""), design=attrs.get("design", ""),
                                                   material=attrs.get("material", "")))
        if code == "sports_shop":
            from apps.verticals.sports_shop.models import SportsProductDetail
            gender = str(attrs.get("gender", "unisex")).lower()
            self.track(SportsProductDetail.objects.create(
                company=self.company, product=product, sport_category=attrs.get("sport_category", "other"),
                size=size, gender=gender if gender in ("men", "women", "unisex", "kids") else "unisex",
                material=attrs.get("material", "")))

    def variants(self, row):
        """A parent product plus one product per size × colour, each with its own stock."""
        parent = self.product(row)
        for colour in row["colours"] or [""]:
            for size in row["sizes"] or [""]:
                self.product(row, parent=parent, size=size, colour=colour, stock=row["stock"])
        return parent

    def service(self, row):
        attrs = {"item_type": "service"} if _code(self.company) == "mobile_shop" else {}
        return self.product({**row, "unit": "service", "attrs": attrs}, stocked=False)


def _currency_factors():
    from apps.verticals.restaurant.kerala_menu import CURRENCY_FACTORS
    return CURRENCY_FACTORS


@transaction.atomic
def install(company, user=None):
    """Adds the sample kit for this business type. Does nothing if it is already there. Returns objects made."""
    if not applies(company) or has_samples(company):
        return 0
    code = _code(company)
    kit = _Kit(company, user)
    spec = kit_for(code)
    for row in spec["products"]:
        kit.product(row, stock=row.get("stock", 0))
    for row in spec["variants"]:
        kit.variants(row)
    for row in spec["services"]:
        kit.service(row)
    if code in SALON_TYPES:
        _salon(kit, code)
    if code == "gym":
        _gym(kit)
    if code == "vehicle_wash":
        _wash(kit)
    if code in data.BOOKING_RESOURCES:
        _resources(kit, code)
    if code in data.COURSES:
        _courses(kit, code)
    if code in ("property_management", "real_estate_brokerage"):
        _properties(kit)
    _people(kit, code)
    return SampleRecord.objects.for_company(company).count()


def _salon(kit, code):
    from apps.inventory.models import ProductCategory
    if code == "saloon":
        from apps.verticals.saloon.services import create_saloon_service as make, create_service_package as make_pkg
    elif code == "spa":
        from apps.verticals.spa.services import create_spa_service as make, create_service_package as make_pkg
    else:
        from apps.verticals.beauty_parlour.services import create_beauty_service as make, create_service_package as make_pkg
    made = {}
    for row in data.SALON_SERVICES[code]:
        service = make(company=kit.company, name=row["name"], duration_minutes=row["minutes"], price=kit.money(row["price"]),
                       category=kit.named(ProductCategory, row["category"]))
        kit.track(service.product)
        kit.track(service)
        made[row["name"]] = service
    name, service_name, sessions, price = data.SALON_PACKAGES[code]
    package = make_pkg(company=kit.company, name=name, service=made[service_name], session_count=sessions,
                       price=kit.money(price), category=kit.named(ProductCategory, "Packages"))
    kit.track(package.product)
    kit.track(package)


def _gym(kit):
    from apps.inventory.models import ProductCategory
    from apps.verticals.gym.services import create_membership_plan
    for name, days, price in data.GYM_PLANS:
        plan = create_membership_plan(company=kit.company, name=name, duration_days=days, price=kit.money(price),
                                      category=kit.named(ProductCategory, "Memberships"))
        kit.track(plan.product)
        kit.track(plan)


def _wash(kit):
    from apps.inventory.models import ProductCategory
    from apps.verticals.vehicle_wash.services import create_wash_package
    for name, vehicle_type, price, minutes, description in data.WASH_PACKAGES:
        package = create_wash_package(company=kit.company, name=name, vehicle_type=vehicle_type, price=kit.money(price),
                                      duration_minutes=minutes, description=description,
                                      category=kit.named(ProductCategory, "Wash packages"))
        kit.track(package.product)
        kit.track(package)


def _resources(kit, code):
    from .models import BookableResource
    for i, (name, kind, rate, unit, capacity, details) in enumerate(data.BOOKING_RESOURCES[code]):
        kit.track(BookableResource.objects.create(company=kit.company, name=name, kind=kind, rate=kit.money(rate),
                                                  rate_unit=unit, capacity=capacity, details=details, sort_order=i))


def _courses(kit, code):
    from .models import Course
    for name, fee, billing, schedule, teacher in data.COURSES[code]:
        kit.track(Course.objects.create(company=kit.company, name=name, fee=kit.money(fee), billing=billing,
                                        schedule=schedule, teacher=teacher))


def _properties(kit):
    from .models import Property, RentalUnit
    for name, kind, address, units in data.PROPERTIES:
        prop = kit.track(Property.objects.create(company=kit.company, name=name, kind=kind, address=address))
        for unit_name, unit_kind, bedrooms, size, rent in units:
            kit.track(RentalUnit.objects.create(company=kit.company, property=prop, name=unit_name, kind=unit_kind,
                                                bedrooms=bedrooms, size=size, monthly_rent=kit.money(rent)))


def _people(kit, code):
    from apps.customers.models import Customer
    from apps.suppliers.models import Supplier
    company = kit.company
    for name, phone, email in data.CUSTOMERS:
        kit.track(Customer.objects.create(company=company, name=f"{name} (sample)", phone=phone, email=email))
    if business_group(code) == "retail" or code in data.PROJECT_MATERIALS:
        for name, phone in data.SUPPLIERS:
            kit.track(Supplier.objects.create(company=company, name=f"{name} (sample)", phone=phone))
    if code in STAFF_TYPES or business_group(code) == "service":
        from apps.employees.models import Employee
        if not Employee.objects.filter(company=company).exists():
            joined = timezone.localdate() - datetime.timedelta(days=180)
            for i, (name, role, salary) in enumerate(data.STAFF):
                kit.track(Employee.objects.create(company=company, name=f"{name} (sample)", role_title=role,
                                                  phone=f"+974 5000 20{i + 1:02d}", salary=kit.money(salary),
                                                  joined_date=joined))


def install_for_new_company(company, user):
    """Called from sign-up. Never blocks sign-up: a problem here is logged and skipped."""
    if not enabled() or not applies(company):
        return 0
    try:
        with transaction.atomic():
            return install(company, user)
    except Exception:
        log.exception("Sample data kit failed for company %s", company.pk)
        return 0


# ------------------------------------------------------------------ remove

@transaction.atomic
def remove(company):
    """Deletes everything the kit made, newest first. Things already used (sold, booked, enrolled) are switched off
    instead. Returns how many were kept that way."""
    kept = 0
    rows = list(SampleRecord.objects.for_company(company).select_related("content_type").order_by("-id"))
    for row in rows:
        model = row.content_type.model_class()
        obj = model._default_manager.filter(pk=row.object_id).first() if model else None
        if obj is None:
            continue
        try:
            with transaction.atomic():
                obj.delete()
        except ProtectedError:
            kept += 1
            changed = [f for f in ("is_active",) if hasattr(obj, f)]
            if changed:
                obj.is_active = False
                if hasattr(obj, "employment_status"):
                    obj.employment_status = "inactive"
                    changed.append("employment_status")
                obj.save(update_fields=changed)
    SampleRecord.objects.for_company(company).delete()
    return kept

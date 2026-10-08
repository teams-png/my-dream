"""Public "Try demo" businesses: anyone can open one without signing up.

Each demo is a normal business marked is_demo, filled with the sample kit (or the Kerala menu) and a few days
of sales. Visitors share it. Every night a demo that someone used is archived and a fresh one made, so the next
visitor starts clean. Risky actions (passwords, staff, exports, sending email…) are blocked by DemoGuardMiddleware.
"""
import datetime
import logging
import random
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

log = logging.getLogger(__name__)

# (business type, name, icon)
DEMOS = [("saloon", "Style Cuts Salon", "💈"), ("supermarket", "FreshMart Supermarket", "🛒"),
         ("clothing_store", "Lulu Fashion", "👗"), ("restaurant", "Spice Garden Restaurant", "🍽️"),
         ("mobile_shop", "Smart Mobiles", "📱")]
CODES = {code for code, _n, _i in DEMOS}


def current(code):
    from apps.tenants.models import Company
    return Company.objects.filter(is_demo=True, is_active=True, business_type__code=code).order_by("-id").first()


def ensure(code):
    return current(code) or create(code)


@transaction.atomic
def create(code):
    from apps.accounts.models import User
    from apps.industry import sample_kit
    from apps.modules.catalog import BUSINESS_TYPE_MAP
    from apps.modules.models import BusinessType
    from apps.subscriptions.models import SubscriptionPlan
    from apps.tenants.services import create_company_with_owner, provision_company_basics
    name = dict((c, n) for c, n, _i in DEMOS)[code]
    stamp = timezone.now().strftime("%Y%m%d") + uuid.uuid4().hex[:6]
    email = f"demo-{code}-{stamp}@demo.bookpilot.invalid"
    user = User.objects.create_user(username=email, email=email, first_name="Demo", last_name="Owner")
    user.set_unusable_password()  # nobody can sign in to it with a password
    user.save(update_fields=["password"])
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": BUSINESS_TYPE_MAP[code]})
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("-max_users", "-price").first()
    company = create_company_with_owner(user=user, name=name, slug=f"demo-{code}-{stamp}", business_type=business_type,
                                        country="Qatar", phone="+974 4400 0000", email=email, default_currency="QAR",
                                        plan=plan)
    company.is_demo = True
    company.save(update_fields=["is_demo"])
    provision_company_basics(company=company)
    sub = company.subscription
    sub.status, sub.end_date = "active", timezone.localdate() + datetime.timedelta(days=3650)
    sub.save(update_fields=["status", "end_date"])
    if code == "restaurant":
        from apps.verticals.restaurant import starter_kit
        if not starter_kit.has_kit(company):
            starter_kit.install(company, user)
    elif not sample_kit.has_samples(company):
        sample_kit.install(company, user)
    _sales_history(company, user)
    return company


def _sales_history(company, user, days=6):
    """A few bills on each of the last days, so the overview and reports have something to show."""
    from apps.customers.models import Customer
    from apps.inventory.models import Product, Warehouse
    from apps.sales.services import create_invoice, record_customer_payment
    rng = random.Random(company.pk)
    warehouse = Warehouse.objects.filter(company=company).first()
    customers = list(Customer.objects.for_company(company).filter(is_active=True)[:3])
    products = [p for p in Product.objects.for_company(company).filter(is_active=True, variants__isnull=True)
                if (p.attributes or {}).get("item_type") != "handset" and p.selling_price > 0 and
                (not p.is_stock_tracked or p.current_stock() > 3)][:12]
    if not (warehouse and customers and products):
        return
    today = timezone.localdate()
    for back in range(days, 0, -1):
        for _ in range(rng.randint(2, 4)):
            picks = rng.sample(products, min(len(products), rng.randint(1, 3)))
            try:
                invoice = create_invoice(
                    company=company, user=user, customer=rng.choice(customers), date=today - datetime.timedelta(days=back),
                    lines=[{"product": p, "quantity": Decimal("1"), "unit_price": p.selling_price} for p in picks],
                    warehouse=warehouse)
                record_customer_payment(company=company, user=user, customer=invoice.customer, amount=invoice.total,
                                        date=invoice.date, invoice=invoice, method=rng.choice(["cash", "card"]))
            except Exception:  # a sample item running out of stock is fine: skip that bill
                log.warning("demo bill skipped", exc_info=True)


def mark_used(company):
    from apps.webapp.checklist import milestones
    state = milestones(company)
    if "demo_used" not in state.milestones:
        state.milestones = {**state.milestones, "demo_used": timezone.now().isoformat()}
        state.save(update_fields=["milestones", "updated_at"])


def nightly_reset():
    """Daily job: a demo somebody used is archived and replaced by a fresh one."""
    from apps.tenants.models import Company
    renewed = 0
    for company in Company.objects.filter(is_demo=True, is_active=True).select_related("business_type"):
        onboarding = getattr(company, "onboarding", None)
        if not onboarding or "demo_used" not in (onboarding.milestones or {}):
            continue
        company.is_active = False
        company.archived_at = timezone.now()
        company.save(update_fields=["is_active", "archived_at"])
        try:
            create(company.business_type.code)
            renewed += 1
        except Exception:
            log.exception("could not renew demo %s", company.business_type.code)
    return renewed

"""
Subscription pricing.

Two price lists only:
  * India      -> INR prices
  * everywhere else (Qatar, GCC, UK, USA, Europe, ...) -> QAR prices

and two tiers per list: normal businesses, and supermarkets / large shops.
Customers outside Qatar are always charged the QAR price; `local_estimate`
only *shows* roughly what that is in their own currency.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

INDIA, GLOBAL = "India", "Global"
REGION_CURRENCY = {INDIA: "INR", GLOBAL: "QAR"}
USER_STEPS = (1, 3, 5)

# Business types billed at the supermarket / large-shop price.
LARGE_BUSINESS_TYPES = {"supermarket", "wholesale_business"}

PRICE_TABLE = {
    (GLOBAL, "standard"): {1: 399, 3: 699, 5: 899},
    (GLOBAL, "large"): {1: 499, 3: 899, 5: 1199},
    (INDIA, "standard"): {1: 3999, 3: 6999, 5: 8999},
    (INDIA, "large"): {1: 5999, 3: 9999, 5: 13999},
}
TIER_LABEL = {"standard": "Business", "large": "Large Shop"}

# Yearly add-ons: each user above the biggest plan's users, and each branch above the first.
# India follows the same ratio as its plan prices (QAR 899 plan = INR 8,999), so QAR 100 = INR 1,000.
ADDON_PRICES = {GLOBAL: {"user": 100, "branch": 100}, INDIA: {"user": 1000, "branch": 1000}}

# How much of each currency one QAR buys, for display only. The GCC
# currencies and USD are pegged, so these are exact; the others float and
# are approximate — override with the DISPLAY_FX_PER_QAR setting.
DEFAULT_FX_PER_QAR = {
    "QAR": "1", "USD": "0.2747", "AED": "1.0089", "SAR": "1.0302", "OMR": "0.1056", "BHD": "0.1033",
    "KWD": "0.0843", "GBP": "0.2050", "EUR": "0.2350", "CAD": "0.3800", "AUD": "0.4200",
}
PEGGED = {"QAR", "USD", "AED", "SAR", "OMR", "BHD"}

CURRENCY_BY_COUNTRY = {
    "Qatar": "QAR", "United Arab Emirates": "AED", "Saudi Arabia": "SAR", "Oman": "OMR", "Kuwait": "KWD",
    "Bahrain": "BHD", "India": "INR", "United Kingdom": "GBP", "United States": "USD", "Canada": "CAD",
    "Australia": "AUD", "Germany": "EUR", "France": "EUR", "Ireland": "EUR", "Netherlands": "EUR",
    "Italy": "EUR", "Spain": "EUR",
}


def region_for(country):
    return INDIA if (country or "").strip().lower() == "india" else GLOBAL


def tier_for(business_type_code):
    return "large" if business_type_code in LARGE_BUSINESS_TYPES else "standard"


def plan_name(tier, users):
    return f"{TIER_LABEL[tier]} · {users} user{'s' if users > 1 else ''}"


def plans_for(country, business_type_code):
    from .models import SubscriptionPlan
    return SubscriptionPlan.objects.filter(
        is_active=True, country=region_for(country), tier=tier_for(business_type_code),
    ).order_by("max_users", "price")


def ensure_default_plans(modules=()):
    """
    Creates the 12 standard plans if they are missing. Existing plans are
    never changed, so prices edited by the platform admin survive deploys.
    """
    from .models import SubscriptionPlan
    # the old free placeholder plan is no longer offered to new sign-ups
    SubscriptionPlan.objects.filter(name="Starter", price=0, is_active=True).update(is_active=False)
    created = 0
    for (region, tier), prices in PRICE_TABLE.items():
        for users, price in prices.items():
            match = dict(country=region, tier=tier, max_users=users, billing_period="yearly",
                         currency=REGION_CURRENCY[region])
            if SubscriptionPlan.objects.filter(**match).exclude(name="Starter", price=0).exists():
                continue
            addon = ADDON_PRICES.get(region, {})
            plan = SubscriptionPlan.objects.create(
                name=plan_name(tier, users), price=Decimal(price),
                extra_user_price=Decimal(addon.get("user", 0)) if users == max(USER_STEPS) else Decimal("0"),
                extra_branch_price=Decimal(addon.get("branch", 0)), **match)
            created += 1
            if modules:
                plan.modules.set(modules)
    return created


def seats_used(company):
    """Logins that count against the plan's users: everyone except the business owner, whose login is free.
    So a 1-user plan is the owner plus one Accountant or Staff login."""
    from apps.tenants.models import CompanyMembership
    return (CompanyMembership.objects.filter(company=company, is_active=True)
            .exclude(role__name="Owner", role__is_system_role=True).count())


def seats(company):
    """For the team pages: users the plan includes (besides the owner), used, left, and the add-on price."""
    sub = getattr(company, "subscription", None)
    if sub is None:
        return None
    used = seats_used(company)
    limit = sub.plan.max_users
    return {"limit": limit, "used": used, "left": max(limit - used, 0), "extra_price": sub.plan.extra_user_price,
            "currency": sub.plan.currency, "full": used >= limit and not sub.plan.extra_user_price}


def usage(company):
    """(users counted against the plan, active branches) of a company."""
    from apps.inventory.models import Warehouse
    branches = Warehouse.objects.for_company(company).filter(is_active=True).count()
    return seats_used(company), max(branches, 1)


def addons(subscription, company=None):
    """What the subscription costs per period: the plan plus extra users and extra branches in use."""
    plan = subscription.plan
    users, branches = usage(company or subscription.company)
    extra_users = max(users - plan.max_users, 0) if plan.extra_user_price else 0
    extra_branches = max(branches - plan.max_warehouses, 0) if plan.extra_branch_price else 0
    users_amount = plan.extra_user_price * extra_users
    branches_amount = plan.extra_branch_price * extra_branches
    return {"users": users, "branches": branches, "extra_users": extra_users, "extra_branches": extra_branches,
            "extra_user_price": plan.extra_user_price, "extra_branch_price": plan.extra_branch_price,
            "users_amount": users_amount, "branches_amount": branches_amount,
            "plan_price": plan.price, "total": plan.price + users_amount + branches_amount, "currency": plan.currency}


def amount_due(subscription):
    return addons(subscription)["total"]


def fx_rates():
    rates = dict(DEFAULT_FX_PER_QAR)
    rates.update(getattr(settings, "DISPLAY_FX_PER_QAR", None) or {})
    return {code: Decimal(str(value)) for code, value in rates.items()}


def local_estimate(amount, from_currency, to_currency):
    """
    Roughly converts a QAR price for display. Returns None when no
    conversion is needed or possible (e.g. INR plans are already local).
    """
    if not to_currency or from_currency != "QAR" or to_currency == "QAR":
        return None
    rate = fx_rates().get(to_currency)
    if rate is None:
        return None
    value = Decimal(amount) * rate
    step = Decimal("1") if value >= 100 else Decimal("0.1")
    return value.quantize(step, rounding=ROUND_HALF_UP)


def is_exact(currency):
    return currency in PEGGED

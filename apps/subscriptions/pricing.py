"""
Subscription pricing.

Two price lists: India in INR (plus GST, see PLAN_TAX_PERCENT) and Global in QAR, each with two tiers (normal businesses, and supermarkets /
large shops, same prices for now). The PRICING_REGION setting picks the one this site sells: every new
sign-up gets that list whatever their country. On the QAR list, customers outside Qatar are charged the QAR
price and `local_estimate` only *shows* roughly what that is in their own currency.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

INDIA, GLOBAL = "India", "Global"
REGION_CURRENCY = {INDIA: "INR", GLOBAL: "QAR"}
USER_STEPS = (1, 3, 5)

# Business types billed at the supermarket / large-shop price.
LARGE_BUSINESS_TYPES = {"supermarket", "wholesale_business"}

# Yearly plan prices by number of users (QAR for Global, INR for India).
PRICE_TABLE = {
    (GLOBAL, "standard"): {1: 699, 3: 899, 5: 999},
    (GLOBAL, "large"): {1: 699, 3: 899, 5: 999},
    (INDIA, "standard"): {1: 4999, 3: 7999, 5: 10999},
    (INDIA, "large"): {1: 4999, 3: 7999, 5: 10999},
}
TIER_LABEL = {"standard": "Business", "large": "Large Shop"}

# Yearly add-ons: each user above the biggest plan's users, and each branch above the first.
ADDON_PRICES = {GLOBAL: {"user": 100, "branch": 300}, INDIA: {"user": 2000, "branch": 2500}}
# Yearly website add-ons: a website (pages, products, enquiries) or an e-commerce website (adds cart and orders).
WEBSITE_PRICES = {GLOBAL: {"website": 499, "shop": 799}, INDIA: {"website": 4999, "shop": 9999}}

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


def sales_region():
    """The price list this site sells to new customers (the PRICING_REGION setting)."""
    region = getattr(settings, "PRICING_REGION", GLOBAL)
    return region if region in REGION_CURRENCY else GLOBAL


def region_for(country):
    """Every country gets the site's price list; the country only changes the currency shown as an estimate."""
    return sales_region()


def tier_for(business_type_code):
    return "large" if business_type_code in LARGE_BUSINESS_TYPES else "standard"


def plan_name(tier, users):
    return f"{TIER_LABEL[tier]} · {users} user{'s' if users > 1 else ''}"


def plans_for(country, business_type_code, region=None):
    """Active plans for a sign-up; `region` keeps an existing customer on the price list they already pay in."""
    from .models import SubscriptionPlan
    return SubscriptionPlan.objects.filter(
        is_active=True, country=region or region_for(country), tier=tier_for(business_type_code),
    ).order_by("max_users", "price")


def ensure_default_plans(modules=()):
    """
    Creates the 6 standard plans if they are missing. Existing plans are
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
    site = website_addon(company or subscription.company, plan)
    website_amount = site[2] if site else Decimal("0")
    subtotal = plan.price + users_amount + branches_amount + website_amount
    percent = tax_percent(plan.currency)
    tax = (subtotal * percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"users": users, "branches": branches, "extra_users": extra_users, "extra_branches": extra_branches,
            "extra_user_price": plan.extra_user_price, "extra_branch_price": plan.extra_branch_price,
            "users_amount": users_amount, "branches_amount": branches_amount,
            "website": site[1] if site else "", "website_amount": website_amount,
            "plan_price": plan.price, "subtotal": subtotal, "tax_percent": percent, "tax_label": tax_label(), "tax": tax,
            "total": subtotal + tax, "currency": plan.currency}


def website_addon(company, plan=None):
    """(package, label, yearly price) of the client's website add-on, or None when it is off."""
    from apps.industry.models import SiteDesign
    design = SiteDesign._base_manager.filter(company=company, enabled=True).first()
    if design is None:
        return None
    region = plan.country if plan and plan.country in WEBSITE_PRICES else region_for(company.country)
    price = Decimal(WEBSITE_PRICES[region][design.package])
    return design.package, design.get_package_display(), price


def tax_percent(currency):
    """Tax added on top of the plan prices (India: 18% GST, set by PLAN_TAX_PERCENT). Only INR plans are taxed."""
    if currency != REGION_CURRENCY[INDIA]:
        return Decimal("0")
    return Decimal(str(getattr(settings, "PLAN_TAX_PERCENT", 0) or 0))


def tax_label():
    return getattr(settings, "PLAN_TAX_LABEL", "GST")


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

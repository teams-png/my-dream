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
            plan = SubscriptionPlan.objects.create(name=plan_name(tier, users), price=Decimal(price), **match)
            created += 1
            if modules:
                plan.modules.set(modules)
    return created


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

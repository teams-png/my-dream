from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Customer, LoyaltyAccount, LoyaltyTransaction

def get_or_create_walkin_customer(company):
    """
    Several verticals (mobile_shop, cycle_shop, medical_shop, protein_shop,
    ...) let the buyer/customer field on a sale be optional, for genuine
    over-the-counter/anonymous sales — but sales.services.create_invoice()
    requires a real Customer (SalesInvoice.customer has no null=True, by
    design: every invoice must be attributable to someone, even if that
    someone is a shared placeholder). This is the one shared place that
    placeholder is created, so every vertical's "walk-in" sale points at
    the same row per company rather than each growing its own convention.
    """
    customer, _ = Customer.objects.get_or_create(
        company=company, name="Walk-in Customer", defaults={"is_active": True},
    )
    return customer


@transaction.atomic
def earn_points(*, company, customer, amount_spent, date, reference=""):
    from apps.sales.models import CommercialSettings
    settings, _ = CommercialSettings.objects.get_or_create(company=company)
    if not settings.loyalty_enabled or settings.loyalty_spend_per_point <= 0:
        return None
    points = int(Decimal(amount_spent) // settings.loyalty_spend_per_point)
    if points <= 0:
        return None
    account, _ = LoyaltyAccount.objects.get_or_create(company=company, customer=customer)
    account.points_balance += points
    account.save(update_fields=["points_balance"])
    LoyaltyTransaction.objects.create(
        company=company, account=account, points=points, type="earn", reference=reference, date=date,
    )
    return points


@transaction.atomic
def redeem_points(*, company, customer, points, date, reference=""):
    account = LoyaltyAccount.objects.filter(company=company, customer=customer).first()
    if not account or account.points_balance < points:
        raise ValidationError("Not enough points for this redemption.")
    account.points_balance -= points
    account.save(update_fields=["points_balance"])
    LoyaltyTransaction.objects.create(
        company=company, account=account, points=-points, type="redeem", reference=reference, date=date,
    )
    return account


@transaction.atomic
def redeem_points_for_discount(*, company, customer, points, date, reference=""):
    from apps.sales.models import CommercialSettings
    points = int(points)
    if points <= 0:
        return Decimal("0")
    settings, _ = CommercialSettings.objects.get_or_create(company=company)
    if not settings.loyalty_enabled:
        raise ValidationError("Loyalty redemption is disabled.")
    redeem_points(company=company, customer=customer, points=points, date=date, reference=reference)
    return (Decimal(points) * settings.loyalty_currency_per_point).quantize(Decimal("0.01"))

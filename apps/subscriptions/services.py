from datetime import timedelta
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from .models import SubscriptionPlan, Subscription

TRIAL_DAYS = 7
EXPIRY_NOTIFY_THRESHOLDS = (30, 15, 7, 3, 1)


def is_subscription_usable(subscription):
    """Real-time check independent of the daily batch job — correct even if
    Celery beat isn't running, since it compares against today's date directly
    rather than trusting a possibly-stale status field."""
    if subscription is None:
        return False
    from django.utils import timezone
    today = timezone.localdate()
    return subscription.end_date >= today or (subscription.grace_ends_at and subscription.grace_ends_at >= today)


def entitlement_snapshot(company):
    """Server-side source of truth for plan limits and module access."""
    subscription = getattr(company, "subscription", None)
    if not subscription:
        return {"usable": False, "modules": [], "limits": {}}
    plan = subscription.plan
    return {
        "usable": is_subscription_usable(subscription),
        "status": subscription.status,
        "read_only": not is_subscription_usable(subscription),
        "modules": list(plan.modules.values_list("code", flat=True)),
        "limits": {
            "users": plan.max_users,
            "warehouses": plan.max_warehouses,
            "invoices_per_month": plan.max_invoices_per_month,
            "storage_mb": plan.storage_limit_mb,
        },
    }


def require_module(company, module_code):
    snapshot = entitlement_snapshot(company)
    if not snapshot["usable"] or module_code not in snapshot["modules"]:
        raise ValidationError(f"Module '{module_code}' is not included in the active plan.")


def enforce_limit(company, resource):
    from apps.tenants.models import CompanyMembership
    from apps.inventory.models import Warehouse
    from apps.sales.models import SalesInvoice
    snapshot = entitlement_snapshot(company)
    limit = snapshot["limits"].get(resource, 0)
    if not limit:
        return
    today = timezone.localdate()
    counts = {
        "users": CompanyMembership.objects.filter(company=company, is_active=True).count(),
        "warehouses": Warehouse.objects.for_company(company).count(),
        "invoices_per_month": SalesInvoice.objects.for_company(company).filter(date__year=today.year, date__month=today.month).count(),
    }
    if counts.get(resource, 0) >= limit:
        raise ValidationError(f"Plan limit reached for {resource} ({limit}).")


@transaction.atomic
def schedule_plan_change(subscription, *, new_plan, effective_on=None):
    """Upgrades immediately; downgrades can be scheduled. No tenant data is deleted."""
    effective_on = effective_on or timezone.localdate()
    is_downgrade = new_plan.max_users < subscription.plan.max_users or new_plan.max_warehouses < subscription.plan.max_warehouses
    if is_downgrade and effective_on > timezone.localdate():
        subscription.downgrade_effective_on = effective_on
        subscription.save(update_fields=["downgrade_effective_on"])
        return subscription
    subscription.plan = new_plan
    subscription.downgrade_effective_on = None
    subscription.save(update_fields=["plan", "downgrade_effective_on"])
    return subscription


@transaction.atomic
def submit_client_payment(subscription, *, amount, method, reference, notes=""):
    """A client reports they've paid (e.g. bank transfer) — logged as
    unconfirmed until a platform admin approves it. Does NOT touch the
    subscription's dates/status yet."""
    from .models import SubscriptionPayment
    return SubscriptionPayment.objects.create(
        subscription=subscription, amount=amount, paid_on=timezone.localdate(),
        method=method, reference=reference, notes=notes, submitted_by_client=True, is_confirmed=False,
    )


@transaction.atomic
def approve_client_payment(payment):
    """Platform admin approves a client-submitted payment: marks it confirmed
    and applies the same renewal effects as an admin-recorded payment."""
    from .models import SubscriptionRenewal

    if payment.is_confirmed:
        return payment.subscription

    subscription = payment.subscription
    previous_end_date = subscription.end_date
    base_date = max(previous_end_date, timezone.localdate())
    days = 365 if subscription.plan.billing_period == "yearly" else 30
    new_end_date = base_date + timedelta(days=days)

    subscription.end_date = new_end_date
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])

    payment.is_confirmed = True
    payment.save(update_fields=["is_confirmed"])

    SubscriptionRenewal.objects.create(
        subscription=subscription, previous_end_date=previous_end_date, new_end_date=new_end_date,
    )
    return subscription


def start_trial_subscription(company, plan=None):
    """Called once at company creation. Requires at least one SubscriptionPlan to exist (seeded via Super Admin)."""
    if plan is None:
        plan = SubscriptionPlan.objects.filter(is_active=True).first()
    if not plan:
        return None
    today = timezone.localdate()
    return Subscription.objects.create(
        company=company, plan=plan, start_date=today,
        end_date=today + timedelta(days=TRIAL_DAYS), trial_ends_at=today + timedelta(days=TRIAL_DAYS), status="trial",
    )


@transaction.atomic
def renew_subscription(subscription, *, new_end_date, amount, method="manual", reference=""):
    from .models import SubscriptionPayment, SubscriptionRenewal

    previous_end_date = subscription.end_date
    subscription.end_date = new_end_date
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])

    SubscriptionPayment.objects.create(
        subscription=subscription, amount=amount, paid_on=timezone.localdate(),
        method=method, reference=reference,
    )
    SubscriptionRenewal.objects.create(
        subscription=subscription, previous_end_date=previous_end_date, new_end_date=new_end_date,
    )
    return subscription


def run_daily_expiry_check():
    """
    Called by the Celery beat task (config/celery.py). For each live
    subscription: fire a notification event at the configured day
    thresholds, and flip status to 'expired' once end_date has passed
    (Phase 0 Section 7 / Phase 1 Section 4).
    """
    today = timezone.localdate()
    live = Subscription.objects.filter(status__in=["trial", "active"]).select_related("company")

    for sub in live:
        days_left = (sub.end_date - today).days

        if days_left < 0:
            sub.status = "expired"
            sub.save(update_fields=["status"])
            from apps.notifications.services import notify_subscription_expired
            notify_subscription_expired(sub.company)
            continue

        if days_left in EXPIRY_NOTIFY_THRESHOLDS:
            from apps.notifications.services import notify_subscription_expiring
            notify_subscription_expiring(sub.company, days_left)


@transaction.atomic
def confirm_stripe_payment(subscription, *, amount, reference):
    """A Stripe Checkout session completed successfully — unlike a client's
    manual bank-transfer submission, this is already verified by Stripe, so
    it renews the subscription immediately with no admin approval step."""
    from .models import SubscriptionPayment, SubscriptionRenewal

    previous_end_date = subscription.end_date
    base_date = max(previous_end_date, timezone.localdate())
    days = 365 if subscription.plan.billing_period == "yearly" else 30
    new_end_date = base_date + timedelta(days=days)

    subscription.end_date = new_end_date
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])

    SubscriptionPayment.objects.create(
        subscription=subscription, amount=amount, paid_on=timezone.localdate(),
        method="card", reference=reference, submitted_by_client=True, is_confirmed=True,
    )
    SubscriptionRenewal.objects.create(
        subscription=subscription, previous_end_date=previous_end_date, new_end_date=new_end_date,
    )
    return subscription


@transaction.atomic
def confirm_razorpay_payment(subscription, *, amount, reference):
    """A Razorpay payment (UPI / PhonePe / card) was verified — renews the
    subscription immediately, same as a verified Stripe payment."""
    from .models import SubscriptionPayment, SubscriptionRenewal

    previous_end_date = subscription.end_date
    base_date = max(previous_end_date, timezone.localdate())
    days = 365 if subscription.plan.billing_period == "yearly" else 30
    new_end_date = base_date + timedelta(days=days)

    subscription.end_date = new_end_date
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])

    SubscriptionPayment.objects.create(
        subscription=subscription, amount=amount, paid_on=timezone.localdate(),
        method="razorpay", reference=reference, submitted_by_client=True, is_confirmed=True,
    )
    SubscriptionRenewal.objects.create(
        subscription=subscription, previous_end_date=previous_end_date, new_end_date=new_end_date,
    )
    return subscription

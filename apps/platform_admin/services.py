"""
Every write action here is something an ordinary tenant Owner can NEVER do
(suspend a tenant, edit a plan, extend/cancel any company's subscription) —
that's the whole point of a separate Super Admin surface (Phase 0
Section 24/25). Views in this app must all use IsPlatformAdmin; nothing
here re-checks that, by design — permission is the view layer's job.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone

from apps.tenants.models import Company
from apps.subscriptions.models import Subscription, SubscriptionPlan, SubscriptionPayment, SubscriptionRenewal
from apps.accounts.models import User


def dashboard_stats():
    today = timezone.localdate()
    companies = Company.objects.exclude(is_demo=True)
    subs = Subscription.objects.all()

    revenue = SubscriptionPayment.objects.filter(is_confirmed=True).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    return {
        "total_tenants": companies.count(),
        "active_tenants": companies.filter(is_active=True).count(),
        "suspended_tenants": companies.filter(is_active=False).count(),
        "trial_subscriptions": subs.filter(status="trial").count(),
        "active_subscriptions": subs.filter(status="active").count(),
        "expired_subscriptions": subs.filter(status="expired").count(),
        "expiring_within_7_days": subs.filter(
            status__in=["trial", "active"], end_date__lte=today + timedelta(days=7), end_date__gte=today,
        ).count(),
        "total_users": User.objects.filter(is_platform_admin=False).count(),
        "total_platform_admins": User.objects.filter(is_platform_admin=True).count(),
        "total_revenue": revenue,
        "mrr_ready": list(SubscriptionPlan.objects.values("id", "name", "price", "billing_period")),
        "plan_breakdown": list(
            subs.values("plan__name").annotate(count=Count("id")).order_by("-count")
        ),
    }


def suspend_tenant(company):
    """
    Locks out every user of the company immediately — ActiveCompanyMiddleware
    only resolves memberships where company__is_active=True (Phase 0
    Section 25). Data is preserved, never deleted (Phase 0 Section 42).
    """
    company.is_active = False
    company.save(update_fields=["is_active"])
    return company


def activate_tenant(company):
    company.is_active = True
    company.save(update_fields=["is_active"])
    return company


@transaction.atomic
def extend_subscription(subscription, *, new_end_date, amount=None, reference=""):
    """Super Admin override — bypasses the normal renew_subscription payment flow for manual/offline renewals."""
    subscription_previous_end = subscription.end_date
    subscription.end_date = new_end_date
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])

    if amount is not None:
        SubscriptionPayment.objects.create(
            subscription=subscription, amount=amount, paid_on=timezone.localdate(),
            method="manual_admin", reference=reference,
        )
    SubscriptionRenewal.objects.create(
        subscription=subscription, previous_end_date=subscription_previous_end, new_end_date=new_end_date,
    )
    return subscription


def cancel_subscription(subscription):
    subscription.status = "cancelled"
    subscription.save(update_fields=["status"])
    return subscription

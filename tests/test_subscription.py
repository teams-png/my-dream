"""Phase 1 Section 38: 'Subscription limits', 'Subscription expiry'."""
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.subscriptions.services import run_daily_expiry_check
from apps.tenants.services import invite_member

pytestmark = pytest.mark.django_db


def test_new_company_gets_a_trial_subscription(make_company):
    company, owner = make_company("textile")
    assert company.subscription.status == "trial"
    assert company.subscription.days_remaining() > 0


def test_inviting_beyond_max_users_is_rejected(make_company):
    """Section 5: 'Maximum users: 1/3/10' must actually be enforced, not just stored on the plan."""
    from tests.conftest import make_user

    company, owner = make_company("textile", owner_email="limit-owner@example.com")
    company.subscription.plan.max_users = 1  # owner alone already fills the plan
    company.subscription.plan.save(update_fields=["max_users"])

    second_user = make_user("second-user@example.com")
    with pytest.raises(ValidationError):
        invite_member(company=company, user=second_user, role_name="Staff")


def test_inviting_within_max_users_succeeds(make_company):
    from tests.conftest import make_user

    company, owner = make_company("textile", owner_email="within-limit-owner@example.com")
    company.subscription.plan.max_users = 3
    company.subscription.plan.save(update_fields=["max_users"])

    staff = make_user("within-limit-staff@example.com")
    membership = invite_member(company=company, user=staff, role_name="Staff")
    assert membership.company_id == company.id
    assert membership.role.name == "Staff"


def test_expired_subscription_is_flagged_by_the_daily_check(make_company):
    company, owner = make_company("textile", owner_email="expired-owner@example.com")
    sub = company.subscription
    sub.end_date = timezone.localdate() - timedelta(days=1)
    sub.save(update_fields=["end_date"])

    run_daily_expiry_check()

    sub.refresh_from_db()
    assert sub.status == "expired"


def test_active_subscription_not_yet_due_stays_untouched(make_company):
    company, owner = make_company("textile", owner_email="active-owner@example.com")
    sub = company.subscription
    original_status = sub.status

    run_daily_expiry_check()

    sub.refresh_from_db()
    assert sub.status == original_status

"""
Subscription tests (master brief Section 5 "Do NOT hard-code the plans" /
Section 6 "yearly subscription" / Section 7 "before/after expiry
behaviour").
"""
from datetime import timedelta

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


class TestUserLimit:
    def test_invite_member_enforces_plan_max_users(self, tenant_a, user_factory):
        """starter_plan fixture sets max_users=2. The owner's login is free,
        so two invites succeed and the next must fail with a clear error,
        not a silent no-op (Section 7)."""
        from apps.tenants.models import Role
        from apps.tenants.services import invite_member

        staff_role = Role.objects.get(company=tenant_a, name="Staff")

        invite_member(company=tenant_a, user=user_factory(), role=staff_role)
        invite_member(company=tenant_a, user=user_factory(), role=staff_role)  # owner + 2 — at the limit
        # re-inviting someone already in doesn't take another place
        accountant = Role.objects.get(company=tenant_a, name="Accountant")
        member = tenant_a.memberships.exclude(role__name="Owner").first().user
        invite_member(company=tenant_a, user=member, role=accountant)

        third_user = user_factory()
        with pytest.raises(ValueError, match="owner plus 2 more users"):
            invite_member(company=tenant_a, user=third_user, role=staff_role)

    def test_invite_endpoint_returns_402_once_limit_reached(
        self, as_tenant_a_owner, tenant_a, user_factory
    ):
        from apps.tenants.models import Role

        staff_role = Role.objects.get(company=tenant_a, name="Staff")
        user_factory(email="second@example.com")  # not yet a member — will invite via API
        second = user_factory(email="already-second@example.com")

        from apps.tenants.services import invite_member
        invite_member(company=tenant_a, user=second, role=staff_role)
        invite_member(company=tenant_a, user=user_factory(), role=staff_role)  # owner + 2 fills the 2-user plan

        third = user_factory(email="third@example.com")
        resp = as_tenant_a_owner.post(
            "/api/tenants/members/", {"user_id": third.id, "role_id": staff_role.id}, format="json"
        )
        assert resp.status_code == 402


class TestSubscriptionExpiry:
    def test_new_company_starts_on_a_trial(self, tenant_a):
        assert tenant_a.subscription.status == "trial"
        assert tenant_a.subscription.days_remaining() > 0

    def test_expiry_check_flips_status_and_notifies(self, tenant_a):
        from apps.subscriptions.services import run_daily_expiry_check
        from apps.notifications.models import Notification

        sub = tenant_a.subscription
        sub.end_date = timezone.localdate() - timedelta(days=1)  # already past due
        sub.save(update_fields=["end_date"])

        run_daily_expiry_check()

        sub.refresh_from_db()
        assert sub.status == "expired"
        assert Notification.objects.filter(company=tenant_a, notif_type="subscription_expired").exists()

    def test_expiry_check_fires_threshold_notifications_without_expiring_early(self, tenant_a):
        from apps.subscriptions.services import run_daily_expiry_check
        from apps.notifications.models import Notification

        sub = tenant_a.subscription
        sub.end_date = timezone.localdate() + timedelta(days=7)  # exactly one threshold
        sub.save(update_fields=["end_date"])

        run_daily_expiry_check()

        sub.refresh_from_db()
        assert sub.status == "trial"  # not expired — still 7 days left
        assert Notification.objects.filter(company=tenant_a, notif_type="subscription_expiring").exists()

    def test_expired_company_blocks_non_owner_routes(self, tenant_a, member_factory):
        """SubscriptionGuardMiddleware (Phase 0 Section 7): once expired,
        every route except billing/admin/accounts is blocked for non-Owner
        roles, with a clear 402, not a silent empty result."""
        from conftest import jwt_client

        sub = tenant_a.subscription
        sub.status = "expired"
        sub.save(update_fields=["status"])

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        resp = client.get("/api/customers/")
        assert resp.status_code == 402

    def test_expired_company_still_lets_owner_reach_billing(self, tenant_a, as_tenant_a_owner):
        sub = tenant_a.subscription
        sub.status = "expired"
        sub.save(update_fields=["status"])

        # Owner must still be able to view their own subscription to renew it.
        resp = as_tenant_a_owner.get("/api/subscriptions/me/")
        assert resp.status_code == 200

    def test_renew_subscription_extends_end_date_and_reactivates(self, tenant_a):
        from decimal import Decimal
        from apps.subscriptions.services import renew_subscription

        sub = tenant_a.subscription
        sub.status = "expired"
        sub.save(update_fields=["status"])

        new_end = timezone.localdate() + timedelta(days=365)
        renew_subscription(sub, new_end_date=new_end, amount=Decimal("499.00"), reference="TEST-REF")

        sub.refresh_from_db()
        assert sub.status == "active"
        assert sub.end_date == new_end
        assert sub.renewals.count() == 1
        assert sub.payments.count() == 1

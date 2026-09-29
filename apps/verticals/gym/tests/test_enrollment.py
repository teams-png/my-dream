"""
Gym enrollment tests — closes the MembershipPlan <-> Product linkage
flagged as a TODO since apps/verticals/gym/services.py was first written
(Phase 3) and left open through Phase 21: enroll_member() must invoice the
member before creating the GymMember row, matching the "never shortcut
the accounting engine" rule (master brief Section 41 / Phase 0 Section 18)
that every other vertical follows.
"""
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def gym_fixtures(tenant_a):
    from apps.inventory.models import Warehouse
    from apps.customers.models import Customer

    warehouse = Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)
    customer = Customer.objects.create(company=tenant_a, name="Walk-in Member")
    return {"warehouse": warehouse, "customer": customer}


class TestCreateMembershipPlan:
    def test_creates_plan_with_a_linked_service_product(self, tenant_a):
        from apps.verticals.gym.services import create_membership_plan

        plan = create_membership_plan(company=tenant_a, name="Monthly", duration_days=30, price=Decimal("150"))

        assert plan.product is not None
        assert plan.product.company_id == tenant_a.id
        assert plan.product.selling_price == Decimal("150")
        assert plan.product.reorder_level == 0


class TestEnrollMember:
    def test_enrollment_creates_an_invoice_before_the_member(self, tenant_a, tenant_a_owner, gym_fixtures):
        from apps.verticals.gym.services import create_membership_plan, enroll_member
        from apps.sales.models import SalesInvoice

        plan = create_membership_plan(company=tenant_a, name="Monthly", duration_days=30, price=Decimal("150"))
        assert SalesInvoice.objects.for_company(tenant_a).count() == 0

        member = enroll_member(
            company=tenant_a, user=tenant_a_owner, customer=gym_fixtures["customer"],
            membership_plan=plan, join_date="2026-01-01", warehouse=gym_fixtures["warehouse"],
        )

        invoices = SalesInvoice.objects.for_company(tenant_a)
        assert invoices.count() == 1
        assert invoices.first().total == Decimal("150.00")
        assert member.status == "active"
        assert member.membership_end == date(2026, 1, 31)

    def test_enrollment_posts_a_balanced_journal_entry(self, tenant_a, tenant_a_owner, gym_fixtures):
        """The whole point of routing through sales.services.create_invoice: a gym
        enrollment must show up in the ledger like any other sale."""
        from apps.verticals.gym.services import create_membership_plan, enroll_member
        from apps.sales.models import SalesInvoice

        plan = create_membership_plan(company=tenant_a, name="Monthly", duration_days=30, price=Decimal("150"))
        enroll_member(
            company=tenant_a, user=tenant_a_owner, customer=gym_fixtures["customer"],
            membership_plan=plan, join_date="2026-01-01", warehouse=gym_fixtures["warehouse"],
        )

        invoice = SalesInvoice.objects.for_company(tenant_a).get()
        je = invoice.journal_entry
        assert je is not None
        debit_total = sum(l.debit for l in je.lines.all())
        credit_total = sum(l.credit for l in je.lines.all())
        assert debit_total == credit_total == Decimal("150.00")

    def test_enrollment_without_linked_product_is_rejected(self, tenant_a, tenant_a_owner, gym_fixtures):
        """A MembershipPlan created directly via the ORM (bypassing create_membership_plan)
        has no product — enroll_member must refuse rather than silently skip invoicing."""
        from apps.verticals.gym.models import MembershipPlan
        from apps.verticals.gym.services import enroll_member

        plan = MembershipPlan.objects.create(company=tenant_a, name="Legacy Plan", duration_days=30, price=Decimal("100"))

        with pytest.raises(ValueError):
            enroll_member(
                company=tenant_a, user=tenant_a_owner, customer=gym_fixtures["customer"],
                membership_plan=plan, join_date="2026-01-01", warehouse=gym_fixtures["warehouse"],
            )

    def test_failed_invoice_leaves_no_gym_member(self, tenant_a, tenant_a_owner, gym_fixtures, monkeypatch):
        """Same atomicity guarantee as sales.create_invoice itself
        (apps/sales/tests/test_invoice_flow.py::TestInvoiceAtomicity):
        if the invoice step fails, no GymMember should be left behind."""
        from apps.verticals.gym import services as gym_services
        from apps.verticals.gym.models import GymMember

        plan = gym_services.create_membership_plan(company=tenant_a, name="Monthly", duration_days=30, price=Decimal("150"))

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated invoice failure")

        monkeypatch.setattr(gym_services, "create_invoice", _boom)

        with pytest.raises(RuntimeError):
            gym_services.enroll_member(
                company=tenant_a, user=tenant_a_owner, customer=gym_fixtures["customer"],
                membership_plan=plan, join_date="2026-01-01", warehouse=gym_fixtures["warehouse"],
            )

        assert GymMember.objects.for_company(tenant_a).count() == 0

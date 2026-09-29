"""
This is the proof-of-concept for the vertical-module pattern (Phase 0
Section 8 / Phase 1 Section 12): a gym enrollment is money changing hands,
so it goes through sales.services.create_invoice() like any other sale —
it does NOT write directly to a revenue account. Every other vertical
copies this shape.

The MembershipPlan <-> Product linkage flagged as a TODO through Phase 21
is resolved here: create_membership_plan() creates both atomically, and
enroll_member() invoices against the linked product before creating the
GymMember row, so a member is never marked active without a real invoice
behind it.

Membership products are created with `is_stock_tracked=False`, so service
invoices post revenue without creating meaningless stock movements.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from .models import GymMember, MembershipPlan
from apps.sales.services import create_invoice


@transaction.atomic
def create_membership_plan(*, company, name, duration_days, price, category=None, unit=None):
    """
    Creates the MembershipPlan's linked service Product in the same
    transaction, so a plan is never left without one. `category`/`unit`
    are optional inventory.ProductCategory/Unit — pass existing ones if
    the company already has a "Membership" category/unit convention;
    otherwise a bare Unit named "membership" is created/reused.
    """
    from apps.inventory.models import Product, Unit

    if unit is None:
        unit, _ = Unit.objects.get_or_create(company=company, name="membership")

    product = Product.objects.create(
        company=company, sku=f"GYM-PLAN-{name.upper().replace(' ', '-')}", name=f"Gym Membership — {name}",
        category=category, unit=unit, cost_price=Decimal("0"), selling_price=price,
        reorder_level=0, is_active=True, is_stock_tracked=False,
    )
    return MembershipPlan.objects.create(
        company=company, name=name, duration_days=duration_days, price=price, product=product,
    )


@transaction.atomic
def enroll_member(*, company, user, customer, membership_plan, join_date, warehouse):
    """
    Invoices the member for the plan's price against its linked service
    Product, then creates the GymMember row only after the invoice
    succeeds (transaction.atomic means a failed invoice rolls back the
    whole enrollment — no member is ever created without payment behind
    it, matching the rule every other vertical follows: never shortcut
    the accounting engine, Phase 0 Section 18).
    """
    if isinstance(join_date, str):
        # create_invoice hands its `date` straight to Django's ORM, which parses ISO
        # strings itself — but membership_end below does raw Python `date + timedelta`
        # arithmetic before that ever happens, so a string has to become a real date first.
        join_date = date.fromisoformat(join_date)

    if membership_plan.product_id is None:
        raise ValueError(
            "This MembershipPlan has no linked Product — create plans via "
            "gym.services.create_membership_plan() so enrollment can invoice correctly."
        )

    create_invoice(
        company=company, user=user, customer=customer, date=join_date, warehouse=warehouse,
        lines=[{"product": membership_plan.product, "quantity": Decimal("1"), "unit_price": membership_plan.price}],
    )

    member = GymMember.objects.create(
        company=company, customer=customer, membership_plan=membership_plan,
        join_date=join_date, membership_start=join_date,
        membership_end=join_date + timedelta(days=membership_plan.duration_days),
        status="active",
    )
    return member


@transaction.atomic
def renew_member(*, company, user, member, membership_plan, start_date, warehouse):
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if member.company_id != company.id or membership_plan.company_id != company.id:
        raise ValueError("Member or plan does not belong to this company.")
    if membership_plan.product_id is None:
        raise ValueError("This membership plan has no linked billing product.")
    invoice = create_invoice(
        company=company, user=user, customer=member.customer, date=start_date, warehouse=warehouse,
        lines=[{"product": membership_plan.product, "quantity": Decimal("1"), "unit_price": membership_plan.price}],
    )
    member.membership_plan = membership_plan
    member.membership_start = start_date
    member.membership_end = start_date + timedelta(days=membership_plan.duration_days)
    member.status = "active"
    member.save(update_fields=["membership_plan", "membership_start", "membership_end", "status"])
    return member, invoice

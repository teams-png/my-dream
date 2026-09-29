from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.customers.models import LoyaltyAccount
from apps.inventory.services import record_stock_movement
from apps.sales.models import CommercialSettings, PriceList, PriceListItem, Promotion
from apps.sales.services import create_invoice, complete_pos_sale, open_pos_shift, resolve_commercial_price


pytestmark = pytest.mark.django_db


def test_price_precedence_is_deterministic(tenant_a, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    general = PriceList.objects.create(company=tenant_a, name="Retail", priority=100)
    PriceListItem.objects.create(price_list=general, product=d["product"], unit_price=Decimal("90"))
    customer = PriceList.objects.create(company=tenant_a, name="VIP", customer=d["customer"], priority=1)
    PriceListItem.objects.create(price_list=customer, product=d["product"], unit_price=Decimal("80"))
    Promotion.objects.create(
        company=tenant_a, name="Ten percent", product=d["product"], discount_type="percentage",
        discount_value=10, priority=5, start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=1),
    )
    price, source, promotion = resolve_commercial_price(
        company=tenant_a, customer=d["customer"], product=d["product"], date=date.today(),
    )
    assert price == Decimal("72.00")
    assert source == "customer_price_list+promotion"
    assert promotion.name == "Ten percent"


def test_inactive_and_expired_rules_are_ignored(tenant_a, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    old = PriceList.objects.create(
        company=tenant_a, name="Old", end_date=date.today() - timedelta(days=1), priority=999,
    )
    PriceListItem.objects.create(price_list=old, product=d["product"], unit_price=1)
    price, source, promotion = resolve_commercial_price(
        company=tenant_a, customer=d["customer"], product=d["product"], date=date.today(),
    )
    assert price == Decimal("100.00")
    assert source == "product"
    assert promotion is None


def test_large_manual_discount_requires_approval(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    CommercialSettings.objects.create(company=tenant_a, discount_approval_threshold_percent=10)
    kwargs = dict(
        company=tenant_a, user=tenant_a_owner, customer=d["customer"], date=date.today(),
        warehouse=d["warehouse"], lines=[{"product": d["product"], "quantity": 1, "unit_price": 100}],
        discount_amount=20, discount_reason="Manager offer",
    )
    with pytest.raises(ValidationError, match="approval threshold"):
        create_invoice(**kwargs)
    invoice = create_invoice(**kwargs, discount_approved_by=tenant_a_owner)
    assert invoice.discount_approved_by == tenant_a_owner
    assert invoice.total == Decimal("80")


def test_pos_pricing_and_loyalty_end_to_end(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    record_stock_movement(company=tenant_a, product=d["product"], warehouse=d["warehouse"],
                          quantity=10, reason="adjustment", reference="opening")
    CommercialSettings.objects.create(
        company=tenant_a, loyalty_spend_per_point=Decimal("10"),
        loyalty_currency_per_point=Decimal("1"),
    )
    account = LoyaltyAccount.objects.create(company=tenant_a, customer=d["customer"], points_balance=10)
    price_list = PriceList.objects.create(company=tenant_a, name="VIP", customer=d["customer"])
    PriceListItem.objects.create(price_list=price_list, product=d["product"], unit_price=80)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=d["warehouse"])
    receipt = complete_pos_sale(
        company=tenant_a, user=tenant_a_owner, shift=shift, customer=d["customer"], date=date.today(),
        lines=[{"product": d["product"], "quantity": 1, "unit_price": 999}],
        payments=[{"method": "cash", "amount": 75}], loyalty_points=5,
    )
    account.refresh_from_db()
    # Redeems 5, then earns 7 from the QAR 75 financial sale.
    assert account.points_balance == 12
    assert receipt.invoice.lines.get().unit_price == Decimal("80")
    assert receipt.invoice.discount_amount == Decimal("5")
    assert receipt.invoice.total == Decimal("75")

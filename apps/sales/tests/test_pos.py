from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import JournalEntry
from apps.inventory.services import record_stock_movement
from apps.sales.models import POSCart, POSPayment
from apps.sales.services import (
    add_pos_cash_movement,
    close_pos_shift,
    complete_pos_sale,
    hold_pos_cart,
    open_pos_shift,
)


pytestmark = pytest.mark.django_db


def _stock(company, data, quantity=Decimal("10")):
    record_stock_movement(
        company=company, product=data["product"], warehouse=data["warehouse"],
        quantity=quantity, reason="adjustment", reference="opening",
    )


def test_pos_sale_posts_one_invoice_and_split_payment(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"], opening_cash=50)
    receipt = complete_pos_sale(
        company=tenant_a, user=tenant_a_owner, shift=shift, customer=data["customer"],
        date=date.today(),
        lines=[{"product": data["product"], "quantity": Decimal("2"), "unit_price": Decimal("100")}],
        payments=[{"method": "cash", "amount": Decimal("80")}, {"method": "card", "amount": Decimal("120")}],
    )
    receipt.invoice.refresh_from_db()
    assert receipt.invoice.total == Decimal("200")
    assert receipt.invoice.amount_paid == Decimal("200")
    assert receipt.invoice.status == "paid"
    assert POSPayment.objects.filter(receipt=receipt).count() == 2
    assert JournalEntry.objects.for_company(tenant_a).filter(source_type="sales_invoice").count() == 1
    assert data["product"].current_stock(data["warehouse"]) == Decimal("8")


def test_held_cart_does_not_post_stock_or_accounting(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"])
    before = JournalEntry.objects.for_company(tenant_a).count()
    cart = hold_pos_cart(
        company=tenant_a, user=tenant_a_owner, shift=shift,
        lines=[{"product": data["product"], "quantity": 2, "unit_price": 100}],
    )
    assert cart.status == "held"
    assert data["product"].current_stock(data["warehouse"]) == Decimal("10")
    assert JournalEntry.objects.for_company(tenant_a).count() == before


def test_resume_held_cart_marks_completed(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"])
    cart = hold_pos_cart(
        company=tenant_a, user=tenant_a_owner, shift=shift,
        lines=[{"product": data["product"], "quantity": 1, "unit_price": 100}],
    )
    receipt = complete_pos_sale(
        company=tenant_a, user=tenant_a_owner, shift=shift, cart=cart, lines=[],
        payments=[{"method": "cash", "amount": 100}], date=date.today(),
    )
    cart.refresh_from_db()
    assert cart.status == "completed"
    assert receipt.cart_id == cart.id


def test_pos_blocks_overselling(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data, Decimal("1"))
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"])
    with pytest.raises(ValidationError, match="Insufficient stock"):
        complete_pos_sale(
            company=tenant_a, user=tenant_a_owner, shift=shift, date=date.today(),
            lines=[{"product": data["product"], "quantity": 2, "unit_price": 100}],
            payments=[{"method": "cash", "amount": 200}],
        )


def test_shift_cash_variance(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"], opening_cash=50)
    complete_pos_sale(
        company=tenant_a, user=tenant_a_owner, shift=shift, date=date.today(),
        lines=[{"product": data["product"], "quantity": 1, "unit_price": 100}],
        payments=[{"method": "cash", "amount": 100}],
    )
    add_pos_cash_movement(company=tenant_a, user=tenant_a_owner, shift=shift,
                          kind="cash_in", amount=20, reason="Float top-up")
    add_pos_cash_movement(company=tenant_a, user=tenant_a_owner, shift=shift,
                          kind="cash_out", amount=10, reason="Petty cash")
    close_pos_shift(company=tenant_a, user=tenant_a_owner, shift=shift, counted_cash=165)
    shift.refresh_from_db()
    assert shift.expected_cash == Decimal("160")
    assert shift.variance == Decimal("5")


def test_wrong_split_total_rolls_back_everything(tenant_a, tenant_a_owner, sales_fixtures_factory):
    data = sales_fixtures_factory(tenant_a)
    _stock(tenant_a, data)
    shift = open_pos_shift(company=tenant_a, user=tenant_a_owner, warehouse=data["warehouse"])
    with pytest.raises(ValidationError, match="must equal"):
        complete_pos_sale(
            company=tenant_a, user=tenant_a_owner, shift=shift, date=date.today(),
            lines=[{"product": data["product"], "quantity": 1, "unit_price": 100}],
            payments=[{"method": "cash", "amount": 90}],
        )
    assert data["product"].current_stock(data["warehouse"]) == Decimal("10")
    assert POSCart.objects.for_company(tenant_a).count() == 0

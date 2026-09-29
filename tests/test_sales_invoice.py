"""Phase 1 Section 38: 'Sales', 'Inventory', 'Invoice generation', 'Payment status'."""
from decimal import Decimal

import pytest

from apps.customers.models import Customer
from apps.inventory.models import Product, Unit, Warehouse
from apps.inventory.services import record_stock_movement
from apps.sales.services import create_invoice, record_customer_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def sales_fixtures(make_company):
    company, owner = make_company("textile", owner_email="sales-owner@example.com")
    unit = Unit.objects.create(company=company, name="pcs")
    warehouse = Warehouse.objects.create(company=company, name="Main Store", is_default=True)
    product = Product.objects.create(
        company=company, sku="SKU-001", name="Test Product", unit=unit,
        cost_price=Decimal("50.00"), selling_price=Decimal("100.00"),
    )
    customer = Customer.objects.create(company=company, name="Walk-in Customer")
    # stock on hand before the sale
    record_stock_movement(company=company, product=product, warehouse=warehouse, quantity=Decimal("10"), reason="opening_stock")
    return company, owner, product, warehouse, customer


def test_create_invoice_totals_are_correct(sales_fixtures):
    company, owner, product, warehouse, customer = sales_fixtures

    invoice = create_invoice(
        company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse,
        lines=[{"product": product, "quantity": Decimal("2"), "unit_price": Decimal("100.00")}],
        tax_rate=Decimal("0.05"),
    )
    assert invoice.subtotal == Decimal("200.00")
    assert invoice.tax_amount == Decimal("10.00")
    assert invoice.total == Decimal("210.00")
    assert invoice.status == "unpaid"


def test_create_invoice_reduces_stock(sales_fixtures):
    from apps.inventory.models import StockMovement

    company, owner, product, warehouse, customer = sales_fixtures

    create_invoice(
        company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse,
        lines=[{"product": product, "quantity": Decimal("3"), "unit_price": Decimal("100.00")}],
    )
    movements = StockMovement.objects.for_company(company).filter(product=product, reason="sale")
    assert movements.count() == 1
    assert movements.first().quantity == Decimal("-3")


def test_create_invoice_posts_a_balanced_journal_entry(sales_fixtures):
    company, owner, product, warehouse, customer = sales_fixtures

    invoice = create_invoice(
        company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse,
        lines=[{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100.00")}],
    )
    entry = invoice.journal_entry
    assert entry is not None
    total_debit = sum(l.debit for l in entry.lines.all())
    total_credit = sum(l.credit for l in entry.lines.all())
    assert total_debit == total_credit == Decimal("100.00")


def test_invoice_creates_no_lines_is_rejected(sales_fixtures):
    from django.core.exceptions import ValidationError

    company, owner, product, warehouse, customer = sales_fixtures
    with pytest.raises(ValidationError):
        create_invoice(company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse, lines=[])


def test_full_payment_marks_invoice_paid(sales_fixtures):
    company, owner, product, warehouse, customer = sales_fixtures

    invoice = create_invoice(
        company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse,
        lines=[{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100.00")}],
    )
    record_customer_payment(
        company=company, user=owner, customer=customer,
        amount=Decimal("100.00"), date="2026-09-09", invoice=invoice,
    )
    invoice.refresh_from_db()
    assert invoice.status == "paid"
    assert invoice.amount_paid == Decimal("100.00")


def test_partial_payment_marks_invoice_partial(sales_fixtures):
    company, owner, product, warehouse, customer = sales_fixtures

    invoice = create_invoice(
        company=company, user=owner, customer=customer, date="2026-09-09", warehouse=warehouse,
        lines=[{"product": product, "quantity": Decimal("2"), "unit_price": Decimal("100.00")}],
    )
    record_customer_payment(
        company=company, user=owner, customer=customer,
        amount=Decimal("50.00"), date="2026-09-09", invoice=invoice,
    )
    invoice.refresh_from_db()
    assert invoice.status == "partial"
    assert invoice.amount_paid == Decimal("50.00")

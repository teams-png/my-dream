from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import JournalLine
from apps.sales.models import ExchangeRate
from apps.sales.services import create_invoice, record_customer_payment


pytestmark = pytest.mark.django_db


def _invoice(company, user, d, **extra):
    return create_invoice(
        company=company, user=user, customer=d["customer"], date=date.today(),
        warehouse=d["warehouse"],
        lines=[{"product": d["product"], "quantity": 2, "unit_price": Decimal("10")}],
        **extra,
    )


def test_foreign_invoice_posts_base_currency(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    ExchangeRate.objects.create(company=tenant_a, currency="USD", effective_date=date.today(), rate=Decimal("3.64"), source="manual")
    invoice = _invoice(tenant_a, tenant_a_owner, d, currency="USD")
    assert invoice.transaction_total == Decimal("20")
    assert invoice.total == Decimal("72.80")
    lines = invoice.journal_entry.lines.all()
    assert sum(x.debit for x in lines) == Decimal("72.80")
    assert sum(x.credit for x in lines) == Decimal("72.80")


def test_settlement_posts_realized_exchange_gain(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    ExchangeRate.objects.create(company=tenant_a, currency="USD", effective_date=date.today(), rate=Decimal("3.60"))
    invoice = _invoice(tenant_a, tenant_a_owner, d, currency="USD")
    payment = record_customer_payment(
        company=tenant_a, user=tenant_a_owner, customer=d["customer"], invoice=invoice,
        amount=Decimal("20"), date=date.today() + timedelta(days=1), method="bank",
        currency="USD", exchange_rate=Decimal("3.70"),
    )
    invoice.refresh_from_db()
    gain = JournalLine.objects.filter(journal_entry=payment.journal_entry, account__code="4050").get()
    assert gain.credit == Decimal("2.00")
    assert invoice.status == "paid"
    assert invoice.transaction_amount_paid == Decimal("20")


def test_base_currency_flow_is_unchanged(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    invoice = _invoice(tenant_a, tenant_a_owner, d)
    payment = record_customer_payment(
        company=tenant_a, user=tenant_a_owner, customer=d["customer"], invoice=invoice,
        amount=Decimal("20"), date=date.today(), method="cash",
    )
    assert invoice.currency == tenant_a.default_currency
    assert invoice.exchange_rate == Decimal("1")
    assert payment.base_amount == Decimal("20")
    assert not payment.journal_entry.lines.filter(account__code__in=["4050", "5150"]).exists()


def test_missing_foreign_rate_is_rejected(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    with pytest.raises(ValidationError, match="No exchange rate"):
        _invoice(tenant_a, tenant_a_owner, d, currency="EUR")

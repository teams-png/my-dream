from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.reports.services import tax_report
from apps.sales.models import TaxScheme, TaxCode
from apps.sales.services import calculate_tax, create_invoice, process_return


pytestmark = pytest.mark.django_db


def _code(company, **overrides):
    scheme = TaxScheme.objects.create(company=company, name="Configurable VAT")
    values = dict(company=company, scheme=scheme, code="STD", name="Standard", rate=Decimal("5"),
                  inclusive=False, classification="taxable", effective_from=date.today())
    values.update(overrides)
    return TaxCode.objects.create(**values)


def test_exact_inclusive_and_exclusive_calculation(tenant_a):
    exclusive = _code(tenant_a)
    taxable, tax = calculate_tax(amount=Decimal("100"), tax_code=exclusive, date=date.today())
    assert (taxable, tax) == (Decimal("100.00"), Decimal("5.00"))
    exclusive.scheme.delete()
    inclusive = _code(tenant_a, code="INC", inclusive=True)
    taxable, tax = calculate_tax(amount=Decimal("105"), tax_code=inclusive, date=date.today())
    assert (taxable, tax) == (Decimal("100.00"), Decimal("5.00"))


def test_zero_and_exempt_codes_charge_no_tax(tenant_a):
    zero = _code(tenant_a, classification="zero_rated", rate=0)
    assert calculate_tax(amount=100, tax_code=zero, date=date.today()) == (Decimal("100.00"), Decimal("0"))


def test_expired_tax_code_is_rejected(tenant_a):
    code = _code(tenant_a, effective_to=date.today() - timedelta(days=1))
    with pytest.raises(ValidationError, match="not effective"):
        calculate_tax(amount=100, tax_code=code, date=date.today())


def test_invoice_return_reverses_original_tax_and_report_reconciles(tenant_a, tenant_a_owner, sales_fixtures_factory):
    d = sales_fixtures_factory(tenant_a)
    d["product"].is_stock_tracked = False
    d["product"].save(update_fields=["is_stock_tracked"])
    code = _code(tenant_a)
    invoice = create_invoice(
        company=tenant_a, user=tenant_a_owner, customer=d["customer"], date=date.today(),
        warehouse=d["warehouse"],
        lines=[{"product": d["product"], "quantity": 2, "unit_price": 100, "tax_code": code}],
    )
    assert invoice.subtotal == Decimal("200.00")
    assert invoice.tax_amount == Decimal("10.00")
    returned = process_return(
        company=tenant_a, user=tenant_a_owner, invoice=invoice, date=date.today(),
        warehouse=d["warehouse"], lines=[{"product": d["product"], "quantity": 1, "unit_price": 100}],
    )
    assert returned.total == Decimal("105.00")
    tax_debit = returned.journal_entry.lines.get(account__code="2100")
    assert tax_debit.debit == Decimal("5.00")
    report = tax_report(tenant_a, date.today(), date.today())
    assert report["tax_collected"] == Decimal("10.00")
    assert report["sales_by_tax_code"][0]["tax_code__code"] == "STD"

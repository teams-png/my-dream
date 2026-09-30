from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.collections.models import CollectionNote
from apps.customers.models import Customer
from apps.inventory.models import Product
from apps.inventory.services import record_stock_movement
from apps.sales import services as sales
from apps.sales.models import CustomerPayment, SalesInvoice

pytestmark = pytest.mark.django_db


@pytest.fixture
def books(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="RICE", stock_price=Decimal("100"))
    record_stock_movement(company=tenant_a, product=base["product"], warehouse=base["warehouse"], quantity=100, reason="purchase")
    ali = Customer.objects.create(company=tenant_a, name="Ali Traders", phone="+974 5555 1212", payment_terms_days=15)
    today = date.today()

    def invoice(days_ago, qty):
        return sales.create_invoice(company=tenant_a, user=tenant_a_owner, customer=ali, date=today - timedelta(days=days_ago),
                                    lines=[{"product": base["product"], "quantity": Decimal(qty), "unit_price": Decimal("100")}],
                                    warehouse=base["warehouse"])
    old, new = invoice(50, 3), invoice(2, 2)
    client.force_login(tenant_a_owner)
    return {"client": client, "company": tenant_a, "ali": ali, "old": old, "new": new}


def test_overview_shows_ageing_and_customer(books):
    page = books["client"].get(reverse("webapp:receivables"))
    assert page.status_code == 200
    assert page.context["summary"]["total_outstanding"] == Decimal("500")
    row = next(r for r in page.context["rows"] if r["customer"] == books["ali"])
    assert row["overdue"] == Decimal("300") and row["balance"] == Decimal("500")
    assert books["client"].get(reverse("webapp:receivables"), {"show": "overdue"}).context["rows"]


def test_payment_goes_to_oldest_bill_first_and_extra_is_kept_on_account(books):
    client, ali = books["client"], books["ali"]
    client.post(reverse("webapp:receive_payment", args=[ali.id]), {"amount": "350", "method": "cash", "date": date.today().isoformat()})
    old, new = SalesInvoice.objects.get(pk=books["old"].pk), SalesInvoice.objects.get(pk=books["new"].pk)
    assert old.status == "paid" and new.amount_paid == Decimal("50") and new.status == "partial"
    client.post(reverse("webapp:receive_payment", args=[ali.id]), {"amount": "200", "method": "bank"})
    new.refresh_from_db()
    assert new.status == "paid"
    assert CustomerPayment.objects.filter(customer=ali, invoice__isnull=True, amount=Decimal("50")).exists()
    account = client.get(reverse("webapp:customer_account", args=[ali.id]))
    assert account.context["balance"] == Decimal("-50") and account.context["closing"] == Decimal("-50")
    assert not account.context["open_invoices"]


def test_pay_one_chosen_bill_and_reject_bad_amounts(books):
    client, ali = books["client"], books["ali"]
    client.post(reverse("webapp:receive_payment", args=[ali.id]), {"amount": "200", "method": "card", "invoice": books["new"].id})
    assert SalesInvoice.objects.get(pk=books["new"].pk).status == "paid"
    assert SalesInvoice.objects.get(pk=books["old"].pk).status != "paid"
    client.post(reverse("webapp:receive_payment", args=[ali.id]), {"amount": "0", "method": "cash"})
    assert CustomerPayment.objects.filter(customer=ali).count() == 1


def test_statement_reminder_and_notes(books):
    client, ali = books["client"], books["ali"]
    page = client.get(reverse("webapp:customer_account", args=[ali.id]))
    assert [l["debit"] for l in page.context["lines"]] == [Decimal("300"), Decimal("200")]
    assert "wa.me/97455551212" in page.context["reminder"]
    client.post(reverse("webapp:customer_account", args=[ali.id]),
                {"action": "note", "note": "Will pay Thursday", "follow_up": date.today().isoformat()})
    assert CollectionNote.objects.filter(customer=ali).exists()
    assert client.get(reverse("webapp:receivables")).context["notes_due"]
    client.post(reverse("webapp:customer_account", args=[ali.id]), {"action": "credit_limit", "credit_limit": "400", "terms": "10"})
    ali.refresh_from_db()
    assert ali.credit_limit == Decimal("400")
    assert client.get(reverse("webapp:customer_account", args=[ali.id])).context["credit"]["over_limit"]
    listing = client.get(reverse("webapp:customer_list"), {"q": "Ali"})
    assert listing.context["customers"][0].balance == Decimal("500")


def test_other_company_customer_is_not_reachable(books, tenant_b):
    other = Customer.objects.create(company=tenant_b, name="Other")
    assert books["client"].get(reverse("webapp:customer_account", args=[other.id])).status_code == 404
    books["client"].post(reverse("webapp:receive_payment", args=[other.id]), {"amount": "10"})
    assert not CustomerPayment.objects.filter(customer=other).exists()

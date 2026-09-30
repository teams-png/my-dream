from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounting.models import Account
from apps.accounting.services import account_balance, seed_chart_of_accounts
from apps.audit.models import AuditLog
from apps.banking.models import BankAccount, StatementTransaction
from apps.crm.models import Activity, Lead, Opportunity
from apps.customers.models import Customer
from apps.sales.models import ExchangeRate, PriceList, PriceListItem, Promotion, TaxCode

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client, tenant_a, tenant_a_owner, sales_fixtures_factory):
    seed_chart_of_accounts(tenant_a)
    base = sales_fixtures_factory(tenant_a, sku="TEA", stock_price=Decimal("10"))
    client.force_login(tenant_a_owner)
    return {"client": client, "company": tenant_a, "user": tenant_a_owner, **base}


def test_bank_accounts_money_in_out_transfer_and_reconcile(owner):
    client, company = owner["client"], owner["company"]
    client.get(reverse("webapp:bank_home"))
    cash = BankAccount.objects.get(company=company, ledger_account__code="1000")
    bankacc = BankAccount.objects.get(company=company, ledger_account__code="1010")
    capital = Account.objects.get(company=company, code="3000")
    client.post(reverse("webapp:bank_home"), {"action": "in", "account": cash.id, "contra": capital.id, "amount": "5000", "memo": "Capital"})
    client.post(reverse("webapp:bank_home"), {"action": "transfer", "from": cash.id, "to": bankacc.id, "amount": "3000"})
    assert account_balance(cash.ledger_account) == Decimal("2000") and account_balance(bankacc.ledger_account) == Decimal("3000")
    client.post(reverse("webapp:bank_home"), {"action": "add", "name": "QNB Savings", "account_type": "bank", "opening": "1000"})
    qnb = BankAccount.objects.get(company=company, name="QNB Savings")
    assert qnb.ledger_account.code == "1011" and account_balance(qnb.ledger_account) == Decimal("1000")
    csv = f"date,description,amount,reference\n{date.today():%Y-%m-%d},Transfer in,3000,T1\n{date.today():%Y-%m-%d},Bank charge,-15,FEE\n"
    client.post(reverse("webapp:bank_account", args=[bankacc.id]), {"action": "import", "statement": SimpleUploadedFile("s.csv", csv.encode())})
    rows = StatementTransaction.objects.filter(bank_account=bankacc).order_by("amount")
    assert rows.count() == 2
    page = client.get(reverse("webapp:bank_account", args=[bankacc.id]))
    transfer_row = next(r for r in page.context["unmatched"] if r.amount == Decimal("3000"))
    assert transfer_row.suggestions
    client.post(reverse("webapp:bank_account", args=[bankacc.id]), {"action": "match", "row": transfer_row.id, "entry": transfer_row.suggestions[0].id})
    fee = rows.first()
    expense = Account.objects.get(company=company, code="5100")
    client.post(reverse("webapp:bank_account", args=[bankacc.id]), {"action": "create", "row": fee.id, "contra": expense.id})
    summary = client.get(reverse("webapp:bank_account", args=[bankacc.id])).context["summary"]
    assert summary["unmatched_count"] == 0 and summary["ledger_balance"] == Decimal("2985")
    # the same file again is refused
    client.post(reverse("webapp:bank_account", args=[bankacc.id]), {"action": "import", "statement": SimpleUploadedFile("s.csv", csv.encode())})
    assert StatementTransaction.objects.filter(bank_account=bankacc).count() == 2


def test_lead_to_customer_and_pipeline(owner):
    client, company = owner["client"], owner["company"]
    client.post(reverse("webapp:lead_list"), {"name": "Maryam", "phone": "5551", "source": "Instagram", "note": "Wants 3 laptops"})
    lead = Lead.objects.get(company=company)
    client.post(reverse("webapp:lead_detail", args=[lead.id]), {"action": "activity", "type": "call", "subject": "Call back", "due": (date.today() + timedelta(days=1)).isoformat()})
    lead.refresh_from_db()
    assert lead.status == "qualified" and Activity.objects.filter(lead=lead, completed_at__isnull=True).count() == 1
    assert client.get(reverse("webapp:crm_pipeline")).context["todo"]
    client.post(reverse("webapp:lead_detail", args=[lead.id]), {"action": "convert"})
    lead.refresh_from_db()
    assert lead.status == "converted" and lead.converted_customer.name == "Maryam"
    deal = Opportunity.objects.get(lead=lead)
    stages = client.get(reverse("webapp:crm_pipeline")).context["stages"]
    won = next(s for s in stages if s.is_won)
    client.post(reverse("webapp:crm_pipeline"), {"action": "move", "id": deal.id, "stage": won.id})
    deal.refresh_from_db()
    assert deal.stage == won
    client.post(reverse("webapp:crm_pipeline"), {"action": "add", "title": "Office chairs", "value": "4500"})
    assert Opportunity.objects.filter(company=company, title="Office chairs").exists()


def test_price_lists_and_offers_reach_editor_and_pos(owner):
    client, company, product = owner["client"], owner["company"], owner["product"]
    vip = Customer.objects.create(company=company, name="VIP")
    client.post(reverse("webapp:pricing"), {"action": "list", "name": "VIP prices", "customer": vip.id})
    plist = PriceList.objects.get(company=company)
    client.post(reverse("webapp:price_list_detail", args=[plist.id]), {"action": "item", "product": product.id, "price": "7.50"})
    assert PriceListItem.objects.get(price_list=plist).unit_price == Decimal("7.50")
    vip_price = client.get(reverse("webapp:price_lookup"), {"product": product.id, "customer": vip.id}).json()
    assert vip_price["price"] == "7.50"
    client.post(reverse("webapp:pricing"), {"action": "offer", "name": "Weekend", "value": "10", "kind": "percentage",
                                            "start": date.today().isoformat(), "end": (date.today() + timedelta(days=2)).isoformat()})
    assert Promotion.objects.filter(company=company, name="Weekend").exists()
    walk_in = client.get(reverse("webapp:price_lookup"), {"product": product.id}).json()
    assert walk_in["price"] == "9.00" and walk_in["offer"] == "Weekend"
    from apps.webapp.views import _pos_catalog
    item = next(c for c in _pos_catalog(company)[0] if c["id"] == product.id)
    assert item["price"] == "9.00" and item["was"] == "10.00"


def test_audit_log_tax_and_rates(owner):
    client, company, user = owner["client"], owner["company"], owner["user"]
    AuditLog.objects.create(company=company, user=user, action="stock_adjustment", model_name="StockMovement", object_id="7", changes={"note": "broken"})
    page = client.get(reverse("webapp:company_audit_log"), {"q": "stock"})
    assert page.status_code == 200 and len(page.context["page"].object_list) == 1
    client.post(reverse("webapp:tax_currency"), {"action": "scheme", "name": "VAT", "registration": "300123"})
    client.post(reverse("webapp:tax_currency"), {"action": "code", "code": "VAT5", "name": "Standard", "rate": "5", "classification": "taxable"})
    client.post(reverse("webapp:tax_currency"), {"action": "rate", "currency": "usd", "rate": "3.64"})
    assert TaxCode.objects.get(company=company).rate == Decimal("5")
    assert ExchangeRate.objects.get(company=company).currency == "USD"
    client.post(reverse("webapp:tax_currency"), {"action": "rate", "currency": "US", "rate": "0"})
    assert ExchangeRate.objects.filter(company=company).count() == 1

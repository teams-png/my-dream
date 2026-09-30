from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.accounting.models import Account, JournalEntry
from apps.accounting.services import post_journal_entry, seed_chart_of_accounts
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(client, settings):
    settings.SIGNUP_LIMIT_PER_IP_PER_HOUR = 1000
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Ledger Co", "business_type": "supermarket", "country": "Qatar", "full_name": "Owner",
        "email": "acc@test.qa", "phone": "", "password": "Ledger-Books-2026!", "accept_terms": "on", "website": ""})
    company = Company.objects.get(email="acc@test.qa")
    seed_chart_of_accounts(company)
    user = company.memberships.first().user
    a = {code: Account.objects.get(company=company, code=code) for code in ("1000", "1010", "3000", "4000", "5100", "5000", "1200")}
    today = date.today()
    post_journal_entry(company=company, date=today, user=user, lines=[(a["1010"], Decimal("10000"), 0), (a["3000"], 0, Decimal("10000"))],
                       reference="Capital", source_type="manual")
    post_journal_entry(company=company, date=today, user=user, lines=[(a["1000"], Decimal("1500"), 0), (a["4000"], 0, Decimal("1500"))],
                       reference="INV-1", source_type="sales_invoice")
    post_journal_entry(company=company, date=today, user=user, lines=[(a["5000"], Decimal("600"), 0), (a["1200"], 0, Decimal("600"))],
                       reference="INV-1 cost", source_type="sales_invoice")
    post_journal_entry(company=company, date=today, user=user, lines=[(a["5100"], Decimal("200"), 0), (a["1000"], 0, Decimal("200"))],
                       reference="Rent", source_type="expense")
    return {"company": company, "user": user, "a": a, "client": client}


def test_statements_show_ledger_figures(owner):
    client = owner["client"]
    pl = client.get(reverse("webapp:acc_pl")).content.decode()
    assert "1500.00" in pl and "900.00" in pl and "700.00" in pl  # income, gross profit, net profit
    bs = client.get(reverse("webapp:acc_bs"))
    assert bs.context["balanced"]
    tb = client.get(reverse("webapp:acc_tb"))
    assert tb.context["balanced"] and tb.context["total_debit"] == Decimal("12100")
    cf = client.get(reverse("webapp:acc_cf"))
    assert cf.context["cf"]["closing_balance"] == Decimal("11300")
    for name in ("acc_home", "acc_vat", "acc_chart", "acc_journal", "acc_journal_add"):
        assert client.get(reverse(f"webapp:{name}")).status_code == 200, name
    ledger = client.get(reverse("webapp:acc_ledger", args=[owner["a"]["1000"].id]), {"period": "all"})
    assert ledger.context["closing"] == Decimal("1300")
    assert client.get(reverse("webapp:acc_pl"), {"period": "last_year"}).context["pl"]["net_profit"] == 0


def test_manual_journal_entry_must_balance_and_can_be_cancelled(owner):
    client, a = owner["client"], owner["a"]
    bad = client.post(reverse("webapp:acc_journal_add"), {
        "date": "2026-09-10", "reference": "Wrong", "memo": "",
        "account": [a["5100"].id, a["1000"].id], "debit": ["100", ""], "credit": ["", "90"], "note": ["", ""]})
    assert bad.status_code == 200 and not JournalEntry.objects.filter(reference="Wrong").exists()
    good = client.post(reverse("webapp:acc_journal_add"), {
        "date": "2026-09-10", "reference": "Electricity", "memo": "September bill",
        "account": [a["5100"].id, a["1000"].id, ""], "debit": ["100", "", ""], "credit": ["", "100", ""], "note": ["", "", ""]})
    entry = JournalEntry.objects.get(reference="Electricity")
    assert good.status_code == 302 and entry.source_type == "manual"
    client.post(reverse("webapp:acc_journal_detail", args=[entry.id]), {"action": "void"})
    entry.refresh_from_db()
    assert entry.is_void
    # automatic entries (from sales) can't be cancelled here
    sale = JournalEntry.objects.get(reference="INV-1")
    client.post(reverse("webapp:acc_journal_detail", args=[sale.id]), {"action": "void"})
    sale.refresh_from_db()
    assert not sale.is_void


def test_new_account_and_duplicate_code(owner):
    client, company = owner["client"], owner["company"]
    client.post(reverse("webapp:acc_chart"), {"action": "add", "code": "5300", "name": "Rent", "type": "expense"})
    client.post(reverse("webapp:acc_chart"), {"action": "add", "code": "5300", "name": "Again", "type": "expense"})
    assert Account.objects.filter(company=company, code="5300").count() == 1
    system = Account.objects.get(company=company, code="1000")
    client.post(reverse("webapp:acc_chart"), {"action": "deactivate", "id": system.id})
    system.refresh_from_db()
    assert system.is_active


def test_staff_role_cannot_open_accounts(owner, client):
    from apps.accounts.models import User
    from apps.tenants.models import CompanyMembership as Membership, Role
    staff_role = Role.objects.get(company=owner["company"], name="Staff")
    cashier = User.objects.create_user(username="cashier@test.qa", email="cashier@test.qa", password="Cashier-2026-x!")
    Membership.objects.create(user=cashier, company=owner["company"], role=staff_role)
    client.force_login(cashier)
    assert client.get(reverse("webapp:acc_pl")).status_code == 302

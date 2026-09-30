from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting.services import seed_chart_of_accounts
from apps.expenses.budgets import month_rows
from apps.expenses.models import ExpenseBudget, ExpenseCategory
from apps.expenses.services import record_expense
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(tenant_a, tenant_a_owner):
    seed_chart_of_accounts(tenant_a)
    rent = ExpenseCategory.objects.create(company=tenant_a, name="Rent")
    fuel = ExpenseCategory.objects.create(company=tenant_a, name="Fuel")
    return {"company": tenant_a, "user": tenant_a_owner, "rent": rent, "fuel": fuel}


def _spend(s, category, amount, day=None):
    return record_expense(company=s["company"], user=s["user"], category=category, date=day or date.today(),
                          amount=Decimal(amount))


def test_page_saves_and_clears_budgets(client, setup):
    client.force_login(setup["user"])
    rent, fuel = setup["rent"], setup["fuel"]
    resp = client.post(reverse("webapp:budgets"), {f"b_{rent.id}": "1000", f"a_{rent.id}": "75", f"b_{fuel.id}": ""})
    assert resp.status_code == 302
    budget = ExpenseBudget.objects.get(company=setup["company"], category=rent)
    assert budget.monthly_amount == Decimal("1000") and budget.alert_percent == 75
    assert not ExpenseBudget.objects.filter(category=fuel).exists()
    client.post(reverse("webapp:budgets"), {f"b_{rent.id}": ""})
    assert not ExpenseBudget.objects.filter(category=rent).exists()
    assert client.get(reverse("webapp:budgets") + "?m=2026-01").status_code == 200


def test_month_rows_states(setup):
    ExpenseBudget.objects.create(company=setup["company"], category=setup["rent"], monthly_amount=Decimal("100"))
    ExpenseBudget.objects.create(company=setup["company"], category=setup["fuel"], monthly_amount=Decimal("100"))
    _spend(setup, setup["rent"], "85")
    _spend(setup, setup["fuel"], "20")
    rows = {r["category"].name: r for r in month_rows(setup["company"], date.today())}
    assert rows["Rent"]["state"] == "near" and rows["Rent"]["percent"] == 85
    assert rows["Fuel"]["state"] == "ok" and rows["Fuel"]["left"] == Decimal("80")


def test_alerts_once_per_level(setup, client):
    ExpenseBudget.objects.create(company=setup["company"], category=setup["rent"], monthly_amount=Decimal("100"))
    alerts = Notification.objects.filter(company=setup["company"], title__icontains="Rent")
    _spend(setup, setup["rent"], "50")
    assert alerts.count() == 0
    _spend(setup, setup["rent"], "35")
    _spend(setup, setup["rent"], "5")
    assert alerts.count() == 1
    _spend(setup, setup["rent"], "20")
    _spend(setup, setup["rent"], "20")
    assert alerts.count() == 2 and alerts.filter(title__startswith="Budget exceeded").count() == 1
    client.force_login(setup["user"])
    assert "Rent" in client.get(reverse("webapp:budgets")).content.decode()

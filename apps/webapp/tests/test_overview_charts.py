"""Overview charts: receivables and payables, sales by month and day, income vs expense, top items — for the
people who may see reports, and only from this business's own bills."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.expenses.models import Expense, ExpenseCategory
from apps.sales.models import SalesInvoice
from apps.webapp import overview_charts

pytestmark = pytest.mark.django_db


def _bill(company, customer, day, total, paid=None, due=None, number="INV"):
    return SalesInvoice.objects.create(company=company, customer=customer, invoice_number=f"{number}-{day}-{total}",
                                       date=day, due_date=due, subtotal=Decimal(total), total=Decimal(total),
                                       amount_paid=Decimal(total if paid is None else paid),
                                       status="paid" if paid is None else "unpaid")


def test_numbers_come_from_this_business_only(tenant_a, tenant_b):
    today = timezone.localdate()
    a = Customer.objects.create(company=tenant_a, name="Ravi")
    b = Customer.objects.create(company=tenant_b, name="Other")
    _bill(tenant_a, a, today, "100")
    _bill(tenant_a, a, today - timedelta(days=1), "50")
    _bill(tenant_a, a, today - timedelta(days=40), "80", paid="0", due=today - timedelta(days=10))  # overdue
    _bill(tenant_a, a, today, "30", paid="0", due=today + timedelta(days=5))  # current
    _bill(tenant_b, b, today, "999")
    cat = ExpenseCategory.objects.create(company=tenant_a, name="Rent")
    Expense.objects.create(company=tenant_a, category=cat, date=today, amount=Decimal("40"))

    data = overview_charts.build(tenant_a, today)
    summary = {s["label"]: s for s in data["summary"]}
    assert summary["Today's sales"]["value"] == Decimal("130") and summary["Today's sales"]["change"] == 160
    receivables = data["dues_cards"][0][2]
    assert receivables["total"] == Decimal("110") and receivables["overdue"] == Decimal("80")
    assert receivables["current"] == Decimal("30")
    assert data["series"]["sales12"][-1] == float(sum(
        Decimal(x) for x, d in (("100", today), ("50", today - timedelta(days=1)), ("30", today))
        if d.month == today.month) + (Decimal("80") if (today - timedelta(days=40)).month == today.month else 0))
    assert data["series"]["daily"][-1] == 130.0 and len(data["series"]["daily"]) == 30
    assert data["series"]["spendLabels"] == ["Rent"]
    assert data["year_sales"] == Decimal("260")


def test_owner_sees_charts_cashier_does_not(tenant_a, tenant_a_owner, user_factory):
    from apps.tenants.models import Role
    from apps.tenants.services import invite_member
    c = Client()
    c.force_login(tenant_a_owner)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "Total receivables" in page and 'id="ovcData"' in page and "overview-charts.js" in page
    json.loads(page.split('id="ovcData" type="application/json">')[1].split("</script>")[0])  # the chart data is valid JSON

    staff = user_factory()
    invite_member(company=tenant_a, user=staff, role=Role.objects.get(company=tenant_a, name="Staff"))
    s = Client()
    s.force_login(staff)
    page = s.get(reverse("webapp:dashboard")).content.decode()
    assert "Total receivables" not in page and 'id="ovcData"' not in page


def test_each_number_shows_once(tenant_a, tenant_a_owner, user_factory):
    """With the charts on, the tiles that repeat them (today's sales, this month, dues) are left out;
    a cashier, who has no charts, still gets those tiles."""
    from apps.tenants.models import Role
    from apps.tenants.services import invite_member
    c = Client()
    c.force_login(tenant_a_owner)
    labels = [k["label"] for k in c.get(reverse("webapp:dashboard")).context["kpis"]]
    assert "Today's sales" not in labels and "This month's revenue" not in labels and "Outstanding dues" not in labels

    staff = user_factory()
    invite_member(company=tenant_a, user=staff, role=Role.objects.get(company=tenant_a, name="Staff"))
    s = Client()
    s.force_login(staff)
    labels = [k["label"] for k in s.get(reverse("webapp:dashboard")).context["kpis"]]
    assert "Today's sales" in labels

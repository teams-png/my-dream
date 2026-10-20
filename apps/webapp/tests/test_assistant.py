"""Ask BookPilot: off without an API key; with one, the question goes to Claude with this business's figures only,
and the answer shows on the page. The Claude API itself is replaced by a stand-in here."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.customers.models import Customer
from apps.sales.models import SalesInvoice
from apps.webapp import assistant

pytestmark = pytest.mark.django_db


def _reply(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_off_without_key(tenant_a_owner, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = Client()
    c.force_login(tenant_a_owner)
    assert reverse("webapp:assistant") not in c.get(reverse("webapp:dashboard")).content.decode()
    assert c.get(reverse("webapp:assistant")).status_code == 404


def test_ask_uses_this_business_figures(tenant_a, tenant_a_owner, tenant_b, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    today = timezone.localdate()
    mine = Customer.objects.create(company=tenant_a, name="Ravi Kumar")
    SalesInvoice.objects.create(company=tenant_a, customer=mine, invoice_number="INV-1", date=today,
                                due_date=today - timedelta(days=1), subtotal=Decimal("120"), total=Decimal("120"),
                                status="unpaid")
    theirs = Customer.objects.create(company=tenant_b, name="Other Shop Customer")
    SalesInvoice.objects.create(company=tenant_b, customer=theirs, invoice_number="X-1", date=today,
                                subtotal=Decimal("999"), total=Decimal("999"), status="unpaid")
    c = Client()
    c.force_login(tenant_a_owner)
    assert reverse("webapp:assistant") in c.get(reverse("webapp:dashboard")).content.decode()

    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return _reply("Ravi Kumar owes you 120.00.")
    fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=fake_create)))
    with mock.patch("anthropic.Anthropic", return_value=fake):
        r = c.post(reverse("webapp:assistant"), {"question": "Who owes me money?"})
    assert r.status_code == 302
    page = c.get(reverse("webapp:assistant")).content.decode()
    assert "Ravi Kumar owes you 120.00." in page and "Who owes me money?" in page
    prompt = sent["messages"][-1]["content"]
    assert "Ravi Kumar" in prompt and "Other Shop Customer" not in prompt and "999" not in prompt
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"

    with mock.patch("anthropic.Anthropic", return_value=SimpleNamespace(beta=SimpleNamespace(
            messages=SimpleNamespace(create=lambda **k: _reply("", "refusal"))))):
        page = c.post(reverse("webapp:assistant"), {"question": "x"}).content.decode()
    assert "can&#x27;t answer" in page or "can't answer" in page

    monkeypatch.setattr(assistant, "DAILY_LIMIT", 1)
    page = c.post(reverse("webapp:assistant"), {"question": "again"}).content.decode()
    assert "used up" in page


def test_staff_role_cannot_ask(tenant_a, user_factory, monkeypatch):
    from apps.tenants.models import Role
    from apps.tenants.services import invite_member
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    staff = user_factory()
    invite_member(company=tenant_a, user=staff, role=Role.objects.get(company=tenant_a, name="Staff"))
    c = Client()
    c.force_login(staff)
    assert c.get(reverse("webapp:assistant")).status_code in (302, 403)

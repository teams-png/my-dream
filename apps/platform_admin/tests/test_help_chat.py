"""Help chat: clients write to support, the platform admin answers from the Help inbox."""
import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.platform_admin import support
from apps.platform_admin.models import SupportMessage, SupportTicket

pytestmark = pytest.mark.django_db


def _login(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def admin_user():
    return User.objects.create_user(username="help@bp.qa", email="help@bp.qa", password="Help-Pass-123",
                                    is_platform_admin=True)


def test_conversation_flow(tenant_a, tenant_a_owner, admin_user, settings, django_capture_on_commit_callbacks):
    settings.SUPPORT_EMAIL = "support@bp.qa"
    tenant_a.country, tenant_a.phone = "Qatar", "+974 5555 1234"
    tenant_a.save(update_fields=["country", "phone"])
    with django_capture_on_commit_callbacks(execute=True):
        m1 = support.client_send(tenant_a, tenant_a_owner, "  How do I add a printer?  ")
        support.client_send(tenant_a, tenant_a_owner, "It is an Epson.")
    ticket = SupportTicket.objects.get(company=tenant_a)
    assert m1.body == "How do I add a printer?" and ticket.subject == "How do I add a printer?"
    assert ticket.admin_unread == 2 and support.admin_unread_total() == 2
    # one email for the first unread message, not one per message
    assert len(mail.outbox) == 1 and "help@bp.qa" in mail.outbox[0].to and "support@bp.qa" in mail.outbox[0].to
    assert "Qatar" in mail.outbox[0].body and "+974 5555 1234" in mail.outbox[0].body

    support.admin_reply(ticket, admin_user, "Go to Settings → Devices.")
    ticket.refresh_from_db()
    assert ticket.admin_unread == 0 and ticket.client_unread == 1 and ticket.status == "in_progress"
    assert support.client_unread_total(tenant_a) == 1
    assert Notification.objects.for_company(tenant_a).filter(title="BookPilot support replied").exists()

    ticket.status = "resolved"
    ticket.save(update_fields=["status"])
    support.client_send(tenant_a, tenant_a_owner, "New question")
    assert SupportTicket.objects.filter(company=tenant_a).count() == 2
    assert [m.body for m in support.conversation(tenant_a)][-1] == "New question"

    from django.core.exceptions import ValidationError
    for bad in ("", "   ", "x" * 4001):
        with pytest.raises(ValidationError):
            support.client_send(tenant_a, tenant_a_owner, bad)


def test_client_pages(tenant_a, tenant_a_owner, tenant_b, tenant_b_owner):
    c = _login(tenant_a_owner)
    page = c.get(reverse("webapp:help"))
    assert page.status_code == 200 and "data-chat" in page.content.decode()
    c.post(reverse("webapp:help"), {"body": "Hello support"})
    r = c.post(reverse("webapp:help") + "?after=0", {"body": "Second"}, HTTP_X_REQUESTED_WITH="fetch")
    data = r.json()["messages"]
    assert [m["body"] for m in data] == ["Hello support", "Second"] and all(m["mine"] for m in data)
    bad = c.post(reverse("webapp:help"), {"body": " "}, HTTP_X_REQUESTED_WITH="fetch")
    assert bad.status_code == 400 and bad.json()["error"]
    after = data[-1]["id"]
    assert c.get(reverse("webapp:help_messages") + f"?after={after}").json()["messages"] == []
    # another business never sees it
    other = _login(tenant_b_owner)
    assert other.get(reverse("webapp:help_messages")).json()["messages"] == []
    assert "Hello support" not in other.get(reverse("webapp:help")).content.decode()
    # staff can't open the admin inbox
    assert c.get(reverse("webapp:platform_support_list")).status_code == 302
    assert c.get(reverse("webapp:platform_support_unread")).status_code == 302


def test_expired_client_can_still_ask_for_help(tenant_a, tenant_a_owner):
    from datetime import timedelta
    from django.utils import timezone
    sub = tenant_a.subscription
    sub.end_date, sub.status = timezone.localdate() - timedelta(days=5), "expired"
    sub.save(update_fields=["end_date", "status"])
    c = _login(tenant_a_owner)
    assert c.get(reverse("webapp:dashboard")).status_code == 302
    assert c.get(reverse("webapp:help")).status_code == 200


def test_admin_inbox(tenant_a, tenant_a_owner, tenant_b, admin_user):
    tenant_a.country = "India"
    tenant_a.save(update_fields=["country"])
    support.client_send(tenant_a, tenant_a_owner, "Need GST invoice help")
    ticket = SupportTicket.objects.get(company=tenant_a)
    a = _login(admin_user)
    assert a.get(reverse("webapp:platform_support_unread")).json()["unread"] == 1
    html = a.get(reverse("webapp:platform_support_list")).content.decode()
    assert "Need GST invoice help" in html and tenant_a.name in html and "India" in html
    for show in ("unread", "resolved", "all", "bogus"):
        assert a.get(reverse("webapp:platform_support_list") + f"?show={show}&q=gst").status_code == 200
    page = a.get(reverse("webapp:platform_support_chat", args=[ticket.id])).content.decode()
    assert "Client details" in page and "India" in page and tenant_a_owner.email in page
    assert a.get(reverse("webapp:platform_support_unread")).json()["unread"] == 0  # opening it reads it
    r = a.post(reverse("webapp:platform_support_chat", args=[ticket.id]) + "?after=0",
               {"action": "reply", "body": "Sure, here is how"}, HTTP_X_REQUESTED_WITH="fetch")
    assert [m["mine"] for m in r.json()["messages"]] == [False, True]
    seen = _login(tenant_a_owner).get(reverse("webapp:help_messages")).json()["messages"]
    assert seen[-1]["who"] == "BookPilot support" and admin_user.email not in str(seen)
    a.post(reverse("webapp:platform_support_chat", args=[ticket.id]),
           {"action": "status", "status": "resolved", "priority": "high", "assigned_to": ""})
    ticket.refresh_from_db()
    assert ticket.status == "resolved" and ticket.priority == "high"
    assert a.get(reverse("webapp:platform_support_edit", args=[ticket.id])).status_code == 302

    # admin starts a conversation with another client
    url = reverse("webapp:platform_support_start", args=[tenant_b.id])
    assert a.get(url).status_code == 200
    r = a.post(url, {"body": "Your trial ends soon"})
    started = SupportTicket.objects.get(company=tenant_b)
    assert r.url == reverse("webapp:platform_support_chat", args=[started.id]) and started.client_unread == 1
    assert SupportMessage.objects.filter(ticket=started, from_admin=True).count() == 1

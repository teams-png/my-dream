"""Welcome, tip, last-day and trial-ended emails, each sent once."""
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.subscriptions import trial_emails
from apps.tenants.models import Company

pytestmark = pytest.mark.django_db


def _signup(client):
    call_command("seed_platform")
    client.post(reverse("webapp:signup"), {
        "business_name": "Style Cuts", "business_type": "saloon", "country": "Qatar", "full_name": "Anu Thomas",
        "email": "anu@style.test", "phone": "", "password": "Style-Cuts-2026!", "accept_terms": "on", "website": ""})
    return Company.objects.get(name="Style Cuts")


def test_welcome_on_signup(client, settings, django_capture_on_commit_callbacks):
    settings.SITE_URL = "https://app.bookpilot.test"
    with django_capture_on_commit_callbacks(execute=True):
        _signup(client)
    welcome = [m for m in mail.outbox if "Welcome to BookPilot" in m.subject]
    assert len(welcome) == 1 and welcome[0].to == ["anu@style.test"]
    assert "https://app.bookpilot.test/pos/?tour=1" in welcome[0].body and "Hi Anu" in welcome[0].body


def test_schedule_and_once(client, settings):
    company = _signup(client)
    mail.outbox.clear()
    sub = company.subscription
    start = sub.start_date
    assert trial_emails.due_kind(sub, start) is None
    assert trial_emails.due_kind(sub, start + timedelta(days=1)) == "tip"
    assert trial_emails.due_kind(sub, sub.end_date - timedelta(days=1)) in ("last_day", "tip")
    assert trial_emails.due_kind(sub, sub.end_date + timedelta(days=1)) == "ended"

    assert trial_emails.send(company, "tip") == 1 and trial_emails.send(company, "tip") == 0
    assert "first bill" in mail.outbox[-1].subject
    trial_emails.send(company, "last_day")
    assert "ends tomorrow" in mail.outbox[-1].subject and "/billing/" in mail.outbox[-1].body
    sub.status = "active"
    sub.save(update_fields=["status"])
    assert trial_emails.due_kind(sub, start + timedelta(days=1)) is None  # paid customers get no trial mails


def test_no_mail_server_no_email(client, settings):
    company = _signup(client)
    mail.outbox.clear()
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = ""
    assert trial_emails.send(company, "ended") == 0 and not mail.outbox

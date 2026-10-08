"""Short emails to the owner during the free trial: welcome, a tip for the next step, and a nudge to pick a plan.

  welcome   – right after sign-up
  tip       – the day after: "make your first sale" if they haven't, else "add your staff / your own products"
  last_day  – the trial's last day: pick a plan, the data stays
  ended     – the day after it ends: everything is still there, renew to carry on
Each goes once (ReminderLog), only while the business is on trial, and only when a mail server is set up.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)


def _owner(company):
    membership = company.memberships.select_related("user").filter(role__name="Owner").first()
    return membership.user if membership else None


def _site():
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def _send(company, user, subject, lines):
    body = "\n\n".join([_("Hi %(name)s,") % {"name": user.first_name or user.email}] + lines +
                       [_("Need help? Reply to this email or chat with us from Help inside BookPilot."), "— BookPilot"])
    send_mail(subject, body, None, [user.email], fail_silently=False)


def message_for(company, kind):
    """(subject, [paragraphs]) for one email."""
    from apps.sales.models import SalesInvoice
    from apps.webapp.checklist import summary
    site = _site()
    if kind == "welcome":
        return (_("Welcome to BookPilot, %(shop)s!") % {"shop": company.name}, [
            _("Your free trial has started. We added sample products, services and customers so you can try everything at once."),
            _("Start here – make a test sale in one minute: %(url)s") % {"url": site + reverse("webapp:pos") + "?tour=1"},
            _("When you are ready, remove the sample data from the Overview page and add your own."),
        ])
    if kind == "tip":
        if not SalesInvoice.objects.for_company(company).exists():
            return (_("Have you made your first bill yet?"), [
                _("A quick test sale shows you the whole flow: bill, payment and a WhatsApp receipt."),
                _("Try it now: %(url)s") % {"url": site + reverse("webapp:pos") + "?tour=1"},
            ])
        left = [i["label"] for i in summary(company)["items"] if not i["done"]]
        return (_("Your next steps in BookPilot"), [
            _("Great start! Here is what is left to finish your setup:"),
            "\n".join(f"• {label}" for label in left[:4]) or _("Everything is set up – well done!"),
            _("Open your checklist: %(url)s") % {"url": site + reverse("webapp:dashboard")},
        ])
    if kind == "last_day":
        return (_("Your BookPilot trial ends tomorrow"), [
            _("Pick a plan today to keep billing without a break. Everything you added stays exactly as it is."),
            _("Choose a plan: %(url)s") % {"url": site + reverse("webapp:billing")},
        ])
    return (_("Your BookPilot trial has ended – your data is safe"), [
        _("Your products, customers and bills are all still there. Choose a plan to carry on where you left off."),
        _("Renew now: %(url)s") % {"url": site + reverse("webapp:billing")},
    ])


def due_kind(subscription, today):
    """Which email (if any) this trial gets today."""
    started = subscription.start_date
    end = subscription.end_date
    if subscription.status == "trial" and end and today == end - timedelta(days=1) and today > started:
        return "last_day"
    if subscription.status == "trial" and today == started + timedelta(days=1):
        return "tip"
    if end and today == end + timedelta(days=1) and subscription.status in ("trial", "expired"):
        return "ended"
    return None


def send(company, kind):
    """Sends one trial email once. Returns 1 if sent."""
    from apps.notifications.rules import once
    from apps.notifications.services import email_configured
    user = _owner(company)
    if user is None or not user.email or not email_configured():
        return 0
    if not once(company, f"trial-email:{kind}"):
        return 0
    with translation.override(settings.LANGUAGE_CODE):
        subject, lines = message_for(company, kind)
        try:
            _send(company, user, subject, lines)
        except Exception:
            log.exception("trial email %s to company %s failed", kind, company.pk)
            return 0
    return 1


def daily(company):
    """Daily job: the trial email due today, if any."""
    sub = getattr(company, "subscription", None)
    if sub is None:
        return 0
    kind = due_kind(sub, timezone.localdate())
    return send(company, kind) if kind else 0

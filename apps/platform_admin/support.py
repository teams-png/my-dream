"""Help chat between a client business and BookPilot support (the platform admin).

A business has at most one open conversation (SupportTicket) at a time; once support marks it
resolved or closed, the client's next message starts a new one. New client messages raise the
admin's unread count and email the platform admins; replies notify the client in-app and by email."""
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import SupportMessage, SupportTicket

log = logging.getLogger(__name__)
OPEN = ("open", "in_progress")
MAX_LENGTH = 4000


def _clean(body):
    body = (body or "").strip()
    if not body:
        raise ValidationError("Type a message first.")
    if len(body) > MAX_LENGTH:
        raise ValidationError(f"Please keep a message under {MAX_LENGTH} characters.")
    return body


def current_ticket(company):
    return SupportTicket.objects.filter(company=company, status__in=OPEN).order_by("-created_at").first()


def conversation(company):
    """Every message this business has exchanged with support, oldest first."""
    return (SupportMessage.objects.filter(ticket__company=company)
            .select_related("sender", "ticket").order_by("created_at", "id"))


@transaction.atomic
def client_send(company, user, body, admin_url=None):
    body = _clean(body)
    ticket = current_ticket(company)
    if ticket is None:
        subject = " ".join(body.split())[:80]
        ticket = SupportTicket.objects.create(company=company, raised_by=user, subject=subject, message=body)
    msg = SupportMessage.objects.create(ticket=ticket, sender=user, body=body)
    first_unread = ticket.admin_unread == 0
    SupportTicket.objects.filter(pk=ticket.pk).update(
        admin_unread=F("admin_unread") + 1, client_unread=0, last_message_at=msg.created_at)
    if first_unread:
        transaction.on_commit(lambda: _email_admins(ticket, user, body, admin_url))
    return msg


@transaction.atomic
def admin_reply(ticket, user, body):
    body = _clean(body)
    msg = SupportMessage.objects.create(ticket=ticket, sender=user, from_admin=True, body=body)
    status = "in_progress" if ticket.status == "open" else ticket.status
    SupportTicket.objects.filter(pk=ticket.pk).update(
        client_unread=F("client_unread") + 1, admin_unread=0, last_message_at=msg.created_at, status=status)
    from apps.notifications.services import notify
    notify(company=ticket.company, recipient=ticket.raised_by, notif_type="general",
           title="BookPilot support replied", message=body[:240])
    return msg


@transaction.atomic
def admin_start(company, user, body):
    """Support writes to a client first (e.g. from the billing page)."""
    body = _clean(body)
    ticket = current_ticket(company)
    if ticket is None:
        owner = company.memberships.filter(role__name="Owner").select_related("user").first()
        ticket = SupportTicket.objects.create(company=company, raised_by=owner.user if owner else None,
                                              subject=" ".join(body.split())[:80], message=body,
                                              status="in_progress")
    admin_reply(ticket, user, body)
    return ticket


def mark_read_by_admin(ticket):
    if ticket.admin_unread:
        SupportTicket.objects.filter(pk=ticket.pk).update(admin_unread=0)
        ticket.admin_unread = 0


def mark_read_by_client(company):
    SupportTicket.objects.filter(company=company, client_unread__gt=0).update(client_unread=0)


def admin_unread_total():
    return SupportTicket.objects.aggregate(n=Sum("admin_unread"))["n"] or 0


def client_unread_total(company):
    return SupportTicket.objects.filter(company=company).aggregate(n=Sum("client_unread"))["n"] or 0


def client_details(company):
    """Everything support needs to know about who is asking."""
    from apps.subscriptions.models import Subscription, SubscriptionPayment
    sub = Subscription.objects.filter(company=company).select_related("plan").first()
    owner = company.memberships.filter(role__name="Owner").select_related("user").first()
    paid = 0
    if sub:
        paid = SubscriptionPayment.objects.filter(subscription=sub, is_confirmed=True).aggregate(t=Sum("amount"))["t"] or 0
    return {
        "company": company,
        "owner": owner.user if owner else None,
        "sub": sub,
        "days_left": sub.days_remaining() if sub else None,
        "paid": paid,
        "users": company.memberships.filter(is_active=True).count(),
        "tickets": SupportTicket.objects.filter(company=company).count(),
        "whatsapp": wa_number(company.phone or (owner.user.phone if owner else "")),
    }


def wa_number(phone):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits if len(digits) >= 8 else ""


def _email_admins(ticket, user, body, admin_url=None):
    from apps.accounts.models import User
    to = set(User.objects.filter(is_platform_admin=True, is_active=True).exclude(email="").values_list("email", flat=True))
    if getattr(settings, "SUPPORT_EMAIL", ""):
        to.add(settings.SUPPORT_EMAIL)
    if not to:
        return
    company = ticket.company
    who = (user.get_full_name() or user.email) if user else "A client"
    lines = [f"{who} from {company.name} wrote:", "", body, "",
             f"Business type: {getattr(company.business_type, 'name', '')}",
             f"Country: {company.country or '-'}",
             f"Phone: {company.phone or getattr(user, 'phone', '') or '-'}",
             f"Email: {company.email or getattr(user, 'email', '') or '-'}"]
    if admin_url:
        lines += ["", f"Reply: {admin_url(ticket)}"]
    try:
        send_mail(f"[BookPilot help] {company.name}: {ticket.subject[:60]}", "\n".join(lines),
                  settings.DEFAULT_FROM_EMAIL, sorted(to), fail_silently=True)
    except Exception:  # email trouble must never lose the chat message
        log.exception("support email failed")


def stamp(msg):
    return timezone.localtime(msg.created_at)

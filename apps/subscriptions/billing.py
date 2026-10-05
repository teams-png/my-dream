"""
Client billing for the platform admin: BookPilot's invoices to its clients.

- An invoice covers one subscription period. It is issued ahead of a renewal (unpaid), or created
  automatically (paid) when a payment renews the subscription without one.
- Every renewal (admin payment, approved bank transfer, Stripe, SkipCash, Razorpay) goes through
  SubscriptionRenewal; the post_save hook below settles the oldest unpaid invoice with that
  payment, so invoices stay right whichever way the client paid.
- Recording a payment extends from the current expiry date (not from today), so days the client
  still had are never lost.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, OuterRef, Q, Subquery, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Subscription, SubscriptionInvoice, SubscriptionPayment, SubscriptionRenewal

METHODS = [("bank", "Bank transfer"), ("cash", "Cash"), ("card", "Card"), ("cheque", "Cheque"), ("online", "Online"),
           ("manual", "Other")]
EXPIRING_DAYS = 30


def period_days(plan):
    return 365 if plan.billing_period == "yearly" else 30


def next_period(subscription, today=None):
    today = today or timezone.localdate()
    start = max(subscription.end_date, today)
    return start, start + timedelta(days=period_days(subscription.plan))


def price(subscription):
    from .pricing import amount_due
    return amount_due(subscription)


def _number(invoice):
    if not invoice.number:
        invoice.number = f"BP-{invoice.issued_on:%Y}-{invoice.pk:05d}"
        invoice.save(update_fields=["number"])
    return invoice


@transaction.atomic
def issue_invoice(subscription, *, user=None, amount=None, due_on=None, notes=""):
    """An unpaid invoice for the next period. Issuing again for the same period returns the open one."""
    start, end = next_period(subscription)
    open_one = subscription.invoices.filter(status="unpaid", period_start=start).first()
    if open_one:
        return open_one
    try:
        amount = Decimal(str(price(subscription) if amount in (None, "") else amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValidationError("The amount must be a number.")
    if amount <= 0:
        raise ValidationError("The amount must be more than zero.")
    today = timezone.localdate()
    invoice = SubscriptionInvoice.objects.create(
        subscription=subscription, issued_on=today, due_on=due_on or max(subscription.end_date, today),
        period_start=start, period_end=end, plan_name=subscription.plan.name, amount=amount,
        currency=subscription.plan.currency, notes=(notes or "")[:255], created_by=user)
    return _number(invoice)


def void_invoice(invoice):
    if invoice.status != "unpaid":
        raise ValidationError("Only an unpaid invoice can be cancelled.")
    invoice.status = "void"
    invoice.save(update_fields=["status"])
    return invoice


@transaction.atomic
def record_payment(subscription, *, amount, method="bank", reference="", paid_on=None, invoice=None, user=None):
    """Money received from a client: renews from the current expiry date and settles the invoice."""
    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("The amount must be a number.")
    if amount <= 0:
        raise ValidationError("The amount must be more than zero.")
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    paid_on = paid_on or timezone.localdate()
    if invoice is not None and (invoice.subscription_id != subscription.pk or invoice.status != "unpaid"):
        raise ValidationError("This invoice can't take a payment.")
    previous_end = subscription.end_date
    start = invoice.period_start if invoice is not None else max(previous_end, paid_on)
    new_end = invoice.period_end if invoice is not None else start + timedelta(days=period_days(subscription.plan))
    payment = SubscriptionPayment.objects.create(subscription=subscription, amount=amount, paid_on=paid_on,
                                                 method=method or "manual", reference=(reference or "")[:100])
    if invoice is not None:
        _settle(invoice, payment)
    subscription.end_date = max(new_end, previous_end)
    subscription.status = "active"
    subscription.save(update_fields=["end_date", "status"])
    SubscriptionRenewal.objects.create(subscription=subscription, previous_end_date=previous_end,
                                       new_end_date=subscription.end_date)
    return payment


def _settle(invoice, payment):
    invoice.status = "paid"
    invoice.payment = payment
    invoice.save(update_fields=["status", "payment"])


@receiver(post_save, sender=SubscriptionRenewal)
def _invoice_for_renewal(sender, instance, created, **kwargs):
    """Whatever renewed the subscription, its payment gets an invoice (the open one, or a new paid one)."""
    if not created:
        return
    sub = instance.subscription
    payment = (sub.payments.filter(is_confirmed=True, invoice__isnull=True).order_by("-paid_on", "-id").first())
    if payment is None:
        return
    open_one = sub.invoices.filter(status="unpaid").order_by("period_start", "id").first()
    if open_one is not None:
        _settle(open_one, payment)
        return
    start = max(instance.previous_end_date, payment.paid_on)
    invoice = SubscriptionInvoice.objects.create(
        subscription=sub, issued_on=payment.paid_on, due_on=payment.paid_on, period_start=min(start, instance.new_end_date),
        period_end=instance.new_end_date, plan_name=sub.plan.name, amount=payment.amount, currency=sub.plan.currency,
        status="paid", payment=payment)
    _number(invoice)


# ------------------------------------------------------------------ the billing list

def _sub(qs, field, agg):
    """One aggregate per subscription as a subquery (two Sum joins in one query would double count)."""
    rows = (qs.filter(subscription=OuterRef("pk")).order_by().values("subscription")
            .annotate(v=agg(field)).values("v")[:1])
    return Subquery(rows)


def overview(*, show="all", q="", today=None):
    """One row per client subscription with expiry, money paid and money owed."""
    today = today or timezone.localdate()
    subs = (Subscription.objects.select_related("company", "plan", "company__business_type")
            .filter(company__is_active=True)
            .annotate(total_paid=_sub(SubscriptionPayment.objects.filter(is_confirmed=True), "amount", Sum),
                      last_paid=_sub(SubscriptionPayment.objects.filter(is_confirmed=True), "paid_on", Max),
                      unpaid=_sub(SubscriptionInvoice.objects.filter(status="unpaid"), "amount", Sum))
            .order_by("end_date"))
    if q:
        subs = subs.filter(Q(company__name__icontains=q) | Q(company__email__icontains=q) | Q(company__phone__icontains=q))
    rows = []
    for s in subs:
        days = (s.end_date - today).days
        state = "expired" if days < 0 else "trial" if s.status == "trial" else "expiring" if days <= EXPIRING_DAYS else "ok"
        row = {"s": s, "days": days, "state": state, "paid": s.total_paid or Decimal("0"),
               "unpaid": s.unpaid or Decimal("0"), "last_paid": s.last_paid}
        if show == "expiring" and not (0 <= days <= EXPIRING_DAYS):
            continue
        if show == "expired" and days >= 0:
            continue
        if show == "trial" and s.status != "trial":
            continue
        if show == "unpaid" and not row["unpaid"]:
            continue
        if show == "paying" and not row["paid"]:
            continue
        rows.append(row)
    return rows


def totals(today=None):
    today = today or timezone.localdate()
    confirmed = SubscriptionPayment.objects.filter(is_confirmed=True, subscription__company__is_active=True)
    live = Subscription.objects.filter(company__is_active=True)
    return {
        "month": confirmed.filter(paid_on__year=today.year, paid_on__month=today.month).aggregate(t=Sum("amount"))["t"] or 0,
        "year": confirmed.filter(paid_on__year=today.year).aggregate(t=Sum("amount"))["t"] or 0,
        "unpaid": SubscriptionInvoice.objects.filter(status="unpaid", subscription__company__is_active=True)
                  .aggregate(t=Sum("amount"))["t"] or 0,
        "expiring": live.filter(end_date__gte=today, end_date__lte=today + timedelta(days=EXPIRING_DAYS)).count(),
        "expired": live.filter(end_date__lt=today).count(),
        "waiting": SubscriptionPayment.objects.filter(is_confirmed=False).count(),
    }


def reminder_link(subscription, invoice=None, app_url=""):
    """WhatsApp message to the client about renewing (empty when the client has no phone)."""
    from apps.sales.sharing import normalise_phone
    company = subscription.company
    number = normalise_phone(company.phone, company.country)
    if not number:
        return ""
    amount = invoice.amount if invoice else price(subscription)
    currency = invoice.currency if invoice else subscription.plan.currency
    days = (subscription.end_date - timezone.localdate()).days
    when = (f"ends on {subscription.end_date:%d %b %Y}" if days >= 0
            else f"ended on {subscription.end_date:%d %b %Y}")
    text = (f"Hello {company.name}, your BookPilot {subscription.plan.name} subscription {when}. "
            f"Amount to renew: {currency} {amount:.2f}"
            + (f" (invoice {invoice.number})" if invoice else "") + ". "
            f"You can pay from Finance → Billing in the app{(': ' + app_url) if app_url else ''}. Thank you!")
    return f"https://wa.me/{number}?text={quote(text)}"

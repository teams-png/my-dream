"""Everything that must happen once a day, for every company, in one place.

Triggered by `python manage.py run_daily_jobs`, by the secured /cron/daily/ URL (a free GitHub Actions
schedule calls it every night) or by Celery beat where a worker runs. A second trigger on the same day
is a no-op unless forced.
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import DailyJobRun
from .rules import once, threshold_for, thresholds

log = logging.getLogger(__name__)


def remind_due_soon(company, today=None):
    """Customer bills and supplier bills that fall due within the configured days."""
    from apps.purchases.models import Purchase
    from apps.sales.models import SalesInvoice
    from .services import notify
    today = today or timezone.localdate()
    sent = 0
    for notif_type, qs, label in (
        ("customer_payment_due", SalesInvoice.objects.for_company(company).exclude(status__in=["paid", "void"]).select_related("customer"), "invoice"),
        ("supplier_payment_due", Purchase.objects.for_company(company).exclude(status="paid").select_related("supplier"), "bill"),
    ):
        days = thresholds(company, notif_type)
        if not days:
            continue
        for doc in qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=max(days))):
            outstanding = doc.total - doc.amount_paid
            if outstanding <= 0:
                continue
            left = (doc.due_date - today).days
            step = threshold_for(left, days)
            if step is None or not once(company, f"{label}:{doc.id}:due:{step}"):
                continue
            when = "today" if left == 0 else f"in {left} day{'s' if left != 1 else ''}"
            if label == "invoice":
                title = f"{doc.customer.name} should pay {doc.invoice_number} {when}"
            else:
                title = f"Pay {doc.supplier.name} (bill {doc.bill_number or doc.id}) {when}"
            notify(company=company, notif_type=notif_type, title=title,
                   message=f"Outstanding: {outstanding:.2f}. Due {doc.due_date:%d %b %Y}.")
            sent += 1
    return sent


def remind_memberships(company, today=None):
    from .services import notify
    try:
        from apps.verticals.gym.models import GymMember
    except ImportError:  # pragma: no cover
        return 0
    today = today or timezone.localdate()
    days = thresholds(company, "membership_expiry")
    if not days:
        return 0
    sent = 0
    for member in GymMember.objects.for_company(company).filter(
            status="active", membership_end__gte=today, membership_end__lte=today + timedelta(days=max(days))).select_related("customer"):
        left = (member.membership_end - today).days
        step = threshold_for(left, days)
        if step is not None and once(company, f"member:{member.id}:{member.membership_end}:{step}"):
            notify(company=company, notif_type="membership_expiry",
                   title=f"{member.customer.name}'s membership ends {'today' if left == 0 else f'in {left} days'}",
                   message=f"Ends {member.membership_end:%d %b %Y}. Phone: {member.customer.phone or '-'}")
            sent += 1
    return sent


def run_for_company(company):
    """The per-company part — also used by the 'Run checks now' button."""
    from apps.inventory.services import check_batch_expiry_and_notify
    from .services import check_low_stock_and_notify, check_overdue_invoices_and_notify
    result = {}
    for name, job in (("low_stock", check_low_stock_and_notify), ("overdue", check_overdue_invoices_and_notify),
                      ("batches", check_batch_expiry_and_notify), ("due_soon", remind_due_soon),
                      ("memberships", remind_memberships)):
        try:
            with transaction.atomic():
                value = job(company)
            result[name] = len(value) if isinstance(value, (list, tuple)) else value
        except Exception:  # one company's bad data must not stop the rest
            log.exception("daily job %s failed for company %s", name, company.pk)
            result[name] = "error"
    for hook in _extra_hooks:
        try:
            with transaction.atomic():
                result[hook.__name__] = hook(company)
        except Exception:
            log.exception("daily hook %s failed for company %s", hook.__name__, company.pk)
            result[hook.__name__] = "error"
    return result


_extra_hooks = []


def register(hook):
    """Other features (daily owner report, budgets) add a per-company job here."""
    if hook not in _extra_hooks:
        _extra_hooks.append(hook)
    return hook


def run_daily_jobs(force=False):
    from apps.tenants.models import Company
    today = timezone.localdate()
    if force:
        DailyJobRun.objects.filter(date=today).delete()
    try:
        with transaction.atomic():
            run = DailyJobRun.objects.create(date=today)
    except IntegrityError:
        return {"skipped": "already ran today"}
    summary = {"companies": 0}
    for job_name, job in (("subscriptions", "apps.subscriptions.services.run_daily_expiry_check"),
                          ("recurring_invoices", "apps.finance.services.run_all_recurring_invoices"),
                          ("cheque_reminders", "apps.finance.services.send_cheque_reminders"),
                          ("medicine_batches", "apps.verticals.medical_shop.tasks.check_medicine_batch_expiry"),
                          ("protein_batches", "apps.verticals.protein_shop.tasks.check_protein_batch_expiry")):
        module, func = job.rsplit(".", 1)
        try:
            value = getattr(__import__(module, fromlist=[func]), func)()
            summary[job_name] = value if isinstance(value, (int, str, dict)) else (len(value) if value is not None else 0)
        except Exception:
            log.exception("daily job %s failed", job_name)
            summary[job_name] = "error"
    for company in Company.objects.filter(is_active=True):
        run_for_company(company)
        summary["companies"] += 1
    run.finished_at = timezone.now()
    run.result = summary
    run.save(update_fields=["finished_at", "result"])
    return summary

"""
Free trials nobody paid for are cleaned up, with plenty of warning:

  trial ends  ─────────── DELETE_AFTER days ───────────▶ account closed ── GRACE days ──▶ deleted for good
               warnings at 14, 7, 3 and 1 day(s) left          (logins stop;            (all business data;
               (in-app + email to the owner)                    the platform admin       a one-line log is kept)
                                                                 can still restore)

Never touched: accounts that ever paid, accounts the platform admin marked "Keep", the platform's own demo
accounts. Choosing a plan at any point before the final step stops it.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import AccountRetention, DeletedAccountLog, Subscription, SubscriptionPayment

log = logging.getLogger(__name__)
WARN_DAYS = (14, 7, 3, 1)


def delete_after():
    return int(getattr(settings, "TRIAL_DELETE_AFTER_DAYS", 30))


def grace_days():
    return int(getattr(settings, "TRIAL_PURGE_GRACE_DAYS", 7))


def ever_paid(subscription):
    return SubscriptionPayment.objects.filter(subscription=subscription, is_confirmed=True, amount__gt=0).exists()


def _trial_end(sub):
    return sub.trial_ends_at or sub.end_date


def kept(company):
    r = AccountRetention.objects.filter(company=company).first()
    return bool(r and r.keep)


def _is_demo(company):
    return bool(getattr(company, "is_demo", False))


def applies(sub):
    """True when this subscription is an unpaid, ended trial that will be deleted."""
    if sub is None or sub.status not in ("trial", "expired"):
        return False
    end = _trial_end(sub)
    if end is None or end >= timezone.localdate():
        return False
    company = sub.company
    return not (ever_paid(sub) or kept(company) or _is_demo(company))


def delete_on(sub):
    """The day the account closes, or None when it never will."""
    return _trial_end(sub) + timedelta(days=delete_after()) if applies(sub) else None


def _owner(company):
    m = company.memberships.select_related("user").filter(role__name="Owner").first()
    return m.user if m else None


def _email(company, subject, lines):
    from django.core.mail import send_mail
    from apps.notifications.services import email_configured
    user = _owner(company)
    if not user or not user.email or not email_configured():
        return
    body = "\n\n".join([_("Hi %(name)s,") % {"name": user.first_name or user.email}] + lines + ["— BookPilot"])
    try:
        send_mail(subject, body, None, [user.email], fail_silently=False)
    except Exception:
        log.exception("retention email to company %s failed", company.pk)


def _site():
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def warn(company, sub, days_left, when):
    """One warning per step (in the app and by email)."""
    from django.urls import reverse
    from apps.notifications.rules import once
    from apps.notifications.services import notify
    if not once(company, f"trial-delete-warning:{days_left}:{when.isoformat()}"):
        return 0
    title = _("Your BookPilot account will be deleted on %(date)s") % {"date": when.strftime("%d %b %Y")}
    message = _("Your free trial has ended. Choose a plan to keep your products, customers and bills — or download your data before %(date)s.") % {"date": when.strftime("%d %b %Y")}  # noqa: E501
    try:
        notify(company=company, title=title, message=message, notif_type="subscription_expiring")
    except Exception:
        log.exception("retention notification failed for company %s", company.pk)
    _email(company, title, [message, _("Choose a plan: %(url)s") % {"url": _site() + reverse("webapp:billing")},
                            _("Download your data: %(url)s") % {"url": _site() + reverse("webapp:export_data")}])
    return 1


@transaction.atomic
def close(company, sub):
    """Day 1 of the end: logins stop, data is still there for the grace days."""
    retention, _created = AccountRetention.objects.get_or_create(company=company)
    if retention.closed_at:
        return 0
    now = timezone.now()
    retention.closed_at, retention.purge_on = now, timezone.localdate() + timedelta(days=grace_days())
    retention.note = "Unpaid trial — closed automatically"
    retention.save(update_fields=["closed_at", "purge_on", "note"])
    company.is_active = False
    company.archived_at = now
    company.save(update_fields=["is_active", "archived_at"])
    _email(company, _("Your BookPilot account has been closed"), [
        _("Your free trial ended and no plan was chosen, so the account %(shop)s is now closed.") % {"shop": company.name},
        _("It will be deleted for good on %(date)s. To keep it, reply to this email before then.") % {
            "date": retention.purge_on.strftime("%d %b %Y")}])
    return 1


def purge(company, reason="Unpaid trial"):
    """Deletes a company and everything it owns. Returns True when done."""
    from django.apps import apps as django_apps
    from apps.tenants.models import Company
    owner = _owner(company)
    sub = Subscription.objects.filter(company=company).first()
    entry = DeletedAccountLog(company_name=company.name[:255], owner_email=(owner.email if owner else "")[:254],
                              business_type=getattr(company.business_type, "code", "")[:60],
                              trial_ended=_trial_end(sub) if sub else None, reason=reason[:120])
    users = list(company.memberships.values_list("user_id", flat=True))
    try:  # our private backup files go too (a copy the owner put in their own Google Drive stays theirs)
        from apps.tenants import backups
        from apps.tenants.models import CompanyBackup
        for b in CompanyBackup.objects.filter(company=company).exclude(file_name=""):
            backups.storage().delete(b.file_name)
    except Exception:
        log.exception("could not remove backup files of company %s", company.pk)
    # tables that point at the company, deleted in rounds so PROTECT links between them sort themselves out
    models = [m for m in django_apps.get_models() if m is not Company and any(
        getattr(f, "related_model", None) is Company and f.many_to_one for f in m._meta.get_fields())]
    for _round in range(8):
        left = 0
        for model in models:
            fields = [f.name for f in model._meta.get_fields()
                      if getattr(f, "related_model", None) is Company and f.many_to_one]
            for name in fields:
                qs = model._base_manager.filter(**{name: company})
                if not qs.exists():
                    continue
                try:
                    with transaction.atomic():
                        qs.delete()
                except ProtectedError:
                    left += 1
        if not left:
            break
    try:
        with transaction.atomic():
            Company._base_manager.filter(pk=company.pk).delete()
    except ProtectedError:
        log.error("company %s could not be deleted completely", company.pk)
        return False
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(id__in=users, is_superuser=False):
        if not user.memberships.exists() and not getattr(user, "is_platform_admin", False):
            user.delete()  # the login of someone who had only this business
    entry.save()
    return True


def run_daily():
    """Daily job: warn, close and finally delete unpaid trials. Returns counts."""
    from apps.tenants.models import Company
    today = timezone.localdate()
    counts = {"warned": 0, "closed": 0, "deleted": 0}
    for sub in Subscription.objects.filter(status__in=("trial", "expired")).select_related("company"):
        company = sub.company
        if not company.is_active:
            continue
        when = delete_on(sub)
        if when is None:
            continue
        left = (when - today).days
        if left <= 0:
            counts["closed"] += close(company, sub)
        elif left in WARN_DAYS:
            counts["warned"] += warn(company, sub, left, when)
    for retention in AccountRetention.objects.filter(closed_at__isnull=False, purge_on__lte=today, keep=False):
        company = Company._base_manager.filter(pk=retention.company_id, is_active=False).first()
        sub = Subscription.objects.filter(company_id=retention.company_id).first()
        if company is None or (sub and ever_paid(sub)):
            continue
        if purge(company):
            counts["deleted"] += 1
    return counts


def restore(company):
    """Platform admin: reopen a closed trial and stop the countdown (marks it Keep)."""
    retention, _created = AccountRetention.objects.get_or_create(company=company)
    retention.keep, retention.closed_at, retention.purge_on = True, None, None
    retention.note = "Restored by the platform admin"
    retention.save()
    company.is_active = True
    company.archived_at = None
    company.save(update_fields=["is_active", "archived_at"])

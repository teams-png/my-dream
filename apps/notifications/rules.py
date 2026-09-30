"""Per-company reminder rules: how many days ahead to warn for each kind of event, and whether to email.

NotificationRule rows hold the owner's choice; without rows the defaults below apply. A rule row with
days_before=0 on an event that has no "days ahead" (low stock, overdue) only carries the email choice.
"""
from django.utils.translation import gettext_lazy as _

from .models import NotificationRule, ReminderLog

# type: (label, help, default days or None when days don't apply)
RULE_TYPES = {
    "customer_payment_due": (_("Customer bills due"), _("Remind before a customer's bill is due"), [3, 0]),
    "supplier_payment_due": (_("Supplier bills due"), _("Remind before you must pay a supplier"), [3, 0]),
    "product_expiry": (_("Stock expiring"), _("Batches with stock that will expire"), [30]),
    "membership_expiry": (_("Memberships ending"), _("Gym / club memberships about to end"), [7, 3, 1]),
    "subscription_expiring": (_("Your BookPilot plan"), _("Before your own subscription ends"), [30, 15, 7, 3, 1]),
    "invoice_overdue": (_("Overdue bills"), _("Customer or supplier bills past their due date"), None),
    "low_stock": (_("Low stock"), _("Items at or below their reorder level"), None),
}


def thresholds(company, notif_type):
    """Days-before list, largest first."""
    days = sorted({r for r in NotificationRule.objects.filter(company=company, notif_type=notif_type)
                   .values_list("days_before", flat=True)}, reverse=True)
    if days:
        return days
    default = RULE_TYPES.get(notif_type, (None, None, None))[2]
    return sorted(default or [], reverse=True)


def email_enabled(company, notif_type):
    rules = list(NotificationRule.objects.filter(company=company, notif_type=notif_type).values_list("also_email", flat=True))
    return any(rules) if rules else True


def threshold_for(days_left, days):
    """The smallest configured threshold that days_left has reached, or None (e.g. days [15, 7, 1], 5 days left -> 7)."""
    reached = [d for d in days if days_left <= d]
    return min(reached) if reached else None


def once(company, key):
    """True the first time a reminder key is seen for this company."""
    _obj, created = ReminderLog.objects.get_or_create(company=company, key=key[:120])
    return created


def save_rules(company, notif_type, days, also_email):
    NotificationRule.objects.filter(company=company, notif_type=notif_type).delete()
    values = sorted(set(days)) or [0]
    NotificationRule.objects.bulk_create([NotificationRule(company=company, notif_type=notif_type, days_before=d,
                                                           also_email=also_email) for d in values])

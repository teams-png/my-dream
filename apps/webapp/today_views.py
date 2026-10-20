"""Today: the owner's one-page morning check, made for the phone — today's numbers and work, who owes money
(with a WhatsApp reminder ready to send) and documents running out."""
from datetime import timedelta
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from .industry_access import company_features
from .role_access import can_open


def _wa(phone, text):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}" if digits else ""


def _overdue(company, today):
    from apps.sales.models import SalesInvoice
    rows = (SalesInvoice.objects.for_company(company).filter(status__in=["unpaid", "partial"], due_date__lt=today)
            .select_related("customer").order_by("due_date")[:8])
    out = []
    for i in rows:
        due = i.total - i.amount_paid
        text = _("Hello %(name)s, a friendly reminder from %(shop)s: invoice %(no)s of %(cur)s %(amount)s was due on %(date)s. Thank you!") % {  # noqa: E501
            "name": i.customer.name, "shop": company.name, "no": i.invoice_number, "cur": i.currency,
            "amount": f"{due:.2f}", "date": f"{i.due_date:%d %b}"}
        days = (today - i.due_date).days
        out.append({"invoice": i, "due": due, "late": _("%(n)s days late") % {"n": days},
                    "whatsapp": _wa(i.customer.phone, text)})
    return out


def _expiring(company, today, features):
    from apps.employees.models import EmployeeDocument
    soon = today + timedelta(days=30)
    rows = [{"who": d.employee.name, "what": d.document_type, "date": d.expiry_date, "late": d.expiry_date < today}
            for d in EmployeeDocument.objects.for_company(company)
            .filter(employee__is_active=True, expiry_date__isnull=False, expiry_date__lte=soon)
            .select_related("employee").order_by("expiry_date")[:8]]
    if "recruitment" in features:
        from apps.industry.models import Candidate
        rows += [{"who": c.name, "what": _("Passport"), "date": c.passport_expiry, "late": c.passport_expiry < today}
                 for c in Candidate.objects.for_company(company).exclude(status__in=["placed", "not_suitable"])
                 .filter(passport_expiry__isnull=False, passport_expiry__lte=today + timedelta(days=90))
                 .order_by("passport_expiry")[:5]]
    return sorted(rows, key=lambda r: r["date"])[:10]


@login_required
def today(request):
    from . import overview
    company = getattr(request, "company", None)
    if company is None:
        return render(request, "webapp/no_company.html")
    now = timezone.localdate()
    data = overview.limit_links(overview.build(company), request)
    can_reports = can_open(request, "analytics")
    return render(request, "webapp/today.html", {
        "today": now, "greeting": overview.greeting(),
        "kpis": [k for k in data["kpis"] if not k.get("reports") or can_reports],
        "main": data["main"], "side": data["side"],
        "overdue": _overdue(company, now) if can_open(request, "receivables") else [],
        "expiring": _expiring(company, now, company_features(company)),
    })


# ------------------------------------------------------------------ bell (top bar) and suggestions (overview)

@login_required
def notification_feed(request):
    """The bell's dropdown: the latest notifications for this member and how many are unread."""
    from django.db.models import Q
    from django.http import JsonResponse
    from apps.notifications.models import Notification
    company = getattr(request, "company", None)
    if company is None:
        return JsonResponse({"unread": 0, "items": []})
    mine = Notification.objects.filter(company=company).filter(Q(recipient=request.user) | Q(recipient__isnull=True))
    items = [{"title": n.title, "message": n.message[:140], "read": n.is_read,
              "when": timezone.localtime(n.created_at).strftime("%d %b %H:%M")} for n in mine.order_by("-created_at")[:6]]
    return JsonResponse({"unread": mine.filter(is_read=False).count(), "items": items})


def suggestions(company, request):
    """A few next steps worth doing today, each with the page that does it (only pages the member may open)."""
    from django.db.models import Max
    from django.urls import reverse
    from apps.customers.models import Customer
    from apps.sales.models import SalesInvoice
    from .overview import _low_stock
    today = timezone.localdate()
    out = []
    late = SalesInvoice.objects.for_company(company).filter(status__in=["unpaid", "partial"], due_date__lt=today).count()
    if late and can_open(request, "today"):
        out.append(("💵", _("Invoices past their due date: %(n)s — send reminders.") % {"n": late}, reverse("webapp:today")))
    quiet = (Customer.objects.for_company(company).exclude(phone="").annotate(last=Max("salesinvoice__date"))
             .filter(last__lt=today - timedelta(days=60)).count())
    if quiet and can_open(request, "reminders"):
        out.append(("👋", _("Customers who haven't bought in 2 months: %(n)s — send an offer?") % {"n": quiet},
                    reverse("webapp:reminders")))
    low = len(_low_stock(company))
    if low and can_open(request, "stock_home"):
        out.append(("📦", _("Products running low: %(n)s — time to reorder.") % {"n": low},
                    reverse("webapp:stock_home") + "?show=low"))
    return out[:3]

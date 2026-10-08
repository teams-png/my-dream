"""End-of-day summary for the owner: sales, money in, costs, profit, cash, what customers owe, what is due."""
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Sum
from django.utils import timezone

from .daily import register
from .models import DailyReportSettings

ZERO = Decimal("0")


def report_day(now=None):
    """The day to report on: today, or yesterday when the job runs just after midnight."""
    now = timezone.localtime(now or timezone.now())
    return now.date() - timedelta(days=1) if now.hour < 6 else now.date()


def build_summary(company, day):
    from apps.accounting.models import Account
    from apps.accounting.services import account_balance, profit_and_loss
    from apps.expenses.models import Expense
    from apps.inventory.models import Product
    from apps.purchases.models import Purchase
    from apps.sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine
    from apps.collections.services import ar_ageing_summary

    invoices = SalesInvoice.objects.for_company(company).filter(date=day).exclude(status="void")
    sales = invoices.aggregate(t=Sum("total"), n=Count("id"))
    pl_day = profit_and_loss(company, date_from=day, date_to=day)
    pl_month = profit_and_loss(company, date_from=day.replace(day=1), date_to=day)
    cash = {code: account_balance(a) for a in Account.objects.for_company(company).filter(code__in=["1000", "1010"]) for code in [a.code]}
    ageing = ar_ageing_summary(company, as_of=day)
    overdue = sum((b["total"] for b in ageing["buckets"]), ZERO) + ageing["unbucketed_overdue"]
    bills_due = Purchase.objects.for_company(company).exclude(status="paid").filter(due_date__lte=day + timedelta(days=7))
    bills_due_total = sum((p.total - p.amount_paid for p in bills_due), ZERO)
    top = list(SalesInvoiceLine.objects.filter(invoice__in=invoices).values("product__name")
               .annotate(q=Sum("quantity"), t=Sum("line_total")).order_by("-t")[:5])
    low = [p for p in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)[:2000]
           if p.current_stock() <= p.reorder_level]
    expenses = Expense.objects.for_company(company).filter(date=day).aggregate(t=Sum("amount"))["t"] or ZERO
    return {
        "day": day, "company": company, "currency": getattr(company, "default_currency", ""),
        "sales": sales["t"] or ZERO, "bills": sales["n"] or 0,
        "received": CustomerPayment.objects.for_company(company).filter(date=day).aggregate(t=Sum("amount"))["t"] or ZERO,
        "expenses": expenses, "profit": pl_day["net_profit"], "month_sales": pl_month["total_income"],
        "month_profit": pl_month["net_profit"], "cash": cash.get("1000", ZERO), "bank": cash.get("1010", ZERO),
        "receivable": ageing["total_outstanding"], "overdue": overdue, "bills_due": bills_due_total,
        "top": top, "low_stock": len(low), "low_names": [p.name for p in low[:5]],
    }


def summary_text(s):
    cur = s["currency"]
    lines = [f"📊 {s['company'].name} — {s['day']:%a %d %b %Y}",
             f"Sales: {cur} {s['sales']:.2f} ({s['bills']} bills)",
             f"Money received: {cur} {s['received']:.2f}",
             f"Expenses: {cur} {s['expenses']:.2f}",
             f"Profit today: {cur} {s['profit']:.2f}",
             f"This month: sales {cur} {s['month_sales']:.2f}, profit {cur} {s['month_profit']:.2f}",
             f"Cash: {cur} {s['cash']:.2f} · Bank: {cur} {s['bank']:.2f}",
             f"Customers owe: {cur} {s['receivable']:.2f} (overdue {cur} {s['overdue']:.2f})",
             f"Supplier bills due in 7 days: {cur} {s['bills_due']:.2f}"]
    if s["top"]:
        lines.append("Top items: " + ", ".join(f"{t['product__name']} ({t['t']:.0f})" for t in s["top"]))
    if s["low_stock"]:
        lines.append(f"Low stock: {s['low_stock']} items (" + ", ".join(s["low_names"]) + ")")
    return "\n".join(lines)


def whatsapp_link(company, text):
    number = "".join(ch for ch in (DailyReportSettings.load(company).whatsapp_number or "") if ch.isdigit())
    return f"https://wa.me/{number}?text={quote(text)}"


def recipients(company, prefs):
    owners = [m.user.email for m in company.memberships.filter(is_active=True, role__name="Owner").select_related("user")
              if m.user.email]
    extra = [e.strip() for e in (prefs.emails or "").replace(";", ",").split(",") if "@" in e]
    return list(dict.fromkeys(owners + extra))


def send_daily_report(company, day=None, force=False):
    """Emails the summary and adds it to Notifications. Returns the number of emails sent (or a skip reason)."""
    from .models import Notification
    prefs = DailyReportSettings.load(company)
    day = day or report_day()
    if not force and (not prefs.enabled or prefs.last_sent_on == day):
        return "skipped"
    summary = build_summary(company, day)
    text = summary_text(summary)
    Notification.objects.create(company=company, notif_type="general", title=f"Daily report {day:%d %b}", message=text)
    to = recipients(company, prefs)
    sent = 0
    if to:
        try:
            send_mail(f"{company.name} — daily report {day:%d %b %Y}", text,
                      getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"), to)
            sent = len(to)
        except Exception:  # email not configured: the in-app copy is still there
            sent = 0
    prefs.last_sent_on = day
    prefs.save(update_fields=["last_sent_on"])
    return sent


@register
def daily_owner_report(company):
    return send_daily_report(company)


@register
def recruitment_reminders(company):
    from apps.industry.recruitment import daily_reminders
    return daily_reminders(company)


@register
def trial_emails(company):
    from apps.subscriptions.trial_emails import daily
    return daily(company)

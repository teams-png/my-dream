"""Reminder rules, the daily-jobs trigger (cron URL) and other automation settings."""
import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.notifications import rules as reminder_rules
from apps.notifications.daily import run_daily_jobs, run_for_company
from apps.notifications.models import DailyJobRun, NotificationRule

from .views import require_permission


@csrf_exempt
@require_POST
def cron_daily(request):
    """Called every night by the scheduled GitHub Action (or any cron). Needs the CRON_SECRET."""
    secret = getattr(settings, "CRON_SECRET", "")
    given = request.headers.get("X-Cron-Key", "")
    if not secret or not hmac.compare_digest(secret, given):
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(run_daily_jobs(force=request.GET.get("force") == "1"))


@login_required
@require_permission("accounting.view_reports")
def reminder_settings(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        if request.POST.get("action") == "run":
            result = run_for_company(company)
            messages.success(request, _("Checks finished. New reminders are in Notifications.") + f" ({result.get('due_soon', 0)}/{result.get('batches', 0)})")
            return redirect("webapp:reminder_settings")
        for key, (_label, _help, default) in reminder_rules.RULE_TYPES.items():
            email = bool(request.POST.get(f"email_{key}"))
            days = []
            if default is not None:
                for part in (request.POST.get(f"days_{key}") or "").replace(" ", "").split(","):
                    if part.isdigit() and int(part) <= 365:
                        days.append(int(part))
            reminder_rules.save_rules(company, key, days, email)
        messages.success(request, _("Reminder settings saved."))
        return redirect("webapp:reminder_settings")
    rows = []
    for key, (label, help_text, default) in reminder_rules.RULE_TYPES.items():
        has_rules = NotificationRule.objects.filter(company=company, notif_type=key).exists()
        rows.append({"key": key, "label": label, "help": help_text, "uses_days": default is not None,
                     "days": ", ".join(str(d) for d in sorted(reminder_rules.thresholds(company, key), reverse=True)),
                     "email": reminder_rules.email_enabled(company, key), "custom": has_rules})
    return render(request, "webapp/automation/reminders.html", {
        "rows": rows, "last_run": DailyJobRun.objects.order_by("-date").first()})


@login_required
@require_permission("accounting.view_reports")
def daily_report(request):
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    from apps.notifications import daily_report as dr
    from apps.notifications.models import DailyReportSettings

    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    prefs = DailyReportSettings.load(company)
    day = parse_date(request.GET.get("date") or "") or timezone.localdate()
    if request.method == "POST":
        if request.POST.get("action") == "send":
            sent = dr.send_daily_report(company, day=day, force=True)
            messages.success(request, _("Report sent to %(count)s email address(es) and saved in Notifications.") % {"count": sent}
                             if isinstance(sent, int) else _("Report saved."))
        else:
            prefs.enabled = bool(request.POST.get("enabled"))
            prefs.emails = (request.POST.get("emails") or "")[:1000]
            prefs.whatsapp_number = (request.POST.get("whatsapp") or "")[:30]
            prefs.save(update_fields=["enabled", "emails", "whatsapp_number"])
            messages.success(request, _("Daily report settings saved."))
        return redirect(f"{request.path}?date={day.isoformat()}")
    summary = dr.build_summary(company, day)
    text = dr.summary_text(summary)
    return render(request, "webapp/automation/daily_report.html", {
        "s": summary, "prefs": prefs, "whatsapp": dr.whatsapp_link(company, text), "text": text,
        "owners": dr.recipients(company, DailyReportSettings(company=company)),
        "prev": day - timedelta(days=1), "next": day + timedelta(days=1), "today": timezone.localdate()})


@login_required
@require_permission("expenses.manage")
def budgets(request):
    from decimal import Decimal, InvalidOperation

    from django.utils import timezone
    from django.utils.dateparse import parse_date

    from apps.expenses.budgets import month_rows
    from apps.expenses.models import ExpenseBudget, ExpenseCategory

    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    day = parse_date((request.GET.get("m") or "") + "-01") or timezone.localdate()
    if request.method == "POST":
        saved = 0
        for category in ExpenseCategory.objects.for_company(company):
            raw = (request.POST.get(f"b_{category.id}") or "").strip()
            try:
                amount = Decimal(raw) if raw else None
                alert = min(max(int(request.POST.get(f"a_{category.id}") or 80), 1), 100)
            except (InvalidOperation, ValueError):
                continue
            if amount is None or amount <= 0:
                ExpenseBudget.objects.filter(company=company, category=category).delete()
            else:
                ExpenseBudget.objects.update_or_create(company=company, category=category,
                                                       defaults={"monthly_amount": amount, "alert_percent": alert})
                saved += 1
        messages.success(request, _("%(count)s budgets saved.") % {"count": saved})
        return redirect("webapp:budgets")
    rows = month_rows(company, day)
    budgeted = [r for r in rows if r["budget"]]
    first = day.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return render(request, "webapp/automation/budgets.html", {
        "rows": rows, "month": first, "prev": prev, "next": nxt,
        "total_budget": sum((r["budget"].monthly_amount for r in budgeted), Decimal("0")),
        "total_spent": sum((r["spent"] for r in rows), Decimal("0")),
        "over": sum(1 for r in rows if r["state"] == "over")})

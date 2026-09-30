"""Reminder rules, the daily-jobs trigger (cron URL) and other automation settings."""
import hmac

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

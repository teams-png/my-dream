"""Customers to remind today (revisit, membership ending), each with a one-tap WhatsApp message."""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.industry import reminders
from apps.industry.models import CustomerReminder


@login_required
def reminder_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    try:
        days = max(1, min(365, int(request.GET["days"])))
    except (KeyError, ValueError):
        days = reminders.revisit_days(company)
    return render(request, "webapp/reminders.html", {
        "rows": reminders.due(company, days), "days": days, "quiet_days": reminders.QUIET_DAYS,
        "sent_today": CustomerReminder.objects.for_company(company).filter(sent_at__date=timezone.localdate()).count(),
    })


@login_required
@require_POST
def reminder_sent(request):
    company = request.company
    kind = request.POST.get("kind")
    if company is None or kind not in ("revisit", "membership"):
        return JsonResponse({"ok": False}, status=400)
    customer = get_object_or_404(Customer.objects.for_company(company), id=request.POST.get("customer_id") or 0)
    CustomerReminder.objects.create(company=company, customer=customer, kind=kind, sent_by=request.user)
    return JsonResponse({"ok": True})

"""Restaurant order history: every order (paid, open or cancelled) with filters."""
from datetime import timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _

from apps.verticals.restaurant.models import RestaurantOrder

from django.contrib.auth.decorators import login_required

from .views import require_business_group, require_permission

OPEN_STATUSES = ["draft", "held", "kitchen", "ready", "served"]
STATUS_TABS = [("all", _("All")), ("paid", _("Paid")), ("open", _("Open")), ("cancelled", _("Cancelled"))]
PERIODS = [("today", _("Today")), ("yesterday", _("Yesterday")), ("7d", _("Last 7 days")), ("30d", _("Last 30 days")), ("all", _("All time"))]


def _date_range(request, today):
    period = request.GET.get("period") or "today"
    start = parse_date(request.GET.get("from") or "")
    end = parse_date(request.GET.get("to") or "")
    if start or end:
        return "custom", start, end
    if period == "yesterday":
        day = today - timedelta(days=1)
        return period, day, day
    if period == "7d":
        return period, today - timedelta(days=6), today
    if period == "30d":
        return period, today - timedelta(days=29), today
    if period == "all":
        return period, None, None
    return "today", today, today


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_order_list(request):
    company = request.company
    today = timezone.localdate()
    period, start, end = _date_range(request, today)
    status = request.GET.get("status") or "all"
    channel = request.GET.get("channel") or ""
    query = (request.GET.get("q") or "").strip()

    orders = RestaurantOrder.objects.for_company(company)
    if start:
        orders = orders.filter(created_at__date__gte=start)
    if end:
        orders = orders.filter(created_at__date__lte=end)
    if channel in dict(RestaurantOrder.CHANNELS):
        orders = orders.filter(channel=channel)
    if query:
        orders = orders.filter(Q(order_number__icontains=query) | Q(invoice__invoice_number__icontains=query)
                               | Q(customer__name__icontains=query) | Q(customer__phone__icontains=query)
                               | Q(table__name__icontains=query))
    # counts for the status tabs use every other filter
    counts = {row["status"]: row["n"] for row in orders.values("status").annotate(n=Count("id"))}
    tab_counts = {"all": sum(counts.values()), "paid": counts.get("paid", 0), "cancelled": counts.get("cancelled", 0),
                  "open": sum(counts.get(s, 0) for s in OPEN_STATUSES)}
    paid = orders.filter(status="paid")
    summary = {"sales": paid.aggregate(t=Sum("invoice__total"))["t"] or Decimal("0"), "paid": tab_counts["paid"],
               "open": tab_counts["open"], "cancelled": tab_counts["cancelled"]}
    summary["average"] = (summary["sales"] / summary["paid"]).quantize(Decimal("0.01")) if summary["paid"] else Decimal("0")

    if status == "paid":
        orders = paid
    elif status == "open":
        orders = orders.filter(status__in=OPEN_STATUSES)
    elif status == "cancelled":
        orders = orders.filter(status="cancelled")
    else:
        status = "all"
    orders = (orders.select_related("table", "customer", "waiter", "invoice")
              .prefetch_related("lines__modifiers", "invoice__payments").order_by("-created_at"))
    page = Paginator(orders, 40).get_page(request.GET.get("page"))
    for order in page:
        order.item_count = sum(line.quantity for line in order.lines.all())
        order.methods = sorted({p.method for p in order.invoice.payments.all()}) if order.invoice_id else []
        order.bill_total = order.invoice.total if order.invoice_id else order.total

    def link(**changes):
        params = request.GET.copy()
        params.pop("page", None)
        for key, value in changes.items():
            params.pop(key, None)
            if value:
                params[key] = value
        return "?" + params.urlencode()

    return render(request, "webapp/restaurant/order_list.html", {
        "page": page, "summary": summary, "status": status, "period": period, "channel": channel, "q": query,
        "start": start, "end": end, "tabs": [(k, label, tab_counts[k], link(status=k)) for k, label in STATUS_TABS],
        "periods": [(k, label, link(period=k, **{"from": "", "to": ""})) for k, label in PERIODS],
        "channels": RestaurantOrder.CHANNELS, "page_link": link(),
    })

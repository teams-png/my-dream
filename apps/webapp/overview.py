"""What the Overview page shows first: today's numbers, today's work list and a second list, per business type.

build(company) returns {"kpis": [...], "main": panel or None, "side": panel or None}.
A KPI is {label, value, url, tone, note, reports}; reports=True means only people who may see reports get it.
A panel is {title, url, link_label, rows, empty, empty_url, empty_label, kind}; the template draws rows by kind.
Business types without their own panels yet get the money tiles and keep the older "Business overview" tiles.
"""
from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

# business type -> (appointment model path, staff field, appointment list, complete url, book url)
APPOINTMENTS = {
    "saloon": ("apps.verticals.saloon.models", "stylist", "webapp:saloon_appointment_list",
               "webapp:saloon_appointment_complete", "webapp:saloon_appointment_book"),
    "spa": ("apps.verticals.spa.models", "therapist", "webapp:appointment_list",
            "webapp:appointment_complete", "webapp:appointment_book"),
    "beauty_parlour": ("apps.verticals.beauty_parlour.models", "beautician", "webapp:beauty_appointment_list",
                       "webapp:beauty_appointment_complete", "webapp:beauty_appointment_book"),
}
APPOINTMENTS["barber_shop"] = APPOINTMENTS["saloon"]
APPOINTMENTS["beauty_salon"] = APPOINTMENTS["beauty_parlour"]


def _invoices(company):
    from apps.sales.models import SalesInvoice
    return SalesInvoice.objects.for_company(company).exclude(status="void")


def _kpi(label, value, url, *, tone="", note="", reports=False):
    return {"label": label, "value": value, "url": url, "tone": tone, "note": note, "reports": reports}


def _money_kpis(company, today):
    """Today's sales, this month, and the dues / low-stock warnings — what every business has."""
    from apps.inventory.models import Product
    invoices = _invoices(company)
    month_start = today.replace(day=1)
    bills = reverse("webapp:sales_invoice_list")
    totals = invoices.aggregate(total=Sum("total"), paid=Sum("amount_paid"))
    dues = (totals["total"] or 0) - (totals["paid"] or 0)
    low = sum(1 for p in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
              if p.current_stock() <= p.reorder_level)
    return {
        "today": _kpi(_("Today's sales"), invoices.filter(date=today).aggregate(t=Sum("total"))["t"] or 0,
                      f"{bills}?from={today:%Y-%m-%d}&to={today:%Y-%m-%d}", tone="money"),
        "month": _kpi(_("This month's revenue"), invoices.filter(date__gte=month_start).aggregate(t=Sum("total"))["t"] or 0,
                      f"{bills}?from={month_start:%Y-%m-%d}&to={today:%Y-%m-%d}", tone="money", reports=True),
        "dues": _kpi(_("Outstanding dues"), dues, reverse("webapp:receivables"),
                     tone="warn money" if dues > 0 else "money"),
        "low": _kpi(_("Low stock items"), low, reverse("webapp:stock_home") + "?show=low", tone="bad" if low else ""),
    }


def _appointments(company, code, today):
    import importlib
    module, staff_field, list_url, done_url, book_url = APPOINTMENTS[code]
    model = importlib.import_module(module).Appointment
    todays = (model.objects.for_company(company).filter(scheduled_at__date=today)
              .exclude(status="cancelled").select_related("customer", "service", staff_field).order_by("scheduled_at"))
    rows = []
    for a in todays:
        staff = getattr(a, staff_field)
        rows.append({"time": timezone.localtime(a.scheduled_at), "customer": a.customer.name, "service": a.service.name,
                     "staff": staff.name if staff else "", "status": a.status, "status_label": a.get_status_display(),
                     "done_url": reverse(done_url, args=[a.id]) + "?next=overview" if a.status == "booked" else ""})
    left = sum(1 for r in rows if r["status"] == "booked")
    done = sum(1 for r in rows if r["status"] == "completed")
    kpi = _kpi(_("Appointments today"), len(rows), reverse(list_url),
               note=_("%(left)s waiting · %(done)s done") % {"left": left, "done": done} if rows else "")
    panel = {"kind": "appointments", "title": _("Today's appointments"), "url": reverse(list_url),
             "link_label": _("All appointments"), "rows": rows[:12], "more": max(0, len(rows) - 12),
             "empty": _("No appointments today."), "empty_url": reverse(book_url), "empty_label": _("Book appointment")}
    return kpi, panel


def _staff_today(company, today):
    rows = (_invoices(company).filter(date=today, served_by__isnull=False).values("served_by__name")
            .annotate(bills=Count("id"), amount=Sum("total")).order_by("-amount"))
    return {"kind": "staff", "title": _("Staff today"), "url": reverse("webapp:staff_list"),
            "link_label": _("Staff"), "more": 0,
            "rows": [{"name": r["served_by__name"], "bills": r["bills"], "amount": r["amount"] or 0} for r in rows],
            "empty": _("Choose who did the work when you bill, and each person's total shows here."),
            "empty_url": reverse("webapp:pos"), "empty_label": _("New bill")}


def build(company):
    code = company.business_type.code if company.business_type_id else ""
    today = timezone.localdate()
    money = _money_kpis(company, today)
    if code in APPOINTMENTS:
        appt_kpi, main = _appointments(company, code, today)
        bills_today = _invoices(company).filter(date=today).count()
        kpis = [money["today"], appt_kpi,
                _kpi(_("Bills today"), bills_today, money["today"]["url"]), money["month"]]
        return {"kpis": kpis, "main": main, "side": _staff_today(company, today), "own_layout": True}
    return {"kpis": [money["today"], money["month"], money["dues"], money["low"]], "main": None, "side": None,
            "own_layout": False}


def greeting(now=None):
    hour = timezone.localtime(now).hour
    if hour < 12:
        return _("Good morning")
    if hour < 17:
        return _("Good afternoon")
    return _("Good evening")


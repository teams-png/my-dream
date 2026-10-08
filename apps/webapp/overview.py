"""What the Overview page shows first: today's numbers, today's work list and a second list, per business type.

build(company) returns {"kpis": [...], "main": panel or None, "side": panel or None, "own_layout": bool}.
A KPI is {label, value, url, tone, note, reports}; reports=True means only people who may see reports get it.
A panel is {title, url, link_label, rows, more, empty, empty_url, empty_label}. Every row is a dict with any of:
  lead (short text on the left, e.g. a time), title, sub, badge + tone, amount, url (the whole row),
  action_url + action_label (a button), since + target (a live kitchen-style timer: ISO start, target minutes).
Business types without their own lists (recruitment) keep the older "Business overview" tiles.
"""
import importlib
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.modules.catalog import ALIASES, business_features, business_group

# business type -> (appointment model path, staff field, appointment list, complete url, book url)
APPOINTMENTS = {
    "saloon": ("apps.verticals.saloon.models", "stylist", "webapp:saloon_appointment_list",
               "webapp:saloon_appointment_complete", "webapp:saloon_appointment_book"),
    "spa": ("apps.verticals.spa.models", "therapist", "webapp:appointment_list",
            "webapp:appointment_complete", "webapp:appointment_book"),
    "beauty_parlour": ("apps.verticals.beauty_parlour.models", "beautician", "webapp:beauty_appointment_list",
                       "webapp:beauty_appointment_complete", "webapp:beauty_appointment_book"),
}
KITCHEN_TARGET = 15  # minutes a ticket may take when its dishes have no preparation time
SHOW = 8  # rows per list


def _invoices(company):
    from apps.sales.models import SalesInvoice
    return SalesInvoice.objects.for_company(company).exclude(status="void")


def _kpi(label, value, url, *, tone="", note="", reports=False):
    return {"label": label, "value": value, "url": url, "tone": tone, "note": note, "reports": reports}


def _panel(title, url, link_label, rows, empty, empty_url="", empty_label=""):
    return {"title": title, "url": url, "link_label": link_label, "rows": rows[:SHOW], "more": max(0, len(rows) - SHOW),
            "empty": empty, "empty_url": empty_url, "empty_label": empty_label}


def _bills_url(start, end):
    return f"{reverse('webapp:sales_invoice_list')}?from={start:%Y-%m-%d}&to={end:%Y-%m-%d}"


def _money(company, today):
    """The numbers every business has: today's sales and bills, this month, dues and low stock."""
    invoices = _invoices(company)
    month_start = today.replace(day=1)
    todays = invoices.filter(date=today).aggregate(t=Sum("total"), n=Count("id"))
    totals = invoices.aggregate(total=Sum("total"), paid=Sum("amount_paid"))
    dues = (totals["total"] or 0) - (totals["paid"] or 0)
    low = len(_low_stock(company))
    return {
        "today": _kpi(_("Today's sales"), todays["t"] or 0, _bills_url(today, today), tone="money"),
        "bills": _kpi(_("Bills today"), todays["n"], _bills_url(today, today)),
        "month": _kpi(_("This month's revenue"), invoices.filter(date__gte=month_start).aggregate(t=Sum("total"))["t"] or 0,
                      _bills_url(month_start, today), tone="money", reports=True),
        "dues": _kpi(_("Outstanding dues"), dues, reverse("webapp:receivables"), tone="warn money" if dues > 0 else "money"),
        "low": _kpi(_("Low stock items"), low, reverse("webapp:stock_home") + "?show=low", tone="bad" if low else ""),
    }


def _low_stock(company):
    from apps.inventory.models import Product
    rows = []
    for p in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).select_related("unit"):
        stock = p.current_stock()
        if stock <= p.reorder_level:
            rows.append((stock, p))
    return sorted(rows, key=lambda r: r[0])


def _top_items(company, today):
    from apps.sales.models import SalesInvoiceLine
    rows = (SalesInvoiceLine.objects.filter(invoice__company=company, invoice__date=today).exclude(invoice__status="void")
            .values("product__name").annotate(qty=Sum("quantity"), amount=Sum("line_total")).order_by("-amount")[:SHOW])
    return _panel(_("Best sellers today"), reverse("webapp:analytics"), _("Reports"),
                  [{"title": r["product__name"].split(" — ")[-1], "sub": f"× {r['qty'].normalize():f}", "amount": r["amount"]}
                   for r in rows],
                  _("Nothing sold yet today."), reverse("webapp:pos"), _("New bill"))


def _staff_today(company, today):
    rows = (_invoices(company).filter(date=today, served_by__isnull=False).values("served_by__name")
            .annotate(bills=Count("id"), amount=Sum("total")).order_by("-amount"))
    return _panel(_("Staff today"), reverse("webapp:staff_list"), _("Staff"),
                  [{"title": r["served_by__name"], "sub": _("%(n)s bills") % {"n": r["bills"]}, "amount": r["amount"] or 0}
                   for r in rows],
                  _("Choose who did the work when you bill, and each person's total shows here."),
                  reverse("webapp:pos"), _("New bill"))


# ---------- one function per kind of business: returns (kpis, main, side) ----------

def _salon(company, code, today, money):
    module, staff_field, list_url, done_url, book_url = APPOINTMENTS[code]
    model = importlib.import_module(module).Appointment
    todays = (model.objects.for_company(company).filter(scheduled_at__date=today).exclude(status="cancelled")
              .select_related("customer", "service", staff_field).order_by("scheduled_at"))
    rows = []
    for a in todays:
        staff = getattr(a, staff_field)
        rows.append({"lead": f"{timezone.localtime(a.scheduled_at):%H:%M}", "title": a.customer.name,
                     "sub": " · ".join(x for x in (a.service.name, staff.name if staff else "") if x),
                     "badge": "" if a.status == "booked" else a.get_status_display(),
                     "tone": "ok" if a.status == "completed" else "bad" if a.status == "no_show" else "",
                     "action_url": reverse(done_url, args=[a.id]) + "?next=overview" if a.status == "booked" else "",
                     "action_label": "✓ " + _("Done")})
    left = sum(1 for a in todays if a.status == "booked")
    done = sum(1 for a in todays if a.status == "completed")
    kpi = _kpi(_("Appointments today"), len(rows), reverse(list_url),
               note=_("%(left)s waiting · %(done)s done") % {"left": left, "done": done} if rows else "")
    main = _panel(_("Today's appointments"), reverse(list_url), _("All appointments"), rows,
                  _("No appointments today."), reverse(book_url), _("Book appointment"))
    return [money["today"], kpi, money["bills"], money["month"]], main, _staff_today(company, today)


def kitchen_targets(company, tickets):
    """Minutes each kitchen ticket should take: its slowest dish (menu preparation time), else KITCHEN_TARGET."""
    from apps.verticals.restaurant.models import RestaurantMenuItem
    prep = dict(RestaurantMenuItem.objects.for_company(company).values_list("product_id", "preparation_minutes"))
    targets = {}
    for t in tickets:
        minutes = [prep.get(line.product_id) or 0 for line in t.order.lines.all() if line.kitchen_round == t.kitchen_round]
        targets[t.id] = max(minutes + [0]) or KITCHEN_TARGET
    return targets


def _restaurant(company, today, money):
    from apps.verticals.restaurant.models import KitchenTicket, RestaurantOrder, RestaurantOrderLine
    orders = RestaurantOrder.objects.for_company(company)
    open_orders = orders.exclude(status__in=["paid", "cancelled"]).count()
    paid_today = orders.filter(status="paid", created_at__date=today).count()
    tickets = list(KitchenTicket.objects.for_company(company).filter(status__in=["queued", "preparing", "ready"])
                   .select_related("order", "order__table").prefetch_related("order__lines")
                   .order_by("-priority", "printed_at"))
    targets = kitchen_targets(company, tickets)
    now = timezone.now()
    late = sum(1 for t in tickets if t.status != "ready" and (now - t.printed_at).total_seconds() > targets[t.id] * 60)
    rows = []
    for t in tickets:
        where = _("Table %(t)s") % {"t": t.order.table.name} if t.order.table else t.order.get_channel_display()
        dishes = [f"{line.quantity.normalize():f}× {line.product.name.split(' — ')[-1]}" for line in t.order.lines.all()
                  if line.kitchen_round == t.kitchen_round]
        rows.append({"title": f"{t.ticket_number} · {where}", "sub": ", ".join(dishes[:4]) + (" …" if len(dishes) > 4 else ""),
                     "badge": t.get_status_display(), "tone": "ok" if t.status == "ready" else "",
                     "since": t.printed_at.isoformat(), "target": targets[t.id], "stopped": t.status == "ready",
                     "url": reverse("webapp:restaurant_kitchen")})
    kitchen = reverse("webapp:restaurant_kitchen")
    kpis = [money["today"],
            _kpi(_("Open orders"), open_orders, reverse("webapp:restaurant_order_list") + "?period=all&status=open"),
            _kpi(_("In the kitchen"), len([t for t in tickets if t.status != "ready"]), kitchen,
                 tone="bad" if late else "", note=_("%(n)s late") % {"n": late} if late else ""),
            _kpi(_("Orders paid today"), paid_today, reverse("webapp:restaurant_order_list") + "?period=today&status=paid")]
    main = _panel(_("Kitchen timer"), kitchen, _("Kitchen screen"), rows,
                  _("Kitchen is clear. Orders sent to the kitchen show here with a timer."),
                  reverse("webapp:restaurant_dashboard"), _("Orders"))
    top = (RestaurantOrderLine.objects.filter(order__company=company, order__status="paid", order__created_at__date=today)
           .values("product__name").annotate(qty=Sum("quantity"), amount=Sum(F("quantity") * F("unit_price")))
           .order_by("-qty")[:SHOW])
    side = _panel(_("Best sellers today"), reverse("webapp:restaurant_reports"), _("Reports"),
                  [{"title": r["product__name"].split(" — ")[-1], "sub": f"× {r['qty'].normalize():f}", "amount": r["amount"]}
                   for r in top], _("Nothing sold yet today."))
    return kpis, main, side


def _retail(company, today, money):
    low = _low_stock(company)
    rows = [{"title": p.name, "sub": _("Reorder at %(n)s") % {"n": p.reorder_level},
             "badge": _("Out of stock") if stock <= 0 else f"{stock.normalize():f} {p.unit.name if p.unit_id else ''}".strip(),
             "tone": "bad" if stock <= 0 else "warn", "url": reverse("webapp:stock_home") + "?show=low"}
            for stock, p in low]
    main = _panel(_("Running low"), reverse("webapp:stock_home") + "?show=low", _("Stock"), rows,
                  _("All products are above their reorder level."), reverse("webapp:purchase_list"), _("Purchases"))
    return [money["today"], money["bills"], money["low"], money["month"]], main, _top_items(company, today)


def _mobile(company, today, money):
    from apps.verticals.mobile_shop.models import MobileRepairJob
    jobs = list(MobileRepairJob.objects.for_company(company).exclude(status__in=["completed", "cancelled"])
                .select_related("customer").order_by("received_at"))
    ready = sum(1 for j in jobs if j.status == "ready")
    rows = [{"lead": j.job_number, "title": j.customer.name, "sub": j.device_description,
             "badge": j.get_status_display(), "tone": "ok" if j.status == "ready" else "",
             "url": reverse("webapp:mobile_repair_detail", args=[j.id])} for j in jobs]
    repairs = reverse("webapp:mobile_repair_list")
    kpis = [money["today"], _kpi(_("Repairs in the shop"), len(jobs), repairs),
            _kpi(_("Ready for pickup"), ready, repairs, tone="ok" if ready else ""), money["month"]]
    main = _panel(_("Repair jobs"), repairs, _("All repairs"), rows, _("No repairs waiting."),
                  reverse("webapp:mobile_repair_add"), _("New repair job"))
    return kpis, main, _top_items(company, today)


def _wash(company, today, money):
    from apps.verticals.vehicle_wash.models import WashOrder
    todays = list(WashOrder.objects.for_company(company).filter(scheduled_at__date=today).exclude(status="cancelled")
                  .select_related("vehicle", "package", "staff").order_by("scheduled_at"))
    queue = [o for o in todays if o.status in ("booked", "in_progress")]
    done = [o for o in todays if o.status == "completed"]
    orders = reverse("webapp:wash_order_list")
    rows = [{"lead": f"{timezone.localtime(o.scheduled_at):%H:%M}", "title": o.vehicle.vehicle_number,
             "sub": " · ".join(x for x in (o.package.name, o.staff.name if o.staff else "") if x),
             "badge": o.get_status_display(), "tone": "warn" if o.status == "in_progress" else "", "url": orders}
            for o in queue]
    kpis = [money["today"], _kpi(_("Cars in the queue"), len(queue), orders),
            _kpi(_("Washed today"), len(done), orders), money["month"]]
    main = _panel(_("Today's queue"), orders, _("All orders"), rows, _("No cars waiting."),
                  reverse("webapp:wash_order_book"), _("Book a wash"))
    by_staff = {}
    for o in done:
        name = o.staff.name if o.staff else _("Not assigned")
        row = by_staff.setdefault(name, {"title": name, "n": 0, "amount": Decimal("0")})
        row["n"] += 1
        row["amount"] += o.price
    side = _panel(_("Staff today"), reverse("webapp:staff_list"), _("Staff"),
                  [{"title": r["title"], "sub": _("%(n)s washes") % {"n": r["n"]}, "amount": r["amount"]}
                   for r in sorted(by_staff.values(), key=lambda r: -r["amount"])],
                  _("Finished washes show here by staff member."))
    return kpis, main, side


def _gym(company, today, money):
    from apps.verticals.gym.models import Attendance, GymMember
    members = GymMember.objects.for_company(company).select_related("customer", "membership_plan")
    expiring = list(members.filter(status="active", membership_end__lte=today + timedelta(days=7)).order_by("membership_end"))
    visits = list(Attendance.objects.for_company(company).filter(check_in__date=today).select_related("member__customer")
                  .order_by("-check_in"))
    member_list = reverse("webapp:member_list")
    kpis = [_kpi(_("Check-ins today"), len(visits), reverse("webapp:attendance_today")),
            _kpi(_("Active members"), members.filter(status="active").count(), member_list),
            _kpi(_("Expiring this week"), len(expiring), member_list, tone="warn" if expiring else ""), money["month"]]
    rows = []
    for m in expiring:
        days = (m.membership_end - today).days
        rows.append({"title": m.customer.name, "sub": m.membership_plan.name,
                     "badge": _("Expired") if days < 0 else _("Today") if days == 0 else _("in %(n)s days") % {"n": days},
                     "tone": "bad" if days <= 0 else "warn", "url": member_list})
    main = _panel(_("Memberships to renew"), member_list, _("All members"), rows, _("No memberships end this week."))
    side = _panel(_("Today's check-ins"), reverse("webapp:attendance_today"), _("Attendance"),
                  [{"lead": f"{timezone.localtime(v.check_in):%H:%M}", "title": v.member.customer.name} for v in visits],
                  _("No check-ins yet today."))
    return kpis, main, side


def _tailoring(company, today, money):
    from apps.verticals.textile.models import TailoringOrder
    open_orders = list(TailoringOrder.objects.for_company(company).filter(status__in=["pending", "in_progress", "ready"])
                       .select_related("customer").order_by("expected_delivery_date"))
    ready = [o for o in open_orders if o.status == "ready"]
    working = [o for o in open_orders if o.status != "ready"]
    orders = reverse("webapp:order_list")
    overdue = sum(1 for o in working if o.expected_delivery_date < today)
    kpis = [money["today"], _kpi(_("Orders in progress"), len(working), orders, tone="bad" if overdue else "",
                                 note=_("%(n)s late") % {"n": overdue} if overdue else ""),
            _kpi(_("Ready for pickup"), len(ready), orders, tone="ok" if ready else ""), money["month"]]

    def row(o):
        days = (o.expected_delivery_date - today).days
        return {"lead": f"{o.expected_delivery_date:%d %b}", "title": o.customer.name, "sub": o.get_status_display(),
                "badge": _("Late") if days < 0 else _("Today") if days == 0 else "", "tone": "bad" if days < 0 else "warn",
                "url": orders}
    main = _panel(_("Due for delivery"), orders, _("All orders"), [row(o) for o in working], _("No orders in progress."))
    side = _panel(_("Ready for pickup"), orders, _("All orders"),
                  [{"title": o.customer.name, "amount": o.price, "url": orders} for o in ready], _("Nothing waiting for pickup."))
    return kpis, main, side


def _bookings(company, today, money):
    from apps.industry.models import BookableResource, Booking
    bookings = Booking.objects.for_company(company).select_related("resource", "customer")
    arrivals = list(bookings.filter(status="reserved", start__date=today).order_by("start"))
    departures = list(bookings.filter(status="checked_in", end__date__lte=today).order_by("end"))
    in_house = bookings.filter(status="checked_in").count()
    now = timezone.now()
    busy = set(bookings.filter(status__in=Booking.ACTIVE, start__lte=now, end__gt=now).values_list("resource_id", flat=True))
    free = list(BookableResource.objects.for_company(company).filter(is_active=True).exclude(id__in=busy))
    board = reverse("webapp:booking_board")
    listing = reverse("webapp:booking_list")
    kpis = [_kpi(_("Arriving today"), len(arrivals), listing + "?status=reserved"),
            _kpi(_("Leaving today"), len(departures), board, tone="warn" if departures else ""),
            _kpi(_("In use now"), in_house, listing + "?status=checked_in"), money["month"]]
    rows = [{"lead": f"{timezone.localtime(b.start):%H:%M}", "title": b.customer.name, "sub": b.resource.name,
             "badge": _("Arriving"), "url": reverse("webapp:booking_detail", args=[b.id])} for b in arrivals]
    rows += [{"lead": f"{timezone.localtime(b.end):%H:%M}", "title": b.customer.name, "sub": b.resource.name,
              "badge": _("Leaving"), "tone": "warn", "url": reverse("webapp:booking_detail", args=[b.id])} for b in departures]
    main = _panel(_("Arrivals and departures"), board, _("Booking board"), rows, _("No arrivals or departures today."),
                  reverse("webapp:booking_add"), _("New booking"))
    side = _panel(_("Free right now"), reverse("webapp:booking_resources"), _("All"),
                  [{"title": r.name, "sub": r.details} for r in free], _("Everything is in use."))
    return kpis, main, side


def _education(company, today, money):
    from apps.industry import education
    from apps.industry.models import Enrollment
    dues = education.dues(company)
    total_due = sum((d["due"] for d in dues), Decimal("0"))
    dues_url = reverse("webapp:education_dues")
    kpis = [money["today"], _kpi(_("Fees due"), total_due, dues_url, tone="warn money" if total_due else "money",
                                 note=_("%(n)s students") % {"n": len(dues)} if dues else ""),
            _kpi(_("Active students"), Enrollment.objects.for_company(company).filter(status="active")
                 .values("student").distinct().count(), reverse("webapp:education_home")), money["month"]]
    main = _panel(_("Fees due"), dues_url, _("All dues"),
                  [{"title": d["student"].name, "sub": _("%(n)s bills") % {"n": len(d["invoices"])}, "amount": d["due"],
                    "url": dues_url} for d in dues], _("No fees due. Well done!"), reverse("webapp:education_fees"), _("Fees"))
    return kpis, main, _recent_payments(company)


def _property(company, today, money):
    from apps.industry import property as prop
    late = prop.overdue(company, today)
    info = prop.summary(company, today)
    late_total = sum((r["due"] for r in late), Decimal("0"))
    home = reverse("webapp:property_home")
    kpis = [_kpi(_("Rent collected this month"), info["collected"], reverse("webapp:rent_run"), tone="money"),
            _kpi(_("Overdue rent"), late_total, home, tone="bad money" if late_total else "money"),
            _kpi(_("Occupancy"), f"{info['occupancy']}%", home, note=_("%(n)s vacant") % {"n": info["vacant"]}),
            money["month"]]
    main = _panel(_("Overdue rent"), home, _("Properties"),
                  [{"title": r["charge"].lease.tenant.name, "sub": f"{r['charge'].lease.unit} · {r['charge'].period}",
                    "badge": _("%(n)s days late") % {"n": r["days"]}, "tone": "bad", "amount": r["due"],
                    "url": reverse("webapp:lease_detail", args=[r["charge"].lease_id])} for r in late],
                  _("No overdue rent."), reverse("webapp:rent_run"), _("Monthly rent"))
    side = _panel(_("Leases ending soon"), reverse("webapp:lease_list"), _("All leases"),
                  [{"lead": f"{lease.end_date:%d %b}", "title": lease.tenant.name, "sub": str(lease.unit),
                    "url": reverse("webapp:lease_detail", args=[lease.id])} for lease in info["expiring"]],
                  _("No leases end in the next 60 days."))
    return kpis, main, side


def _service(company, today, money):
    from apps.verticals.saloon.models import ServiceCase
    cases = list(ServiceCase.objects.for_company(company).filter(status__in=["open", "in_progress", "waiting"])
                 .select_related("profile", "assigned_staff").order_by(F("due_date").asc(nulls_last=True), "opened_date"))
    overdue = sum(1 for c in cases if c.due_date and c.due_date < today)
    case_list = reverse("webapp:service_case_list")
    kpis = [money["today"], _kpi(_("Open work"), len(cases), case_list, tone="bad" if overdue else "",
                                 note=_("%(n)s late") % {"n": overdue} if overdue else ""), money["dues"], money["month"]]
    rows = [{"lead": f"{c.due_date:%d %b}" if c.due_date else "", "title": c.title,
             "sub": " · ".join(x for x in (str(c.profile), c.assigned_staff.name if c.assigned_staff else "") if x),
             "badge": c.get_status_display(), "tone": "bad" if c.due_date and c.due_date < today else "",
             "url": reverse("webapp:service_case_detail", args=[c.id])} for c in cases]
    main = _panel(_("Open work"), case_list, _("All work"), rows, _("No open work."))
    return kpis, main, _staff_today(company, today)


def _projects(company, today, money):
    from apps.verticals.construction.models import Project
    projects = list(Project.objects.for_company(company).filter(status__in=["planning", "active", "on_hold"])
                    .select_related("client").order_by(F("end_date").asc(nulls_last=True)))
    active = sum(1 for p in projects if p.status == "active")
    project_list = reverse("webapp:project_list")
    kpis = [money["today"], _kpi(_("Active projects"), active, project_list), money["dues"], money["month"]]
    rows = [{"lead": f"{p.end_date:%d %b}" if p.end_date else "", "title": p.name,
             "sub": p.client.name if p.client_id else "", "badge": p.get_status_display(),
             "tone": "bad" if p.end_date and p.end_date < today else "warn" if p.status == "on_hold" else "",
             "url": reverse("webapp:project_detail", args=[p.id])} for p in projects]
    main = _panel(_("Projects"), project_list, _("All projects"), rows, _("No running projects."))
    return kpis, main, _recent_payments(company)


def _recent_payments(company):
    paid = (_invoices(company).filter(amount_paid__gt=0).select_related("customer").order_by("-date", "-id")[:SHOW])
    return _panel(_("Recent payments"), reverse("webapp:sales_invoice_list"), _("All bills"),
                  [{"lead": f"{i.date:%d %b}", "title": i.customer.name if i.customer_id else i.invoice_number,
                    "amount": i.amount_paid} for i in paid], _("No payments yet."))


def build(company):
    raw = company.business_type.code if company.business_type_id else ""
    code = ALIASES.get(raw, raw)
    features = business_features(code)
    group = business_group(code)
    today = timezone.localdate()
    money = _money(company, today)
    if code in APPOINTMENTS:
        parts = _salon(company, code, today, money)
    elif group == "restaurant":
        parts = _restaurant(company, today, money)
    elif code == "gym":
        parts = _gym(company, today, money)
    elif code == "vehicle_wash":
        parts = _wash(company, today, money)
    elif code == "mobile_shop":
        parts = _mobile(company, today, money)
    elif code == "textile":
        parts = _tailoring(company, today, money)
    elif "bookings" in features:
        parts = _bookings(company, today, money)
    elif "education" in features:
        parts = _education(company, today, money)
    elif "leases" in features:
        parts = _property(company, today, money)
    elif code == "recruitment_agency":
        return {"kpis": [money["today"], money["month"], money["dues"], money["low"]], "main": None, "side": None,
                "own_layout": False}
    elif group == "service":
        parts = _service(company, today, money)
    elif group == "project" or code == "construction":
        parts = _projects(company, today, money)
    else:
        parts = _retail(company, today, money)
    kpis, main, side = parts
    return {"kpis": kpis, "main": main, "side": side, "own_layout": True}


def limit_links(data, request):
    """Drop the links this member's role can't open (a cashier sees the lists, not the Reports link)."""
    from .role_access import blocked_paths
    blocked = blocked_paths(request)
    if not blocked:
        return data

    def ok(url):
        return url and url.split("?")[0] not in blocked
    for kpi in data["kpis"]:
        kpi["url"] = kpi["url"] if ok(kpi["url"]) else ""
    for panel in (data["main"], data["side"]):
        if not panel:
            continue
        for key in ("url", "empty_url"):
            panel[key] = panel[key] if ok(panel[key]) else ""
        for row in panel["rows"]:
            for key in ("url", "action_url"):
                if row.get(key) and not ok(row[key]):
                    row[key] = ""
    return data


def greeting(now=None):
    hour = timezone.localtime(now).hour
    if hour < 12:
        return _("Good morning")
    if hour < 17:
        return _("Good afternoon")
    return _("Good evening")

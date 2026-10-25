"""Van sales: lines (routes) and their shops, the day's trips, the driver's phone page (bill / collect on the
line), evening settlement of stock and cash, and the daily report per driver."""
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.industry import van_sales as svc
from apps.industry.models import VanOrder, VanRoute, VanRouteStop, VanSettings, VanTrip
from apps.inventory.models import Product, ProductPack, Warehouse
from apps.sales import services as sales, sharing
from apps.sales.models import SalesInvoiceLine
from apps.tenants.models import CompanyMembership

from .industry_access import require_industry
from .receivables_views import _balances
from .views import require_permission

ZERO = Decimal("0")


def van_view(view):
    return require_industry("van_sales")(require_permission("sales.create_invoice")(view))


def _manager(request):
    """Owners and accountants run the vans; drivers (staff) only see their own trips."""
    role = getattr(request, "role", None)
    return role is None or role.permissions.filter(permission__code="reports.view").exists()


def _manager_only(request):
    if not _manager(request):
        raise Http404


def _num(value, default="0"):
    try:
        return Decimal(str(value if value not in (None, "") else default).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(_("Enter a valid number."))


def _error(request, exc):
    messages.error(request, " ".join(getattr(exc, "messages", None) or [str(exc)]))


def _drivers(company):
    ids = CompanyMembership.objects.filter(company=company, is_active=True).values_list("user_id", flat=True)
    return get_user_model().objects.filter(id__in=ids).order_by("first_name", "username")


def _trip(request, trip_id):
    trip = get_object_or_404(VanTrip.objects.for_company(request.company).select_related("route", "driver", "warehouse"),
                             id=trip_id)
    if not _manager(request) and trip.driver_id != request.user.id:
        raise Http404
    return trip


def _warehouses(company):
    return Warehouse.objects.for_company(company).filter(is_active=True).order_by("-is_default", "name")


@van_view
def van_home(request):
    company = request.company
    manager = _manager(request)
    day = parse_date(request.GET.get("date") or "") or timezone.localdate()
    trips = VanTrip.objects.for_company(company).filter(date=day).select_related("route", "driver")
    if not manager:
        trips = VanTrip.objects.for_company(company).filter(driver=request.user).exclude(
            status="closed", date__lt=timezone.localdate() - timedelta(days=7)).select_related("route", "driver")[:30]
    rows = [{"trip": t, "money": svc.totals(t)} for t in trips]
    routes = VanRoute.objects.for_company(company).filter(is_active=True).select_related("driver")
    started = {t.route_id for t in trips if t.route_id}
    waiting = [r for r in routes if r.runs_on(day) and r.id not in started] if manager else []
    return render(request, "webapp/van/home.html", {
        "manager": manager, "day": day, "prev": day - timedelta(days=1), "next": day + timedelta(days=1),
        "rows": rows, "waiting": waiting, "routes": routes, "drivers": _drivers(company),
        "warehouses": _warehouses(company), "currency": company.default_currency,
    })


@van_view
@require_POST
def van_trip_start(request):
    """Manager opens today's trip for a line (or a one-off trip without a line)."""
    _manager_only(request)
    company = request.company
    route = VanRoute.objects.for_company(company).filter(id=request.POST.get("route") or 0).first()
    driver = _drivers(company).filter(id=request.POST.get("driver") or 0).first() or (route.driver if route else None)
    warehouse = _warehouses(company).filter(id=request.POST.get("warehouse") or 0).first() or _warehouses(company).first()
    if driver is None or warehouse is None:
        messages.error(request, _("Choose a driver."))
        return redirect("webapp:van_home")
    day = parse_date(request.POST.get("date") or "") or timezone.localdate()
    trip = VanTrip.objects.create(company=company, route=route, driver=driver, date=day, warehouse=warehouse)
    last = (VanTrip.objects.for_company(company).filter(route=route, status="closed").exclude(id=trip.id)
            .order_by("-date", "-id").first() if route else None)
    if last and request.POST.get("copy_load"):
        for load in last.loads.all():
            trip.loads.create(product=load.product, loaded=load.loaded)
    messages.success(request, _("Trip opened. Add what goes into the van, then hand it to the driver."))
    return redirect("webapp:van_trip", trip_id=trip.id)


def _stops(trip, balances):
    """Shops of the trip: the line's shops in order, then any other shop billed on this trip."""
    customers = [s.customer for s in trip.route.stops.select_related("customer")] if trip.route else []
    seen = {c.id for c in customers}
    for sale in trip.sales.select_related("invoice__customer"):
        if sale.invoice.customer_id not in seen:
            customers.append(sale.invoice.customer)
            seen.add(sale.invoice.customer_id)
    billed = {}
    for sale in trip.sales.select_related("invoice"):
        billed[sale.invoice.customer_id] = billed.get(sale.invoice.customer_id, ZERO) + sale.invoice.total
    collected = {}
    for c in trip.collections.all():
        collected[c.customer_id] = collected.get(c.customer_id, ZERO) + c.amount
    return [{"customer": c, "due": balances.get(c.id, ZERO), "billed": billed.get(c.id),
             "collected": collected.get(c.id)} for c in customers]


@van_view
def van_trip(request, trip_id):
    trip = _trip(request, trip_id)
    company = request.company
    manager = _manager(request)
    balances = _balances(company)
    stock = svc.stock(trip)
    shared = None
    billed_id = request.GET.get("billed")
    if billed_id and str(billed_id).isdigit():
        sale = trip.sales.select_related("invoice__customer").filter(invoice_id=billed_id).first()
        if sale:
            url = request.build_absolute_uri(reverse("webapp:public_invoice", args=[sharing.share_token(sale.invoice)]))
            shared = {"invoice": sale.invoice, "whatsapp": sharing.whatsapp_url(sale.invoice, url)}
    loaded_ids = {row["product"].id for row in stock}
    sales_rows = list(trip.sales.select_related("invoice__customer").order_by("-id"))
    for row in sales_rows:
        row.credit = row.invoice.total - row.paid_now
    return render(request, "webapp/van/trip.html", {
        "trip": trip, "manager": manager, "stock": stock, "money": svc.totals(trip),
        "suggestion": svc.load_suggestion(trip) if manager and trip.status != "closed" else [],
        "expenses": trip.expenses.order_by("-id"), "returns": trip.returns.select_related("customer", "product").order_by("-id"),
        "orders": VanOrder.objects.for_company(company).filter(trip=trip).select_related("customer", "product", "pack"),
        "owner_whatsapp": svc.owner_whatsapp_link(trip) if manager and trip.status == "closed" else "",
        "stops": _stops(trip, balances), "shared": shared, "currency": company.default_currency,
        "sales": sales_rows,
        "collections": trip.collections.select_related("customer").order_by("-id"),
        "products": Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
                    .exclude(id__in=loaded_ids).order_by("name") if manager else [],
        "customers": Customer.objects.for_company(company).filter(is_active=True).order_by("name"),
    })


@van_view
@require_POST
def van_trip_action(request, trip_id):
    trip = _trip(request, trip_id)
    action = request.POST.get("action")
    try:
        if action == "start":
            svc.start(trip)
            messages.success(request, _("Trip started. Have a good day on the line!"))
        elif action == "load":
            _manager_only(request)
            product = get_object_or_404(Product.objects.for_company(request.company), id=request.POST.get("product") or 0)
            svc.set_load(trip, product, _num(request.POST.get("quantity")))
        elif action == "suggest":
            _manager_only(request)
            for row in svc.load_suggestion(trip):
                if row["suggested"] > row["loaded"]:
                    svc.set_load(trip, row["product"], row["suggested"])
            messages.success(request, _("Suggested load added."))
        elif action == "collect":
            customer = get_object_or_404(Customer.objects.for_company(request.company), id=request.POST.get("customer") or 0)
            row = svc.collect(trip=trip, user=request.user, customer=customer, amount=_num(request.POST.get("amount")),
                              method=request.POST.get("method"))
            messages.success(request, _("%(amount)s received from %(name)s.") % {"amount": f"{row.amount:.2f}",
                                                                                "name": customer.name})
        elif action == "close":
            _manager_only(request)
            returned = {row["product"].id: _num(request.POST.get(f"returned_{row['product'].id}"), row["left"])
                        for row in svc.stock(trip)}
            svc.close(trip=trip, user=request.user, returned=returned, cash_handed=request.POST.get("cash_handed"))
            money = svc.totals(trip)
            if money["cash_short"] > 0:
                messages.warning(request, _("Trip settled. Cash is short by %(amount)s.") % {"amount": f"{money['cash_short']:.2f}"})
            else:
                messages.success(request, _("Trip settled."))
        else:
            raise Http404
    except ValidationError as exc:
        _error(request, exc)
    return redirect("webapp:van_trip", trip_id=trip.id)


def _last_prices(company, customer, products):
    """{product_id: price} the shop paid last time, per piece."""
    prices = {}
    lines = (SalesInvoiceLine.objects.filter(invoice__company=company, invoice__customer=customer, unit_factor=1,
                                             product__in=products).order_by("product_id", "-invoice__date", "-id")
             .values_list("product_id", "unit_price"))
    for pid, price in lines:
        prices.setdefault(pid, price)
    return prices


@van_view
def van_sell(request, trip_id):
    """The driver's bill screen: one shop, the van's items with this shop's usual price, paid now / credit."""
    trip = _trip(request, trip_id)
    company = request.company
    if trip.status == "closed":
        messages.error(request, _("This trip is already settled."))
        return redirect("webapp:van_trip", trip_id=trip.id)
    customer = Customer.objects.for_company(company).filter(id=request.GET.get("customer") or request.POST.get("customer") or 0).first()
    if customer is None:
        raise Http404
    stock = {row["product"].id: row for row in svc.stock(trip)}
    products = list(Product.objects.for_company(company).filter(id__in=stock) if stock else
                    Product.objects.for_company(company).filter(is_active=True).exclude(is_stock_tracked=False).order_by("name")[:200])
    packs = {}
    for pack in ProductPack.objects.filter(product__in=products, is_active=True):
        packs.setdefault(pack.product_id, []).append(pack)
    last = _last_prices(company, customer, products)
    today = timezone.localdate()
    items = []
    for p in sorted(products, key=lambda p: p.name):
        price = last.get(p.id) or sales.resolve_commercial_price(company=company, customer=customer, product=p, date=today)[0]
        units = [{"id": "", "name": p.unit.name if getattr(p, "unit", None) else _("piece"), "price": f"{price:.2f}", "factor": "1"}]
        units += [{"id": str(k.id), "name": k.name, "price": f"{k.price:.2f}", "factor": f"{k.factor.normalize():f}"}
                  for k in packs.get(p.id, [])]
        items.append({"product": p, "price": f"{price:.2f}", "units": units, "units_json": json.dumps(units),
                      "left": stock[p.id]["left"] if p.id in stock else None})
    if request.method == "POST":  # keep what was typed if the bill can't be saved
        for item in items:
            pid = item["product"].id
            item["qty"] = request.POST.get(f"qty_{pid}", "")
            item["price"] = request.POST.get(f"price_{pid}") or item["price"]
            item["unit"] = request.POST.get(f"unit_{pid}", "")
        lines = []
        try:
            for item in items:
                p = item["product"]
                qty = _num(request.POST.get(f"qty_{p.id}"))
                if not qty:
                    continue
                pack = None
                pack_id = request.POST.get(f"unit_{p.id}") or ""
                if pack_id:
                    pack = next((k for k in packs.get(p.id, []) if str(k.id) == pack_id), None)
                    if pack is None:
                        raise ValidationError(_("Choose a valid unit."))
                line = {"product": p, "quantity": qty, "unit_price": _num(request.POST.get(f"price_{p.id}"))}
                if pack:
                    line["pack"] = pack
                lines.append(line)
            invoice = svc.sell(trip=trip, user=request.user, customer=customer, lines=lines,
                               paid=_num(request.POST.get("paid")), method=request.POST.get("method"))
        except ValidationError as exc:
            _error(request, exc)
        else:
            credit = invoice.total - _num(request.POST.get("paid"))
            text = _("Bill %(no)s for %(name)s: %(total)s.") % {"no": invoice.invoice_number, "name": customer.name,
                                                               "total": f"{invoice.total:.2f}"}
            if credit > 0:
                text += " · " + _("%(amount)s added to credit.") % {"amount": f"{credit:.2f}"}
            messages.success(request, text)
            return redirect(reverse("webapp:van_trip", args=[trip.id]) + f"?billed={invoice.id}")
    return render(request, "webapp/van/sell.html", {
        "trip": trip, "customer": customer, "items": items, "due": _balances(company).get(customer.id, ZERO),
        "paid": request.POST.get("paid", "") if request.method == "POST" else "",
        "currency": company.default_currency,
    })


# ---------------------------------------------------------------- lines (routes)

def _route_from_post(route, request):
    route.name = (request.POST.get("name") or "").strip()[:120]
    route.driver = _drivers(request.company).filter(id=request.POST.get("driver") or 0).first()
    route.days = ",".join(d for d in request.POST.getlist("days") if d in dict(VanRoute.DAYS))
    route.notes = (request.POST.get("notes") or "").strip()[:255]
    if len(route.name) < 2:
        raise ValidationError(_("Give the line a name."))


@van_view
def van_routes(request):
    _manager_only(request)
    company = request.company
    settings = VanSettings.load(company)
    if request.method == "POST" and request.POST.get("action") == "settings":
        days = request.POST.get("block_overdue_days") or "0"
        settings.block_overdue_days = min(int(days), 365) if days.isdigit() else 0
        settings.notify_owner = bool(request.POST.get("notify_owner"))
        settings.save()
        messages.success(request, _("Van settings saved."))
        return redirect("webapp:van_routes")
    if request.method == "POST":
        route = VanRoute(company=company)
        try:
            _route_from_post(route, request)
        except ValidationError as exc:
            _error(request, exc)
        else:
            route.save()
            messages.success(request, _("Line added. Now add its shops."))
            return redirect("webapp:van_route", route_id=route.id)
    routes = VanRoute.objects.for_company(company).select_related("driver").order_by("-is_active", "name")
    return render(request, "webapp/van/routes.html", {"routes": routes, "drivers": _drivers(company),
                                                      "days": VanRoute.DAYS, "settings": settings})


@van_view
def van_route(request, route_id):
    _manager_only(request)
    company = request.company
    route = get_object_or_404(VanRoute.objects.for_company(company), id=route_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "save":
                _route_from_post(route, request)
                route.is_active = bool(request.POST.get("is_active"))
                route.save()
                messages.success(request, _("Line saved."))
            elif action == "add":
                customer = Customer.objects.for_company(company).filter(id=request.POST.get("customer") or 0).first()
                name = (request.POST.get("new_name") or "").strip()
                if customer is None and len(name) >= 2:
                    phone = (request.POST.get("new_phone") or "").strip()[:20]
                    customer = (Customer.objects.for_company(company).filter(phone=phone).first() if phone else None) \
                        or Customer.objects.create(company=company, name=name[:255], phone=phone)
                if customer is None:
                    raise ValidationError(_("Choose a shop or type a new shop's name."))
                last = route.stops.order_by("-position").first()
                VanRouteStop.objects.get_or_create(route=route, customer=customer,
                                                   defaults={"position": (last.position + 1) if last else 1})
            elif action in ("up", "down", "remove"):
                stop = get_object_or_404(route.stops, id=request.POST.get("stop") or 0)
                if action == "remove":
                    stop.delete()
                else:
                    stops = list(route.stops.all())
                    i = stops.index(stop)
                    j = i - 1 if action == "up" else i + 1
                    if 0 <= j < len(stops):
                        stops[i], stops[j] = stops[j], stops[i]
                    for n, s in enumerate(stops, start=1):
                        if s.position != n:
                            s.position = n
                            s.save(update_fields=["position"])
            else:
                raise Http404
        except ValidationError as exc:
            _error(request, exc)
        return redirect("webapp:van_route", route_id=route.id)
    on_route = route.stops.values_list("customer_id", flat=True)
    return render(request, "webapp/van/route.html", {
        "route": route, "stops": route.stops.select_related("customer"), "drivers": _drivers(company),
        "days": VanRoute.DAYS, "customers": Customer.objects.for_company(company).filter(is_active=True)
        .exclude(id__in=on_route).order_by("name"),
    })


# ---------------------------------------------------------------- report

@van_view
def van_report(request):
    """Per driver for a period: bills, sales, paid now, credit given, old dues collected, cash due and handed."""
    _manager_only(request)
    company = request.company
    today = timezone.localdate()
    start = parse_date(request.GET.get("start") or "") or today
    end = parse_date(request.GET.get("end") or "") or start
    if end < start:
        start, end = end, start
    trips = (VanTrip.objects.for_company(company).filter(date__range=(start, end))
             .select_related("route", "driver").order_by("date", "id"))
    keys = ("bills", "sales", "paid_cash", "paid_bank", "credit", "collected", "returns", "expenses", "expected_cash",
            "cash_short")
    drivers, grand, rows = {}, dict.fromkeys(keys, ZERO), []
    for trip in trips:
        money = svc.totals(trip)
        rows.append({"trip": trip, "money": money})
        name = (trip.driver.get_full_name() or trip.driver.username) if trip.driver else _("No driver")
        d = drivers.setdefault(name, {"name": name, "trips": 0, "handed": ZERO, "open": 0, **dict.fromkeys(keys, ZERO)})
        d["trips"] += 1
        d["open"] += trip.status != "closed"
        d["handed"] += money["handed"] or ZERO
        for k in keys:
            d[k] += money[k]
            grand[k] += money[k]
    return render(request, "webapp/van/report.html", {
        "start": start, "end": end, "drivers": sorted(drivers.values(), key=lambda d: -d["sales"]), "grand": grand,
        "rows": rows, "currency": company.default_currency,
    })

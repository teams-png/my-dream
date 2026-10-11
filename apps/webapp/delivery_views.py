"""Restaurant home delivery: the delivery board (riders, areas, who has which order, cash with each rider),
the rider's own phone page (private link, no login) and the delivery report."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.inventory.models import Warehouse
from apps.verticals.restaurant import delivery as svc
from apps.verticals.restaurant.models import DeliveryRider, DeliveryZone, RestaurantOrder

from .online_order_views import staff_view


def _money(value, default="0"):
    try:
        amount = Decimal(str(value or default).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(_("Enter a valid amount."))
    if amount < 0 or amount > Decimal("100000"):
        raise ValidationError(_("Enter a valid amount."))
    return amount.quantize(Decimal("0.01"))


def _pk(value):
    return int(value) if str(value or "").isdigit() else 0


def rider_link(request, rider):
    return request.build_absolute_uri(reverse("webapp:delivery_rider_page", args=[rider.token]))


@staff_view
def board(request):
    company = request.company
    orders = list(svc.board_orders(company))
    riders = list(DeliveryRider.objects.for_company(company))
    for o in orders:
        o.collect = svc.to_collect(o)
        o.maps = svc.maps_url(o.delivery_address)
        o.late = svc.late(o)
        o.whatsapp = svc.customer_whatsapp(o) if o.rider and o.delivery_status in ("assigned", "out") else ""
    for r in riders:
        r.busy = sum(1 for o in orders if o.rider_id == r.id and o.delivery_status in ("assigned", "out"))
        r.cash = svc.cash_with(r) if r.is_active or r.handovers.exists() else Decimal("0")
        r.to_settle = svc.unsettled(r).count()
        r.link = rider_link(request, r)
        r.whatsapp = svc.rider_whatsapp(r, r.link)
    columns = [
        ("waiting", _("Waiting for a rider"), [o for o in orders if o.delivery_status in ("waiting", "failed")]),
        ("assigned", _("Rider assigned"), [o for o in orders if o.delivery_status == "assigned"]),
        ("out", _("On the way"), [o for o in orders if o.delivery_status == "out"]),
        ("delivered", _("Delivered today"), [o for o in orders if o.delivery_status == "delivered"]),
    ]
    return render(request, "webapp/restaurant/deliveries.html", {
        "columns": columns, "riders": riders, "active_riders": [r for r in riders if r.is_active],
        "zones": DeliveryZone.objects.for_company(company), "currency": company.default_currency,
        "warehouses": Warehouse.objects.for_company(company).filter(is_active=True),
        "cash_total": sum((r.cash for r in riders), Decimal("0")),
    })


@staff_view
@require_POST
def action(request):
    company = request.company
    what = request.POST.get("do", "")
    back = request.POST.get("next") or ""
    if not back.startswith("/") or back.startswith("//"):
        back = reverse("webapp:restaurant_deliveries")

    def order():
        return get_object_or_404(RestaurantOrder.objects.for_company(company), id=_pk(request.POST.get("order_id")))

    def rider(required=True):
        rid = _pk(request.POST.get("rider_id"))
        if not rid and not required:
            return None
        return get_object_or_404(DeliveryRider.objects.for_company(company), id=rid)

    try:
        if what == "assign":
            o = svc.assign(order(), rider(required=False))
            messages.success(request, _("%(order)s → %(rider)s") % {"order": o.order_number, "rider": o.rider or _("no rider")})
        elif what == "out":
            o = svc.dispatch(order())
            messages.success(request, _("%(order)s is on the way. Send the customer a WhatsApp from the card.") % {"order": o.order_number})
        elif what == "delivered":
            o = svc.deliver(order(), request.POST.get("method", ""))
            messages.success(request, _("%(order)s delivered.") % {"order": o.order_number})
        elif what == "failed":
            o = svc.fail(order(), request.POST.get("reason", ""))
            messages.success(request, _("%(order)s marked not delivered. Assign it again when ready.") % {"order": o.order_number})
        elif what == "zone":
            zid = _pk(request.POST.get("zone_id"))
            zone = get_object_or_404(DeliveryZone.objects.for_company(company), id=zid) if zid else None
            o = order()
            fee = svc.set_zone(o, zone)
            messages.success(request, _("Delivery area saved. Delivery charge: %(fee)s") % {"fee": f"{company.default_currency} {fee:.2f}"})
        elif what == "handover":
            wid = _pk(request.POST.get("warehouse_id"))
            warehouse = Warehouse.objects.for_company(company).filter(id=wid, is_active=True).first() if wid else None
            r = rider()
            record = svc.handover(r, request.user, warehouse)
            messages.success(request, _("Received %(cash)s cash from %(name)s. %(n)s order(s) billed.") % {
                "cash": f"{company.default_currency} {record.cash:.2f}", "name": r.name, "n": record.orders_count})
        elif what == "rider_save":
            rid = _pk(request.POST.get("rider_id"))
            r = get_object_or_404(DeliveryRider.objects.for_company(company), id=rid) if rid else DeliveryRider(company=company)
            name, phone = request.POST.get("name", "").strip()[:120], request.POST.get("phone", "").strip()[:30]
            if len(name) < 2 or len(phone) < 6:
                raise ValidationError(_("Enter the rider's name and phone number."))
            r.name, r.phone = name, phone
            r.vehicle = request.POST.get("vehicle", "").strip()[:80]
            r.id_number = request.POST.get("id_number", "").strip()[:60]
            r.save()
            messages.success(request, _("Rider %(name)s saved. Send them their page link on WhatsApp.") % {"name": r.name})
        elif what == "rider_toggle":
            r = rider()
            if r.is_active and RestaurantOrder.objects.for_company(company).filter(rider=r, delivery_status__in=("assigned", "out")).exists():
                raise ValidationError(_("%(name)s still has orders on the way.") % {"name": r.name})
            r.is_active = not r.is_active
            r.save(update_fields=["is_active"])
            messages.success(request, _("Saved."))
        elif what == "rider_new_link":
            import uuid
            r = rider()
            r.token = uuid.uuid4()
            r.save(update_fields=["token"])
            messages.success(request, _("New link made — the old link no longer works. Send %(name)s the new one.") % {"name": r.name})
        elif what == "zone_save":
            zid = _pk(request.POST.get("zone_id"))
            z = get_object_or_404(DeliveryZone.objects.for_company(company), id=zid) if zid else DeliveryZone(company=company)
            z.name = request.POST.get("name", "").strip()[:100]
            if len(z.name) < 2:
                raise ValidationError(_("Enter the area name."))
            z.fee, z.free_over = _money(request.POST.get("fee")), _money(request.POST.get("free_over"))
            z.minutes = max(5, min(240, _pk(request.POST.get("minutes")) or 30))
            z.save()
            messages.success(request, _("Delivery area %(name)s saved.") % {"name": z.name})
        elif what == "zone_toggle":
            z = get_object_or_404(DeliveryZone.objects.for_company(company), id=_pk(request.POST.get("zone_id")))
            z.is_active = not z.is_active
            z.save(update_fields=["is_active"])
            messages.success(request, _("Saved."))
        else:
            raise Http404
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(back)


@staff_view
def report(request):
    company = request.company
    today = timezone.localdate()
    start = parse_date(request.GET.get("start") or "") or today - timedelta(days=6)
    end = parse_date(request.GET.get("end") or "") or today
    if start > end:
        start, end = end, start
    rows, zones = svc.report(company, start, end)
    handovers = (svc.DeliveryHandover.objects.for_company(company).filter(created_at__date__gte=start, created_at__date__lte=end)
                 .select_related("rider", "received_by")[:200])
    return render(request, "webapp/restaurant/delivery_report.html", {
        "rows": rows, "zones": zones, "handovers": handovers, "start": start, "end": end,
        "currency": company.default_currency,
        "totals": {"delivered": sum(r["delivered"] for r in rows), "failed": sum(r["failed"] for r in rows),
                   "cash": sum((r["cash"] for r in rows), Decimal("0")), "card": sum((r["card"] for r in rows), Decimal("0")),
                   "fees": sum((r["fees"] for r in rows), Decimal("0"))},
    })


def rider_page(request, token):
    """The rider's own page on their phone. The private link is the key; it shows only their orders."""
    rider = DeliveryRider.objects.select_related("company").filter(token=token, is_active=True).first()
    if rider is None or not rider.company.is_active:
        raise Http404
    if request.method == "POST":
        o = get_object_or_404(RestaurantOrder.objects.for_company(rider.company), id=_pk(request.POST.get("order_id")), rider=rider)
        what = request.POST.get("do")
        try:
            if what == "out":
                svc.dispatch(o)
            elif what == "delivered":
                svc.deliver(o, request.POST.get("method", ""))
            elif what == "failed":
                svc.fail(o, request.POST.get("reason", ""))
            else:
                raise Http404
            messages.success(request, _("Saved."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("webapp:delivery_rider_page", token=rider.token)
    orders = list(svc.rider_orders(rider))
    for o in orders:
        o.collect = svc.to_collect(o)
        o.maps = svc.maps_url(o.delivery_address)
        o.items = [l for l in o.lines.all() if l.product.sku != svc.FEE_SKU]
    return render(request, "webapp/restaurant/rider_page.html", {
        "rider": rider, "company": rider.company, "currency": rider.company.default_currency,
        "open": [o for o in orders if o.delivery_status in ("assigned", "out")],
        "done": [o for o in orders if o.delivery_status == "delivered"],
        "cash": svc.cash_with(rider),
    })

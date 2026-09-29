"""
Hardware / device support.

Printers, cash drawers, scanners and customer displays are attached to the
till PC, not to the server, so the browser talks to them directly
(static/js/devices.js: WebUSB, Web Serial or the local print agent in
scripts/print_agent.py). These views only supply the page and the
print-ready data; the per-till device choice lives in that browser.
"""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from functools import wraps

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.sales.models import SalesInvoice
from apps.verticals.restaurant.models import KitchenTicket, RestaurantOrder


def company_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "company", None) is None:
            raise Http404("No active business.")
        return view(request, *args, **kwargs)
    return wrapper


def _money(value):
    return f"{Decimal(value or 0):.2f}"


def _qty(value):
    value = Decimal(value or 0).normalize()
    return f"{value:f}"


def _header(company):
    return {
        "name": company.name, "address": company.address, "phone": company.phone,
        "currency": company.default_currency,
    }


@login_required
def devices_settings(request):
    """Per-till device setup page (printer, drawer, scanner, display, alarm)."""
    return render(request, "webapp/devices.html", {})


@login_required
@company_required
def customer_display(request):
    """Second-screen page that mirrors the POS cart for the customer."""
    return render(request, "webapp/customer_display.html", {"company": request.company})


@login_required
@company_required
def invoice_receipt_data(request, invoice_id):
    invoice = get_object_or_404(
        SalesInvoice.objects.for_company(request.company).select_related("customer"), id=invoice_id,
    )
    lines = invoice.lines.select_related("product")
    return JsonResponse({
        "kind": "receipt",
        "company": _header(request.company),
        "title": invoice.invoice_number,
        "meta": [invoice.date.strftime("%d %b %Y"), str(invoice.customer)],
        "lines": [{"qty": _qty(l.quantity), "name": l.product.name, "amount": _money(l.line_total), "extra": []} for l in lines],
        "totals": [["Subtotal", _money(invoice.subtotal)]]
                  + ([["Discount", "-" + _money(invoice.discount_amount)]] if invoice.discount_amount else [])
                  + ([["Tax", _money(invoice.tax_amount)]] if invoice.tax_amount else []),
        "grand_total": _money(invoice.total),
        "payments": [["Paid", _money(invoice.amount_paid)]],
        "footer": "Thank you for your business!",
        "open_drawer": True,
    })


@login_required
@company_required
def restaurant_receipt_data(request, order_id):
    order = get_object_or_404(
        RestaurantOrder.objects.for_company(request.company).select_related("table"), id=order_id,
    )
    totals = [["Subtotal", _money(order.subtotal)]]
    if order.service_charge:
        totals.append(["Service charge", _money(order.service_charge)])
    if order.tip_amount:
        totals.append(["Tip", _money(order.tip_amount)])
    if order.tax_percent:
        totals.append([f"Tax {order.tax_percent.normalize():f}%", _money(order.tax_amount)])
    if order.discount_amount:
        totals.append(["Discount", "-" + _money(order.discount_amount)])
    meta = [timezone.localtime(order.created_at).strftime("%d %b %Y %I:%M %p"), order.get_channel_display()]
    if order.table:
        meta.append(f"Table {order.table.name}")
    return JsonResponse({
        "kind": "receipt",
        "company": _header(request.company),
        "title": order.order_number,
        "meta": meta,
        "lines": [{
            "qty": _qty(line.quantity), "name": line.product.name, "amount": _money(line.total),
            "extra": [f"+ {m.modifier.name}" for m in line.modifiers.all()],
        } for line in order.lines.select_related("product").prefetch_related("modifiers__modifier")],
        "totals": totals,
        "grand_total": _money(order.total),
        "payments": [[p.get_method_display(), _money(p.amount)] for p in order.payment_splits.all()],
        "footer": "Thank you. Please visit again!",
        "open_drawer": order.status == "paid" and order.payment_splits.filter(method="cash").exists(),
    })


@login_required
@company_required
def kot_data(request, ticket_id):
    ticket = get_object_or_404(
        KitchenTicket.objects.for_company(request.company).select_related("order", "order__table", "station"),
        id=ticket_id,
    )
    station_categories = set(ticket.station.categories.values_list("id", flat=True)) if ticket.station else set()
    lines = []
    for line in ticket.order.lines.select_related("product").prefetch_related("modifiers__modifier"):
        if line.kitchen_round != ticket.kitchen_round:
            continue
        if station_categories and line.product.category_id not in station_categories:
            continue
        extra = [f"+ {m.modifier.name}" for m in line.modifiers.all()]
        if line.notes:
            extra.append(f"NOTE: {line.notes}")
        lines.append({"qty": _qty(line.quantity), "name": line.product.name, "extra": extra})
    order = ticket.order
    meta = [ticket.ticket_number, f"{order.order_number} · {order.get_channel_display()}"]
    if order.table:
        meta.append(f"TABLE {order.table.name}")
    if order.guests:
        meta.append(f"GUESTS {order.guests}")
    if ticket.station:
        meta.append(ticket.station.name)
    if ticket.kitchen_round > 1:
        meta.append(f"*** ADD-ON ROUND {ticket.kitchen_round} ***")
    meta.append(timezone.localtime(ticket.printed_at).strftime("%I:%M %p"))
    return JsonResponse({"kind": "kot", "title": "KITCHEN ORDER", "meta": meta, "lines": lines})

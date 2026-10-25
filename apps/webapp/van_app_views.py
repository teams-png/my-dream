"""The driver's phone app for a van trip. It works offline: the page keeps the trip's shops, items and prices,
records bills, collections, returns, orders and expenses on the phone, and sends them here when there is a
network. Every action carries an id made on the phone, so sending it twice never books it twice."""
import base64
import binascii
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.industry import van_sales as svc
from apps.industry.models import VanOrder, VanSettings, VanSyncOp, VanTripExpense
from apps.inventory.models import Product, ProductPack
from apps.sales import sharing
from apps.sales.allocation import open_invoices
from apps.sales.models import SalesInvoiceLine

from .receivables_views import _balances
from .van_views import _manager, _trip, van_view

MAX_PHOTO = 3 * 1024 * 1024


def _s(value):
    return f"{Decimal(value or 0):.2f}"


def _q(value):
    return f"{Decimal(value or 0).normalize():f}"


def _bill_link(request, invoice):
    url = request.build_absolute_uri(reverse("webapp:public_invoice", args=[sharing.share_token(invoice)]))
    return sharing.whatsapp_url(invoice, url)


def app_state(request, trip):
    """Everything the phone needs to keep working without a network."""
    company = trip.company
    settings = VanSettings.load(company)
    balances = _balances(company)
    stock = svc.stock(trip)
    if stock:
        products = [r["product"] for r in stock]
        left = {r["product"].id: r["left"] for r in stock}
    else:
        products = list(Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
                        .select_related("unit").order_by("name")[:300])
        left = {}
    packs = {}
    for pack in ProductPack.objects.filter(product__in=products, is_active=True):
        packs.setdefault(pack.product_id, []).append(pack)
    items = [{"id": p.id, "name": p.name, "left": _q(left[p.id]) if p.id in left else None,
              "units": [{"id": "", "name": p.unit.name if p.unit_id else _("piece"), "factor": "1", "price": _s(p.selling_price)}]
              + [{"id": str(k.id), "name": k.name, "factor": _q(k.factor), "price": _s(k.price)} for k in packs.get(p.id, [])]}
             for p in sorted(products, key=lambda p: p.name)]

    customers = [s.customer for s in trip.route.stops.select_related("customer")] if trip.route_id else []
    seen = {c.id for c in customers}
    for sale in trip.sales.select_related("invoice__customer"):
        if sale.invoice.customer_id not in seen:
            customers.append(sale.invoice.customer)
            seen.add(sale.invoice.customer_id)
    prices = {}
    for cid, pid, price in (SalesInvoiceLine.objects.filter(invoice__company=company, invoice__customer_id__in=seen,
                                                            product__in=products, unit_factor=1)
                            .order_by("-invoice__date", "-id").values_list("invoice__customer_id", "product_id", "unit_price")):
        prices.setdefault(cid, {}).setdefault(str(pid), _s(price))
    orders = {}
    for o in VanOrder.objects.for_company(company).filter(status="open", customer_id__in=seen).select_related("product", "pack"):
        orders.setdefault(o.customer_id, []).append({"id": o.id, "product": o.product_id, "name": o.product.name,
                                                     "unit": str(o.pack_id or ""), "unit_name": o.pack.name if o.pack else "",
                                                     "qty": _q(o.quantity), "note": o.note})
    billed, collected = {}, {}
    for sale in trip.sales.select_related("invoice"):
        billed[sale.invoice.customer_id] = billed.get(sale.invoice.customer_id, Decimal("0")) + sale.invoice.total
    for c in trip.collections.all():
        collected[c.customer_id] = collected.get(c.customer_id, Decimal("0")) + c.amount
    shops = []
    for c in customers:
        late = svc.overdue(company, c, settings.block_overdue_days) if settings.block_overdue_days else None
        shops.append({"id": c.id, "name": c.name, "phone": c.phone, "due": _s(balances.get(c.id)),
                      "limit": _s(c.credit_limit), "late": late[1] if late else 0, "late_no": late[0].invoice_number if late else "",
                      "billed": _s(billed[c.id]) if c.id in billed else "", "collected": _s(collected[c.id]) if c.id in collected else "",
                      "prices": prices.get(c.id, {}), "orders": orders.get(c.id, [])})
    others = [{"id": c.id, "name": c.name, "phone": c.phone} for c in
              Customer.objects.for_company(company).filter(is_active=True).exclude(id__in=seen).order_by("name")[:3000]]
    money = {k: (_s(v) if isinstance(v, Decimal) else v) for k, v in svc.totals(trip).items() if v is not None}
    recent = [{"no": s.invoice.invoice_number, "shop": s.invoice.customer.name, "total": _s(s.invoice.total),
               "wa": _bill_link(request, s.invoice)}
              for s in trip.sales.select_related("invoice__customer").order_by("-id")[:15]]
    return {"trip": {"id": trip.id, "name": trip.route.name if trip.route_id else _("Extra trip"),
                     "date": trip.date.isoformat(), "status": trip.status, "status_label": str(trip.get_status_display())},
            "currency": company.default_currency, "block_days": settings.block_overdue_days,
            "shops": shops, "items": items, "others": others, "money": money, "recent": recent,
            "kinds": [[k, str(v)] for k, v in VanTripExpense.KINDS], "at": timezone.now().isoformat()}


def app_text():
    """Words the phone app shows (it runs offline, so they travel with the page)."""
    return {
        "shops": _("Shops"), "van": _("Van stock"), "spend": _("Expenses"), "summary": _("Summary"),
        "bill": _("Bill"), "collect": _("Collect"), "return": _("Return"), "order": _("Order"),
        "owes": _("Owes"), "billed": _("Billed"), "collected": _("Collected"), "late": _("%(days)s days overdue"),
        "no_credit": _("No more credit: an old bill is overdue. Take full payment or collect first."),
        "over_limit": _("Credit limit crossed. Take more payment."), "not_enough": _("Not enough left in the van:"),
        "in_van": _("In van"), "qty": _("Qty"), "price": _("Price"), "total": _("Total"), "paid_now": _("Paid now"),
        "paid_by": _("Paid by"), "cash": _("Cash"), "bank": _("Bank / UPI"), "full": _("Paid in full"),
        "on_credit": _("On credit"), "save": _("Save"), "save_bill": _("Save bill"), "cancel": _("Cancel"),
        "amount": _("Amount"), "item": _("Item"), "pieces": _("Pieces"), "good": _("Good – back in the van"),
        "damaged": _("Damaged – write off"), "price_piece": _("Value per piece"), "note": _("Note"),
        "photo": _("Bill photo"), "kind": _("What for"), "open_orders": _("Open orders"),
        "online": _("Online"), "offline": _("Offline – saved on this phone"), "waiting": _("waiting to send"),
        "send_now": _("Send now"), "sent": _("Sent"), "failed": _("Not saved"), "remove": _("Remove"),
        "whatsapp": _("WhatsApp"), "recent": _("Recent bills"), "other_shop": _("Another shop"),
        "loaded": _("Loaded"), "left": _("Left"), "no_load": _("Nothing loaded: any item can be billed."),
        "sales": _("Sales"), "credit": _("Credit given"), "old_dues": _("Old dues collected"),
        "returns": _("Goods taken back"), "expenses": _("Spent on the line"), "cash_due": _("Cash to hand over"),
        "bills": _("Bills"), "closed": _("This trip is already settled."), "enter_qty": _("Enter a quantity for at least one item."),
        "enter_amount": _("Enter the amount."), "queued": _("Saved on the phone. It will be sent when there is a network."),
        "ordered": _("Ordered"), "start": _("Start trip"), "photo_big": _("The photo could not be read."),
    }


@van_view
def van_app(request, trip_id):
    trip = _trip(request, trip_id)
    return render(request, "webapp/van/app.html", {
        "trip": trip, "state": app_state(request, trip), "manager": _manager(request), "text": app_text(),
        "sync_url": reverse("webapp:van_sync", args=[trip.id]),
    })


def _dec(value):
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except (InvalidOperation, ValueError):
        raise ValidationError(_("Enter a valid number."))


def _customer(trip, value):
    customer = Customer.objects.for_company(trip.company).filter(id=value if str(value).isdigit() else 0).first()
    if customer is None:
        raise ValidationError(_("This shop was not found."))
    return customer


def _product(trip, value):
    product = Product.objects.for_company(trip.company).filter(id=value if str(value).isdigit() else 0).first()
    if product is None:
        raise ValidationError(_("This item was not found."))
    return product


def _pack(product, value):
    if not value:
        return None
    pack = ProductPack.objects.filter(product=product, id=value if str(value).isdigit() else 0).first()
    if pack is None:
        raise ValidationError(_("Choose a valid unit."))
    return pack


def _photo(trip, data, uid):
    if not data:
        return None
    if not isinstance(data, str) or not data.startswith("data:image/") or ";base64," not in data:
        raise ValidationError(_("The photo could not be read."))
    head, raw = data.split(";base64,", 1)
    ext = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}.get(head[len("data:image/"):].lower())
    if ext is None or len(raw) > MAX_PHOTO * 4 // 3:
        raise ValidationError(_("The photo could not be read."))
    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError(_("The photo could not be read."))
    return ContentFile(content, name=f"van-{trip.id}-{uid[:8]}.{ext}")


def _apply(request, trip, op, uid):
    kind, day = op.get("type"), parse_date(str(op.get("day") or ""))
    user = request.user
    if kind == "bill":
        customer = _customer(trip, op.get("customer"))
        lines = []
        for row in op.get("lines") or []:
            product = _product(trip, row.get("product"))
            line = {"product": product, "quantity": _dec(row.get("qty")), "unit_price": _dec(row.get("price"))}
            pack = _pack(product, row.get("unit"))
            if pack:
                line["pack"] = pack
            lines.append(line)
        invoice = svc.sell(trip=trip, user=user, customer=customer, lines=lines, paid=_dec(op.get("paid")),
                           method=op.get("method"), day=day)
        return {"message": _("Bill %(no)s for %(name)s: %(total)s.") % {"no": invoice.invoice_number, "name": customer.name,
                                                                          "total": _s(invoice.total)},
                "invoice": invoice.invoice_number, "wa": _bill_link(request, invoice)}
    if kind == "collect":
        customer = _customer(trip, op.get("customer"))
        row = svc.collect(trip=trip, user=user, customer=customer, amount=_dec(op.get("amount")), method=op.get("method"), day=day)
        return {"message": _("%(amount)s received from %(name)s.") % {"amount": _s(row.amount), "name": customer.name}}
    if kind == "return":
        customer, product = _customer(trip, op.get("customer")), _product(trip, op.get("product"))
        row = svc.take_back(trip=trip, user=user, customer=customer, product=product, quantity=_dec(op.get("qty")),
                            good=bool(op.get("good")), unit_price=op.get("price") or None, day=day)
        return {"message": _("%(qty)s %(item)s taken back from %(name)s.") % {"qty": _q(row.quantity), "item": product.name,
                                                                                "name": customer.name}}
    if kind == "order":
        customer, product = _customer(trip, op.get("customer")), _product(trip, op.get("product"))
        svc.add_order(trip=trip, user=user, customer=customer, product=product, quantity=_dec(op.get("qty")),
                      pack=_pack(product, op.get("unit")), note=str(op.get("note") or ""))
        return {"message": _("Order noted for %(name)s.") % {"name": customer.name}}
    if kind == "cancel_order":
        order = VanOrder.objects.for_company(trip.company).filter(id=op.get("order") if str(op.get("order")).isdigit() else 0,
                                                                  status="open").first()
        if order:
            order.status = "cancelled"
            order.save(update_fields=["status"])
        return {"message": _("Order cancelled.")}
    if kind == "expense":
        row = svc.add_expense(trip=trip, user=user, kind=op.get("kind"), amount=_dec(op.get("amount")),
                              note=str(op.get("note") or ""), photo=_photo(trip, op.get("photo"), uid), day=day)
        return {"message": _("%(amount)s spent on %(what)s.") % {"amount": _s(row.amount), "what": row.get_kind_display()}}
    if kind == "start":
        svc.start(trip)
        return {"message": _("Trip started. Have a good day on the line!")}
    raise ValidationError(_("Unknown action."))


@van_view
@require_POST
def van_sync(request, trip_id):
    trip = _trip(request, trip_id)
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "bad request"}, status=400)
    results = []
    for op in (data.get("ops") or [])[:100]:
        if not isinstance(op, dict):
            continue
        uid = str(op.get("id") or "")[:40]
        if len(uid) < 8:
            continue
        done = VanSyncOp.objects.filter(uid=uid).first()
        if done is not None:
            results.append({"id": uid, **(done.result if done.trip_id == trip.id else {"ok": False, "message": _("Unknown action.")})})
            continue
        try:
            with transaction.atomic():
                result = {"ok": True, **_apply(request, trip, op, uid)}
                VanSyncOp.objects.create(trip=trip, uid=uid, kind=str(op.get("type"))[:12], ok=True, result=result)
        except (ValidationError, Http404) as exc:
            result = {"ok": False, "message": " ".join(getattr(exc, "messages", None) or [str(exc)])}
            VanSyncOp.objects.create(trip=trip, uid=uid, kind=str(op.get("type"))[:12], ok=False, result=result)
        results.append({"id": uid, **result})
        trip.refresh_from_db()
    return JsonResponse({"results": results, "state": app_state(request, trip)})

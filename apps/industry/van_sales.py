"""Van sales: load the van in the morning, bill shops and collect old dues on the line, then hand back
the stock that is left and the cash in the evening.

Stock leaves the branch only when a shop is billed (the normal invoice does that), so goods in the van still
count as the branch's stock. At settlement any stock that should have come back but didn't is written off.
On the line the driver can also take back goods (good ones go back in the van, damaged ones are written off),
note orders for the next visit and record what was spent (fuel, food…) from the cash collected.
"""
import math
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.inventory.services import record_stock_movement
from apps.sales import services as sales
from apps.sales.allocation import allocate_payment, open_invoices
from apps.sales.models import SalesInvoiceLine, SalesReturnLine

from .models import VanOrder, VanSettings, VanTripCollection, VanTripExpense, VanTripLoad, VanTripReturn, VanTripSale

ZERO = Decimal("0")
METHODS = ("cash", "bank")
EXPENSE_CATEGORY = "Van / route expenses"


def _pieces_expr():
    return ExpressionWrapper(F("quantity") * F("unit_factor"), output_field=DecimalField(max_digits=18, decimal_places=3))


def sold(trip):
    """{product_id: pieces billed on this trip}."""
    rows = (SalesInvoiceLine.objects.filter(invoice__van_sale__trip=trip).values("product_id")
            .annotate(q=Sum(_pieces_expr())))
    return {r["product_id"]: r["q"] or ZERO for r in rows}


def taken_back(trip):
    """{product_id: good pieces shops gave back into the van on this trip}."""
    rows = trip.returns.filter(good=True).values("product_id").annotate(q=Sum("quantity"))
    return {r["product_id"]: r["q"] or ZERO for r in rows}


def stock(trip):
    """What is in the van: one row per loaded product with loaded, sold, taken back, left and returned."""
    billed, back = sold(trip), taken_back(trip)
    rows = []
    for load in trip.loads.select_related("product").order_by("product__name"):
        out, came = billed.get(load.product_id, ZERO), back.get(load.product_id, ZERO)
        left = load.loaded - out + came
        rows.append({"load": load, "product": load.product, "loaded": load.loaded, "sold": out, "taken_back": came,
                     "left": left, "returned": load.returned,
                     "short": (left - load.returned) if load.returned is not None else ZERO})
    return rows


def totals(trip):
    """Money of the trip: sales, how much of it was paid now (cash / bank) or left on credit, old dues collected,
    goods taken back, money spent on the line and the cash the driver should hand over."""
    sales_rows = list(trip.sales.select_related("invoice"))
    collections = list(trip.collections.all())
    spent = list(trip.expenses.all())
    sale_total = sum((s.invoice.total for s in sales_rows), ZERO)
    paid_cash = sum((s.paid_now for s in sales_rows if s.method == "cash"), ZERO)
    paid_bank = sum((s.paid_now for s in sales_rows if s.method != "cash"), ZERO)
    coll_cash = sum((c.amount for c in collections if c.method == "cash"), ZERO)
    coll_bank = sum((c.amount for c in collections if c.method != "cash"), ZERO)
    expenses = sum((e.amount for e in spent), ZERO)
    returns = sum((r.quantity * r.unit_price for r in trip.returns.all()), ZERO).quantize(Decimal("0.01"))
    expected = paid_cash + coll_cash - expenses
    handed = trip.cash_handed
    return {"bills": len(sales_rows), "sales": sale_total, "paid_cash": paid_cash, "paid_bank": paid_bank,
            "credit": sale_total - paid_cash - paid_bank, "collected_cash": coll_cash, "collected_bank": coll_bank,
            "collected": coll_cash + coll_bank, "expenses": expenses, "returns": returns,
            "expected_cash": expected, "handed": handed,
            "cash_short": (expected - handed) if handed is not None else ZERO}


def _open(trip):
    if trip.status == "closed":
        raise ValidationError(_("This trip is already settled."))


def _day(trip, day=None):
    """The date an action counts on: today, or the day the phone recorded it while offline (never in the future
    and never before the trip)."""
    today = timezone.localdate()
    if day is None or day > today:
        return today
    return max(day, trip.date)


def set_load(trip, product, quantity):
    """Loads (or corrects) how much of a product went into the van. 0 takes it off the list."""
    _open(trip)
    quantity = Decimal(quantity)
    if quantity < 0:
        raise ValidationError(_("Enter a quantity of 0 or more."))
    if not product.is_stock_tracked:
        raise ValidationError(_("Only stock items can be loaded."))
    out = sold(trip).get(product.id, ZERO) - taken_back(trip).get(product.id, ZERO)
    if quantity < out:
        raise ValidationError(_("%(sold)s of %(name)s are already billed on this trip.")
                              % {"sold": f"{out.normalize():f}", "name": product.name})
    if quantity == 0 and not out and not trip.returns.filter(product=product).exists():
        VanTripLoad.objects.filter(trip=trip, product=product).delete()
        return None
    load, _created = VanTripLoad.objects.update_or_create(trip=trip, product=product, defaults={"loaded": quantity})
    return load


def start(trip):
    _open(trip)
    if trip.status == "loading":
        trip.status, trip.started_at = "out", timezone.now()
        trip.save(update_fields=["status", "started_at"])


def overdue(company, customer, days):
    """(oldest invoice, days overdue) when the shop has a bill overdue by more than `days`, else None."""
    today = timezone.localdate()
    for invoice in open_invoices(company, customer):
        if invoice.due_date and (today - invoice.due_date).days > days:
            return invoice, (today - invoice.due_date).days
    return None


def credit_check(company, customer, credit, settings=None):
    """Raises if `credit` more on account isn't allowed: over the credit limit, or an old bill is overdue."""
    if credit <= 0:
        return
    settings = settings or VanSettings.load(company)
    if settings.block_overdue_days:
        late = overdue(company, customer, settings.block_overdue_days)
        if late:
            raise ValidationError(_("No more credit for %(name)s: bill %(no)s is %(days)s days overdue. Collect it first or take full payment.")
                                  % {"name": customer.name, "no": late[0].invoice_number, "days": late[1]})
    if customer.credit_limit:
        from apps.collections.services import customer_credit_status
        owed = customer_credit_status(company, customer)["outstanding"]
        if owed + credit > customer.credit_limit:
            raise ValidationError(_("Credit limit crossed: %(name)s already owes %(owed)s (limit %(limit)s).")
                                  % {"name": customer.name, "owed": f"{owed:.2f}", "limit": f"{customer.credit_limit:.2f}"})


def sell(*, trip, user, customer, lines, paid=ZERO, method="cash", day=None):
    """Bills a shop from the van. lines: [{"product", "quantity", "unit_price", "pack"?}]. `paid` is what the shop
    pays now (cash or bank); the rest stays on the shop's account as credit. Returns the invoice."""
    _open(trip)
    lines = [l for l in lines if Decimal(l["quantity"]) != 0]
    if not lines:
        raise ValidationError(_("Enter a quantity for at least one item."))
    for line in lines:
        if Decimal(line["quantity"]) < 0 or Decimal(line["unit_price"]) < 0:
            raise ValidationError(_("Quantities and prices can't be negative."))
    loads = {l.product_id: l for l in trip.loads.all()}
    if loads:  # the van was loaded: only what is in it can be sold
        billed, back = sold(trip), taken_back(trip)
        left = {pid: load.loaded - billed.get(pid, ZERO) + back.get(pid, ZERO) for pid, load in loads.items()}
        for line in lines:
            pieces = Decimal(line["quantity"]) * (line["pack"].factor if line.get("pack") else 1)
            pid = line["product"].id
            if pid not in left:
                raise ValidationError(_("%(name)s is not loaded in this van.") % {"name": line["product"].name})
            left[pid] -= pieces
            if left[pid] < 0:
                raise ValidationError(_("Not enough %(name)s left in the van.") % {"name": line["product"].name})
    total = sum((Decimal(l["quantity"]) * Decimal(l["unit_price"]) for l in lines), ZERO)
    paid = Decimal(paid or 0)
    if paid < 0 or paid > total:
        raise ValidationError(_("Paid now must be between 0 and the bill total."))
    method = method if method in METHODS else "cash"
    credit_check(trip.company, customer, total - paid)
    day = _day(trip, day)
    with transaction.atomic():
        start(trip)
        invoice = sales.create_invoice(company=trip.company, user=user, customer=customer, date=day,
                                       lines=lines, warehouse=trip.warehouse)
        if paid:
            sales.record_customer_payment(company=trip.company, user=user, customer=customer, amount=paid,
                                          date=day, invoice=invoice, method=method)
        VanTripSale.objects.create(trip=trip, invoice=invoice, paid_now=paid, method=method)
        billed_products = {l["product"].id for l in lines}
        VanOrder.objects.for_company(trip.company).filter(customer=customer, status="open",
                                                          product_id__in=billed_products).update(status="billed", invoice=invoice)
    return invoice


def collect(*, trip, user, customer, amount, method="cash", day=None):
    """A shop pays old dues to the driver: applied to its oldest open bills first."""
    _open(trip)
    amount = Decimal(amount or 0).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError(_("Enter the amount received."))
    method = method if method in METHODS else "cash"
    with transaction.atomic():
        start(trip)
        receipts, _left = allocate_payment(company=trip.company, user=user, customer=customer, amount=amount,
                                           date=_day(trip, day), method=method)
        return VanTripCollection.objects.create(trip=trip, customer=customer, amount=amount, method=method,
                                                receipts=", ".join(receipts)[:255])


def take_back(*, trip, user, customer, product, quantity, good=True, unit_price=None, day=None):
    """A shop gives goods back. The value comes off the shop's account (against its latest bill with that item);
    good pieces go back into the van, damaged ones are written off."""
    _open(trip)
    quantity = Decimal(quantity or 0)
    if quantity <= 0:
        raise ValidationError(_("Enter how many pieces came back."))
    lines = (SalesInvoiceLine.objects.filter(invoice__company=trip.company, invoice__customer=customer, product=product)
             .exclude(invoice__status="void").select_related("invoice").order_by("-invoice__date", "-id"))
    target = None
    for line in lines:
        bought = sum((l.quantity * l.unit_factor for l in line.invoice.lines.filter(product=product)), ZERO)
        back = SalesReturnLine.objects.filter(sales_return__invoice=line.invoice, product=product).aggregate(
            q=Sum(_pieces_expr()))["q"] or ZERO
        if bought - back >= quantity:
            target = line
            break
    if target is None:
        raise ValidationError(_("%(name)s didn't buy that many %(item)s on one bill.") % {"name": customer.name, "item": product.name})
    per_piece = (Decimal(unit_price) if unit_price not in (None, "") else
                 (target.unit_price / (target.unit_factor or 1))).quantize(Decimal("0.01"))
    if per_piece < 0:
        raise ValidationError(_("Quantities and prices can't be negative."))
    day = _day(trip, day)
    with transaction.atomic():
        start(trip)
        sales_return = sales.process_return(
            company=trip.company, user=user, invoice=target.invoice, date=day, warehouse=trip.warehouse,
            lines=[{"product": product, "quantity": quantity, "unit_price": per_piece}],
            reason=_("Van return – good") if good else _("Van return – damaged"), refund_method="store_credit")
        if good:
            if trip.loads.exists() and not trip.loads.filter(product=product).exists():
                VanTripLoad.objects.create(trip=trip, product=product, loaded=ZERO)
        elif product.is_stock_tracked:
            record_stock_movement(company=trip.company, product=product, warehouse=trip.warehouse, quantity=-quantity,
                                  reason="adjustment", reference=f"VAN-{trip.id} damaged")
        return VanTripReturn.objects.create(trip=trip, customer=customer, product=product, quantity=quantity,
                                            unit_price=per_piece, good=good, sales_return=sales_return)


def add_order(*, trip, user, customer, product, quantity, pack=None, note=""):
    quantity = Decimal(quantity or 0)
    if quantity <= 0:
        raise ValidationError(_("Enter the quantity ordered."))
    if pack is not None and pack.product_id != product.id:
        raise ValidationError(_("Choose a valid unit."))
    return VanOrder.objects.create(company=trip.company, customer=customer, product=product, pack=pack,
                                   quantity=quantity, note=(note or "")[:200], trip=trip, created_by=user)


def add_expense(*, trip, user, kind, amount, note="", photo=None, day=None):
    """Money spent on the line from the cash collected: booked as a business expense (paid in cash)."""
    from apps.expenses.models import ExpenseCategory
    from apps.expenses.services import record_expense
    _open(trip)
    amount = Decimal(amount or 0).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError(_("Enter the amount spent."))
    kind = kind if kind in dict(VanTripExpense.KINDS) else "other"
    category = (ExpenseCategory.objects.for_company(trip.company).filter(name=EXPENSE_CATEGORY).first()
                or ExpenseCategory.objects.create(company=trip.company, name=EXPENSE_CATEGORY))
    label = dict(VanTripExpense.KINDS)[kind]
    with transaction.atomic():
        start(trip)
        expense = record_expense(company=trip.company, user=user, category=category, date=_day(trip, day), amount=amount,
                                 description=f"{label} · VAN-{trip.id}" + (f" · {note}" if note else ""), payment_method="cash")
        row = VanTripExpense(trip=trip, kind=kind, amount=amount, note=(note or "")[:200], expense=expense)
        if photo is not None:
            from apps.common.validators import validate_upload_file
            validate_upload_file(photo)
            row.photo = photo
        row.save()
    return row


def load_suggestion(trip, last=3):
    """Per product: pieces the line's shops ordered, pieces usually sold on this line (average of the last
    `last` settled trips) and the suggestion — the bigger of the two."""
    from .models import VanTrip
    rows = {}
    if trip.route_id:
        shops = trip.route.stops.values_list("customer_id", flat=True)
        for order in VanOrder.objects.for_company(trip.company).filter(status="open", customer_id__in=shops).select_related("product", "pack"):
            row = rows.setdefault(order.product_id, {"product": order.product, "ordered": ZERO, "usual": ZERO})
            row["ordered"] += order.pieces
        past = list(VanTrip.objects.for_company(trip.company).filter(route=trip.route, status="closed")
                    .exclude(id=trip.id).order_by("-date", "-id")[:last])
        for t in past:
            for pid, qty in sold(t).items():
                row = rows.setdefault(pid, {"product": None, "ordered": ZERO, "usual": ZERO})
                row["usual"] += qty / len(past)
        missing = [pid for pid, r in rows.items() if r["product"] is None]
        if missing:
            from apps.inventory.models import Product
            for p in Product.objects.filter(id__in=missing):
                rows[p.id]["product"] = p
    loaded = {l.product_id: l.loaded for l in trip.loads.all()}
    out = []
    for pid, r in rows.items():
        r["usual"] = Decimal(math.ceil(r["usual"]))
        r["suggested"] = max(r["ordered"], r["usual"])
        r["loaded"] = loaded.get(pid, ZERO)
        if r["product"] is not None and r["product"].is_stock_tracked and r["suggested"] > 0:
            out.append(r)
    return sorted(out, key=lambda r: r["product"].name)


def close(*, trip, user, returned, cash_handed):
    """Evening settlement. returned: {product_id: pieces back}. Stock missing from the van is written off;
    the cash handed over is kept against what the driver collected in cash less what was spent."""
    _open(trip)
    cash_handed = Decimal(cash_handed if cash_handed not in (None, "") else -1)
    if cash_handed < 0:
        raise ValidationError(_("Enter the cash the driver handed over."))
    rows = stock(trip)
    with transaction.atomic():
        for row in rows:
            back = Decimal(returned.get(row["product"].id, row["left"]))
            if back < 0 or back > row["left"]:
                raise ValidationError(_("%(name)s: returned must be between 0 and %(left)s.")
                                      % {"name": row["product"].name, "left": f"{row['left'].normalize():f}"})
            missing = row["left"] - back
            if missing:
                record_stock_movement(company=trip.company, product=row["product"], warehouse=trip.warehouse,
                                      quantity=-missing, reason="adjustment", reference=f"VAN-{trip.id} short")
            row["load"].returned = back
            row["load"].save(update_fields=["returned"])
        trip.status, trip.closed_at, trip.closed_by, trip.cash_handed = "closed", timezone.now(), user, cash_handed
        if not trip.started_at:
            trip.started_at = trip.closed_at
        trip.save(update_fields=["status", "closed_at", "closed_by", "cash_handed", "started_at"])
    if VanSettings.load(trip.company).notify_owner:
        transaction.on_commit(lambda: notify_owner(trip))
    return trip


def summary_text(trip):
    m = totals(trip)
    cur = trip.company.default_currency
    driver = (trip.driver.get_full_name() or trip.driver.username) if trip.driver else "-"
    lines = [f"🚚 {trip.route.name if trip.route else _('Extra trip')} · {trip.date:%d %b} · {driver}",
             f"{_('Sales')}: {cur} {m['sales']:.2f} ({m['bills']} {_('bills')})",
             f"{_('Paid now')}: {cur} {m['paid_cash'] + m['paid_bank']:.2f} · {_('Credit given')}: {cur} {m['credit']:.2f}",
             f"{_('Old dues collected')}: {cur} {m['collected']:.2f}"]
    if m["returns"]:
        lines.append(f"{_('Goods taken back')}: {cur} {m['returns']:.2f}")
    if m["expenses"]:
        lines.append(f"{_('Spent on the line')}: {cur} {m['expenses']:.2f}")
    lines.append(f"{_('Cash due')}: {cur} {m['expected_cash']:.2f} · {_('Cash handed')}: {cur} {(m['handed'] or ZERO):.2f}")
    if m["cash_short"] > 0:
        lines.append(f"⚠️ {_('Cash short')}: {cur} {m['cash_short']:.2f}")
    short = [r for r in stock(trip) if r["short"]]
    if short:
        lines.append("⚠️ " + _("Stock short") + ": " + ", ".join(f"{r['product'].name} {r['short'].normalize():f}" for r in short))
    return "\n".join(lines)


def notify_owner(trip):
    """In-app notification and an email to the owners when a trip is settled."""
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.notifications.daily_report import recipients
    from apps.notifications.models import DailyReportSettings, Notification
    text = summary_text(trip)
    title = _("Van trip settled") + f" · {trip.route.name if trip.route else _('Extra trip')}"
    Notification.objects.create(company=trip.company, notif_type="general", title=title[:200], message=text)
    to = recipients(trip.company, DailyReportSettings.load(trip.company))
    if to:
        try:
            send_mail(f"{trip.company.name} — {title}", text, getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"), to)
        except Exception:  # email not set up: the in-app notification is still there
            pass


def owner_whatsapp_link(trip):
    from apps.notifications.daily_report import whatsapp_link
    return whatsapp_link(trip.company, summary_text(trip))

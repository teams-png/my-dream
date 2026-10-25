"""Van sales: load the van in the morning, bill shops and collect old dues on the line, then hand back
the stock that is left and the cash in the evening.

Stock leaves the branch only when a shop is billed (the normal invoice does that), so goods in the van still
count as the branch's stock. At settlement any stock that should have come back but didn't is written off.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.inventory.services import record_stock_movement
from apps.sales import services as sales
from apps.sales.allocation import allocate_payment
from apps.sales.models import SalesInvoiceLine

from .models import VanTripCollection, VanTripLoad, VanTripSale

ZERO = Decimal("0")
METHODS = ("cash", "bank")


def sold(trip):
    """{product_id: pieces billed on this trip}."""
    pieces = ExpressionWrapper(F("quantity") * F("unit_factor"), output_field=DecimalField(max_digits=18, decimal_places=3))
    rows = (SalesInvoiceLine.objects.filter(invoice__van_sale__trip=trip).values("product_id")
            .annotate(q=Sum(pieces)))
    return {r["product_id"]: r["q"] or ZERO for r in rows}


def stock(trip):
    """What is in the van: one row per loaded product with loaded, sold, left and (after settlement) returned."""
    billed = sold(trip)
    rows = []
    for load in trip.loads.select_related("product").order_by("product__name"):
        out = billed.get(load.product_id, ZERO)
        rows.append({"load": load, "product": load.product, "loaded": load.loaded, "sold": out,
                     "left": load.loaded - out, "returned": load.returned,
                     "short": (load.loaded - out - load.returned) if load.returned is not None else ZERO})
    return rows


def totals(trip):
    """Money of the trip: sales, how much of it was paid now (cash / bank) or left on credit, old dues collected
    and the cash the driver should hand over."""
    sales_rows = list(trip.sales.select_related("invoice"))
    collections = list(trip.collections.all())
    sale_total = sum((s.invoice.total for s in sales_rows), ZERO)
    paid_cash = sum((s.paid_now for s in sales_rows if s.method == "cash"), ZERO)
    paid_bank = sum((s.paid_now for s in sales_rows if s.method != "cash"), ZERO)
    coll_cash = sum((c.amount for c in collections if c.method == "cash"), ZERO)
    coll_bank = sum((c.amount for c in collections if c.method != "cash"), ZERO)
    expected = paid_cash + coll_cash
    handed = trip.cash_handed
    return {"bills": len(sales_rows), "sales": sale_total, "paid_cash": paid_cash, "paid_bank": paid_bank,
            "credit": sale_total - paid_cash - paid_bank, "collected_cash": coll_cash, "collected_bank": coll_bank,
            "collected": coll_cash + coll_bank, "expected_cash": expected, "handed": handed,
            "cash_short": (expected - handed) if handed is not None else ZERO}


def _open(trip):
    if trip.status == "closed":
        raise ValidationError(_("This trip is already settled."))


def set_load(trip, product, quantity):
    """Loads (or corrects) how much of a product went into the van. 0 takes it off the list."""
    _open(trip)
    quantity = Decimal(quantity)
    if quantity < 0:
        raise ValidationError(_("Enter a quantity of 0 or more."))
    if not product.is_stock_tracked:
        raise ValidationError(_("Only stock items can be loaded."))
    out = sold(trip).get(product.id, ZERO)
    if quantity < out:
        raise ValidationError(_("%(sold)s of %(name)s are already billed on this trip.")
                              % {"sold": f"{out.normalize():f}", "name": product.name})
    if quantity == 0:
        VanTripLoad.objects.filter(trip=trip, product=product).delete()
        return None
    load, _created = VanTripLoad.objects.update_or_create(trip=trip, product=product, defaults={"loaded": quantity})
    return load


def start(trip):
    _open(trip)
    if trip.status == "loading":
        trip.status, trip.started_at = "out", timezone.now()
        trip.save(update_fields=["status", "started_at"])


def sell(*, trip, user, customer, lines, paid=ZERO, method="cash"):
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
        left = {pid: load.loaded - sold(trip).get(pid, ZERO) for pid, load in loads.items()}
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
    if customer.credit_limit and paid < total:
        from apps.collections.services import customer_credit_status
        owed = customer_credit_status(trip.company, customer)["outstanding"]
        if owed + total - paid > customer.credit_limit:
            raise ValidationError(_("Credit limit crossed: %(name)s already owes %(owed)s (limit %(limit)s).")
                                  % {"name": customer.name, "owed": f"{owed:.2f}", "limit": f"{customer.credit_limit:.2f}"})
    today = timezone.localdate()
    with transaction.atomic():
        start(trip)
        invoice = sales.create_invoice(company=trip.company, user=user, customer=customer, date=today,
                                       lines=lines, warehouse=trip.warehouse)
        if paid:
            sales.record_customer_payment(company=trip.company, user=user, customer=customer, amount=paid,
                                          date=today, invoice=invoice, method=method)
        VanTripSale.objects.create(trip=trip, invoice=invoice, paid_now=paid, method=method)
    return invoice


def collect(*, trip, user, customer, amount, method="cash"):
    """A shop pays old dues to the driver: applied to its oldest open bills first."""
    _open(trip)
    amount = Decimal(amount or 0).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError(_("Enter the amount received."))
    method = method if method in METHODS else "cash"
    with transaction.atomic():
        start(trip)
        receipts, _left = allocate_payment(company=trip.company, user=user, customer=customer, amount=amount,
                                           date=timezone.localdate(), method=method)
        return VanTripCollection.objects.create(trip=trip, customer=customer, amount=amount, method=method,
                                                receipts=", ".join(receipts)[:255])


def close(*, trip, user, returned, cash_handed):
    """Evening settlement. returned: {product_id: pieces back}. Stock missing from the van is written off;
    the cash handed over is kept against what the driver collected in cash."""
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
    return trip

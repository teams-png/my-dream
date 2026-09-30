"""Stock for every business: overview, adjustments, transfers between branches, stock taking,
batches with expiry, serial numbers and each item's movement history."""
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.inventory import services as inv
from apps.inventory.models import (Product, ProductBatch, ProductCategory, ProductSerial, StockCount, StockCountLine,
                                   StockMovement, Warehouse)

from . import xlsx
from .views import require_permission

VIEW = "inventory.view_products"
MANAGE = "inventory.manage_stock"
ZERO = Decimal("0")
ADJUST_REASONS = [("damaged", gettext_lazy("Damaged")), ("expired", gettext_lazy("Expired")), ("lost", gettext_lazy("Lost / stolen")),
                  ("own_use", gettext_lazy("Own use")), ("found", gettext_lazy("Found extra")), ("correction", gettext_lazy("Correction")),
                  ("opening", gettext_lazy("Opening stock"))]


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))


def _warehouses(company):
    qs = Warehouse.objects.for_company(company).filter(is_active=True).order_by("-is_default", "name")
    if not qs.exists():
        Warehouse.objects.create(company=company, name="Main Branch", is_active=True, is_default=True)
    return qs


def _stock_map(company):
    """{(product_id, warehouse_id): qty} in one query."""
    rows = (StockMovement.objects.for_company(company).values("product_id", "warehouse_id")
            .annotate(q=Sum("quantity")))
    return {(r["product_id"], r["warehouse_id"]): r["q"] or ZERO for r in rows}


def _dec(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


# ------------------------------------------------------------------ overview

@login_required
@require_permission(VIEW)
def stock_home(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = list(_warehouses(company))
    stock = _stock_map(company)
    show = request.GET.get("show", "all")
    query = (request.GET.get("q") or "").strip()
    category = request.GET.get("category") or ""
    products = Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).select_related("category", "unit").order_by("name")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    if category:
        products = products.filter(category_id=category)
    rows, value, low, out = [], ZERO, 0, 0
    for p in products:
        per = [stock.get((p.id, w.id), ZERO) for w in warehouses]
        total = sum(per, ZERO)
        is_low = total <= p.reorder_level
        low += is_low and total > 0
        out += total <= 0
        value += max(total, ZERO) * p.cost_price
        if show == "low" and not (is_low and total > 0):
            continue
        if show == "out" and total > 0:
            continue
        rows.append({"p": p, "per": per, "total": total, "low": is_low, "value": max(total, ZERO) * p.cost_price})
    if xlsx.wants(request):
        data = [[_("Item"), _("SKU"), _("Category"), *[w.name for w in warehouses], _("Total"), _("Unit"),
                 _("Reorder level"), _("Cost"), _("Stock value"), _("Low")]]
        data += [[r["p"].name, r["p"].sku, getattr(r["p"].category, "name", ""), *r["per"], r["total"],
                  getattr(r["p"].unit, "name", ""), r["p"].reorder_level, r["p"].cost_price, r["value"], bool(r["low"])]
                 for r in rows]
        data.append([xlsx.Bold(_("Total")), *[""] * (len(warehouses) + 7), sum((r["value"] for r in rows), ZERO)])
        return xlsx.response(f"stock-{timezone.localdate()}", [(_("Stock"), data)])
    today = timezone.localdate()
    expiring = ProductBatch.objects.for_company(company).filter(expiry_date__isnull=False, expiry_date__lte=today + timedelta(days=30)).count()
    page = Paginator(rows, 60).get_page(request.GET.get("page"))
    return render(request, "webapp/stock/home.html", {
        "page": page, "warehouses": warehouses, "show": show, "q": query, "category": category,
        "categories": ProductCategory.objects.for_company(company).order_by("name"),
        "stats": {"items": len(rows) if show == "all" else products.count(), "value": value, "low": low, "out": out, "expiring": expiring},
    })


@login_required
@require_permission(VIEW)
def stock_history(request, product_id):
    company = request.company
    product = get_object_or_404(Product.objects.for_company(company), id=product_id)
    moves = StockMovement.objects.for_company(company).filter(product=product).select_related("warehouse", "batch", "serial").order_by("moved_at", "id")
    warehouse = request.GET.get("warehouse") or ""
    if warehouse:
        moves = moves.filter(warehouse_id=warehouse)
    rows, running = [], ZERO
    for m in moves:
        running += m.quantity
        rows.append({"m": m, "balance": running})
    rows.reverse()
    return render(request, "webapp/stock/history.html", {
        "product": product, "rows": rows[:500], "balance": running, "warehouse": warehouse,
        "warehouses": _warehouses(company)})


# ------------------------------------------------------------------ adjust & transfer

@login_required
@require_permission(MANAGE)
def stock_adjust(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = _warehouses(company)
    if request.method == "POST":
        product = Product.objects.for_company(company).filter(id=request.POST.get("product")).first()
        warehouse = warehouses.filter(id=request.POST.get("warehouse")).first()
        qty = _dec(request.POST.get("quantity") or "")
        direction = request.POST.get("direction")
        reason = request.POST.get("reason") or "correction"
        if not product or not warehouse or not qty or qty <= 0:
            messages.error(request, _("Choose an item, a location and a quantity."))
        else:
            delta = qty if direction == "in" else -qty
            try:
                label = dict(ADJUST_REASONS).get(reason, reason)
                note = f"{label}: {(request.POST.get('note') or '').strip()}".strip(": ")[:100]
                inv.create_stock_adjustment(company=company, user=request.user, product=product, warehouse=warehouse,
                                            quantity_delta=delta, reason_note=note)
                messages.success(request, _("Stock of %(item)s changed by %(qty)s.") % {"item": product.name, "qty": f"{delta.normalize():f}"})
                return redirect(f"{request.path}?product={product.id}")
            except ValidationError as exc:
                _err(request, exc)
    recent = (StockMovement.objects.for_company(company).filter(reason="adjustment").select_related("product", "warehouse")
              .order_by("-moved_at")[:20])
    return render(request, "webapp/stock/adjust.html", {
        "warehouses": warehouses, "reasons": ADJUST_REASONS, "recent": recent,
        "products": Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).order_by("name"),
        "selected": request.GET.get("product") or ""})


@login_required
@require_permission(MANAGE)
def stock_transfer(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = _warehouses(company)
    if request.method == "POST":
        source = warehouses.filter(id=request.POST.get("from")).first()
        target = warehouses.filter(id=request.POST.get("to")).first()
        moved, errors = 0, []
        with transaction.atomic():
            for pid, qty in zip(request.POST.getlist("product"), request.POST.getlist("qty")):
                if not pid:
                    continue
                product = Product.objects.for_company(company).filter(id=pid).first()
                quantity = _dec(qty or "")
                if not product or not quantity or quantity <= 0 or not source or not target:
                    errors.append(_("Choose both locations, an item and a quantity on every line."))
                    continue
                try:
                    with transaction.atomic():
                        inv.create_stock_transfer(company=company, user=request.user, product=product, from_warehouse=source,
                                                  to_warehouse=target, quantity=quantity,
                                                  reference=(request.POST.get("reference") or "")[:100])
                    moved += 1
                except ValidationError as exc:
                    errors.append(f"{product.name}: " + "; ".join(exc.messages))
        for error in dict.fromkeys(errors):
            messages.error(request, error)
        if moved:
            messages.success(request, _("%(count)s items moved from %(from)s to %(to)s.") % {"count": moved, "from": source.name, "to": target.name})
            return redirect("webapp:stock_transfer")
    recent = (StockMovement.objects.for_company(company).filter(reason="transfer_in").select_related("product", "warehouse")
              .order_by("-moved_at")[:20])
    stock = _stock_map(company)
    products = list(Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).order_by("name"))
    for p in products:
        p.stock_json = json.dumps({str(w.id): f"{stock.get((p.id, w.id), ZERO):f}" for w in warehouses})
    return render(request, "webapp/stock/transfer.html", {"warehouses": warehouses, "products": products, "recent": recent})


# ------------------------------------------------------------------ stock taking

@login_required
@require_permission(MANAGE)
def count_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = _warehouses(company)
    if request.method == "POST":
        warehouse = warehouses.filter(id=request.POST.get("warehouse")).first()
        products = Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).order_by("name")
        if request.POST.get("category"):
            products = products.filter(category_id=request.POST.get("category"))
        if not warehouse or not products.exists():
            messages.error(request, _("Choose a location that has items to count."))
        else:
            count = inv.start_stock_count(company=company, user=request.user, warehouse=warehouse, products=list(products))
            return redirect("webapp:count_detail", count.id)
    counts = StockCount.objects.for_company(company).select_related("warehouse", "created_by").order_by("-created_at")[:40]
    return render(request, "webapp/stock/counts.html", {
        "counts": counts, "warehouses": warehouses, "categories": ProductCategory.objects.for_company(company).order_by("name")})


@login_required
@require_permission(MANAGE)
def count_detail(request, count_id):
    company = request.company
    count = get_object_or_404(StockCount.objects.for_company(company).select_related("warehouse"), id=count_id)
    lines = list(count.lines.select_related("product", "product__unit").order_by("product__name"))
    if request.method == "POST" and count.status == "draft":
        try:
            with transaction.atomic():
                for line in lines:
                    raw = request.POST.get(f"c_{line.id}")
                    if raw is None:
                        continue
                    if raw.strip() == "":
                        if line.counted_quantity is not None:
                            line.counted_quantity = None
                            line.save(update_fields=["counted_quantity"])
                        continue
                    qty = _dec(raw)
                    if qty is None or qty < 0:
                        raise ValidationError(_("Counted quantities must be zero or more."))
                    inv.submit_stock_count_line(company=company, stock_count_line=line, counted_quantity=qty)
                if request.POST.get("action") == "complete":
                    inv.complete_stock_count(company=company, user=request.user, stock_count=count)
                    messages.success(request, _("Stock count completed. Stock corrected where it was different."))
                else:
                    messages.success(request, _("Progress saved."))
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:count_detail", count.id)
    counted = sum(1 for l in lines if l.counted_quantity is not None)
    short = sum((abs(l.variance) * l.product.cost_price for l in lines if l.variance and l.variance < 0), ZERO)
    extra = sum((l.variance * l.product.cost_price for l in lines if l.variance and l.variance > 0), ZERO)
    return render(request, "webapp/stock/count_detail.html", {
        "count": count, "lines": lines, "counted": counted, "short_value": short, "extra_value": extra,
        "differences": sum(1 for l in lines if l.variance)})


# ------------------------------------------------------------------ batches & serials

@login_required
@require_permission(VIEW)
def batches(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = _warehouses(company)
    if request.method == "POST":
        if request.role and not request.role.permissions.filter(permission__code=MANAGE).exists():
            messages.error(request, _("You don't have permission to do that."))
            return redirect("webapp:stock_batches")
        product = Product.objects.for_company(company).filter(id=request.POST.get("product")).first()
        warehouse = warehouses.filter(id=request.POST.get("warehouse")).first()
        qty = _dec(request.POST.get("quantity") or "0") or ZERO
        number = (request.POST.get("batch_number") or "").strip()
        if not product or not number:
            messages.error(request, _("Choose an item and enter the batch number."))
        else:
            try:
                with transaction.atomic():
                    if product.tracking_type != "batch":
                        product.tracking_type = "batch"
                        product.save(update_fields=["tracking_type"])
                    batch = ProductBatch.objects.for_company(company).filter(product=product, batch_number=number).first() or \
                        inv.create_batch(company=company, product=product, batch_number=number[:100],
                                         manufacture_date=parse_date(request.POST.get("manufacture_date") or "") or None,
                                         expiry_date=parse_date(request.POST.get("expiry_date") or "") or None)
                    if qty > 0 and warehouse:
                        inv.receive_batch_stock(company=company, product=product, warehouse=warehouse, batch=batch,
                                                quantity=qty, reference=_("Batch received"))
                messages.success(request, _("Batch %(number)s saved.") % {"number": number})
                return redirect("webapp:stock_batches")
            except (ValidationError, IntegrityError) as exc:
                _err(request, exc)
    today = timezone.localdate()
    show = request.GET.get("show", "stock")
    qty = {r["batch_id"]: r["q"] for r in StockMovement.objects.for_company(company).filter(batch__isnull=False)
           .values("batch_id").annotate(q=Sum("quantity"))}
    rows = []
    for b in ProductBatch.objects.for_company(company).select_related("product").order_by("expiry_date", "batch_number"):
        stock = qty.get(b.id) or ZERO
        days = (b.expiry_date - today).days if b.expiry_date else None
        state = "expired" if days is not None and days < 0 else "soon" if days is not None and days <= 30 else "ok"
        if show == "stock" and stock <= 0:
            continue
        if show == "expiring" and (state == "ok" or stock <= 0):
            continue
        rows.append({"b": b, "stock": stock, "days": days, "state": state, "value": max(stock, ZERO) * b.product.cost_price})
    return render(request, "webapp/stock/batches.html", {
        "rows": rows, "show": show, "warehouses": warehouses, "today": today,
        "at_risk": sum((r["value"] for r in rows if r["state"] != "ok"), ZERO),
        "products": Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).order_by("name")})


@login_required
@require_permission(VIEW)
def serials(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    warehouses = _warehouses(company)
    if request.method == "POST":
        if request.role and not request.role.permissions.filter(permission__code=MANAGE).exists():
            messages.error(request, _("You don't have permission to do that."))
            return redirect("webapp:stock_serials")
        product = Product.objects.for_company(company).filter(id=request.POST.get("product")).first()
        warehouse = warehouses.filter(id=request.POST.get("warehouse")).first()
        numbers = [n.strip() for n in (request.POST.get("serials") or "").replace(",", "\n").splitlines() if n.strip()]
        if not product or not warehouse or not numbers:
            messages.error(request, _("Choose an item, a location and enter at least one serial number."))
        else:
            added, skipped = 0, []
            if product.tracking_type != "serial":
                product.tracking_type = "serial"
                product.save(update_fields=["tracking_type"])
            for number in dict.fromkeys(numbers):
                try:
                    with transaction.atomic():
                        inv.register_serial(company=company, product=product, warehouse=warehouse, serial_number=number[:150],
                                            received_date=timezone.localdate())
                    added += 1
                except (ValidationError, IntegrityError):
                    skipped.append(number)
            if added:
                messages.success(request, _("%(count)s serial numbers added to stock.") % {"count": added})
            if skipped:
                messages.error(request, _("Already registered: %(list)s") % {"list": ", ".join(skipped[:20])})
            return redirect("webapp:stock_serials")
    query = (request.GET.get("q") or "").strip()
    status = request.GET.get("status", "in_stock")
    qs = ProductSerial.objects.for_company(company).select_related("product", "warehouse").order_by("-created_at")
    if query:
        qs = qs.filter(Q(serial_number__icontains=query) | Q(product__name__icontains=query))
    if status:
        qs = qs.filter(status=status)
    found = None
    if query:
        found = ProductSerial.objects.for_company(company).filter(serial_number__iexact=query).select_related("product", "warehouse").first()
        if found:
            found.moves = found.movements.select_related("warehouse").order_by("moved_at")
    return render(request, "webapp/stock/serials.html", {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")), "q": query, "status": status, "found": found,
        "warehouses": warehouses, "statuses": ProductSerial.STATUS,
        "products": Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True).order_by("name"),
        "in_stock": ProductSerial.objects.for_company(company).filter(status="in_stock").count()})

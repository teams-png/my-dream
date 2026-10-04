"""Purchase orders → goods receipt (GRN) → supplier bill, bill details and purchase returns."""
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.inventory.models import Product, Warehouse
from apps.purchases import services as purchases
from apps.purchases.models import GoodsReceiptNote, Purchase, PurchaseOrder, PurchaseReturn
from apps.suppliers.models import Supplier

from .sales_docs_views import _err, _parse_lines, _warehouse
from .views import require_permission
from apps.common.safe_json import script_json

CREATE = "purchases.create_purchase"
VIEW = "purchases.view_purchase"
ZERO = Decimal("0")


def _supplier(request, company):
    supplier_id = request.POST.get("customer")
    if supplier_id:
        return Supplier.objects.for_company(company).filter(id=supplier_id).first()
    name = (request.POST.get("customer_name") or "").strip()
    if name:
        return Supplier.objects.create(company=company, name=name[:255], phone=(request.POST.get("customer_phone") or "")[:20])
    return None


def _cost_catalog(company):
    return [{"id": p.id, "name": p.name, "sku": p.sku, "price": f"{p.cost_price:.2f}"}
            for p in Product.objects.for_company(company).filter(is_active=True).order_by("name")[:3000]]


def _po_share(company, po, lines, total):
    rows = [company.name, f"{_('Purchase order')} {po.number}", po.supplier.name]
    rows += [f"• {l.product.name} × {l.quantity.normalize():f}" for l in lines]
    if po.expected_date:
        rows.append(f"{_('Expected delivery')}: {po.expected_date:%d %b %Y}")
    rows.append(f"{_('Total')}: {company.default_currency} {total:.2f}")
    phone = "".join(ch for ch in (po.supplier.phone or "") if ch.isdigit())
    return f"https://wa.me/{phone}?text={quote(chr(10).join(rows))}"


# ------------------------------------------------------------------ purchase orders

@login_required
@require_permission(VIEW)
def po_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    status = request.GET.get("status") or ""
    qs = PurchaseOrder.objects.for_company(company).select_related("supplier").annotate(total=Sum("lines__line_total")).order_by("-date", "-id")
    if status:
        qs = qs.filter(status=status)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(number__icontains=query) | Q(supplier__name__icontains=query) | Q(reference__icontains=query))
    return render(request, "webapp/purchase_docs/po_list.html", {
        "page": Paginator(qs, 30).get_page(request.GET.get("page")), "status": status, "q": query,
        "statuses": PurchaseOrder.STATUS})


@login_required
@require_permission(CREATE)
def po_add(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        lines, errors = _parse_lines(request, company)
        supplier = _supplier(request, company)
        if supplier is None:
            errors.append(_("Choose a supplier or type a new supplier's name."))
        if not errors:
            try:
                with transaction.atomic():
                    po = purchases.create_purchase_order(
                        company=company, user=request.user, supplier=supplier, reference=(request.POST.get("reference") or "")[:50],
                        date=parse_date(request.POST.get("date") or "") or timezone.localdate(),
                        expected_date=parse_date(request.POST.get("expected_date") or "") or None,
                        lines=[{"product": l["product"], "quantity": l["quantity"], "unit_cost": l["unit_price"]} for l in lines])
                    purchases.confirm_purchase_order(company=company, purchase_order=po)
                messages.success(request, _("Purchase order %(number)s created.") % {"number": po.number})
                return redirect("webapp:po_detail", po.id)
            except ValidationError as exc:
                _err(request, exc)
        for error in errors:
            messages.error(request, error)
    rows = [{"product": "", "qty": "1", "price": ""}]
    if request.method == "POST":
        rows = [{"product": p, "qty": q, "price": pr} for p, q, pr in zip(
            request.POST.getlist("product"), request.POST.getlist("qty"), request.POST.getlist("price"))] or rows
    elif request.GET.get("reorder"):
        # prefill with items at or below their reorder level
        rows = []
        for product in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True):
            stock = product.current_stock()
            if stock <= product.reorder_level:
                need = max(Decimal(product.reorder_level) * 2 - Decimal(stock), Decimal("1"))
                rows.append({"product": str(product.id), "qty": f"{need.normalize():f}", "price": f"{product.cost_price:.2f}"})
        rows = rows[:60] or [{"product": "", "qty": "1", "price": ""}]
    return render(request, "webapp/sales_docs/editor.html", {
        "title": _("New purchase order"), "kind": "po", "rows": rows, "catalog_json": script_json(_cost_catalog(company)),
        "customers": Supplier.objects.for_company(company).filter(is_active=True).order_by("name")[:2000],
        "today": timezone.localdate(), "post": request.POST, "show_reference": True, "show_expected": True})


@login_required
@require_permission(VIEW)
def po_detail(request, po_id):
    company = request.company
    po = get_object_or_404(PurchaseOrder.objects.for_company(company).select_related("supplier"), id=po_id)
    lines = list(po.lines.select_related("product"))
    for line in lines:
        line.received = purchases.received_quantity(line)
        line.billed = purchases.billed_quantity(line)
        line.to_receive = max(line.quantity - line.received, ZERO)
        line.to_bill = max(line.received - line.billed, ZERO)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "confirm":
                    purchases.confirm_purchase_order(company=company, purchase_order=po)
                elif action == "cancel":
                    purchases.cancel_purchase_order(company=company, purchase_order=po)
                    messages.success(request, _("Purchase order cancelled."))
                elif action in ("receive", "receive_bill"):
                    picked = []
                    for line in lines:
                        try:
                            qty = Decimal(request.POST.get(f"r_{line.id}") or "0")
                        except InvalidOperation:
                            qty = ZERO
                        if qty > 0:
                            picked.append({"po_line": line, "quantity": qty})
                    if not picked:
                        raise ValidationError(_("Enter the quantity received."))
                    grn = purchases.create_goods_receipt(company=company, user=request.user, purchase_order=po,
                                                         warehouse=_warehouse(company, request.POST.get("warehouse")),
                                                         date=timezone.localdate(), lines=picked)
                    messages.success(request, _("Goods receipt %(number)s saved. Stock updated.") % {"number": grn.number})
                    if action == "receive_bill":
                        bill = purchases.create_bill_from_grn(company=company, user=request.user, purchase_order=po,
                                                              lines=picked, date=timezone.localdate(),
                                                              bill_number=(request.POST.get("bill_number") or "")[:30])
                        messages.success(request, _("Supplier bill saved (%(total)s).") % {"total": f"{bill.total:.2f}"})
                elif action == "bill":
                    picked = [{"po_line": line, "quantity": line.to_bill} for line in lines if line.to_bill > 0]
                    if not picked:
                        raise ValidationError(_("Nothing received is waiting for a bill."))
                    bill = purchases.create_bill_from_grn(company=company, user=request.user, purchase_order=po, lines=picked,
                                                          date=timezone.localdate(),
                                                          bill_number=(request.POST.get("bill_number") or "")[:30])
                    messages.success(request, _("Supplier bill saved (%(total)s).") % {"total": f"{bill.total:.2f}"})
                    return redirect("webapp:purchase_detail", bill.id)
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:po_detail", po.id)
    total = sum((l.line_total for l in lines), ZERO)
    return render(request, "webapp/purchase_docs/po_detail.html", {
        "doc": po, "lines": lines, "total": total,
        "receipts": po.receipts.select_related("warehouse").order_by("-date", "-id"),
        "bills": Purchase.objects.for_company(company).filter(purchase_order=po).order_by("-date"),
        "warehouses": Warehouse.objects.for_company(company).filter(is_active=True),
        "can_receive": po.status in ("confirmed", "partially_received") and any(l.to_receive > 0 for l in lines),
        "can_bill": any(l.to_bill > 0 for l in lines), "share": _po_share(company, po, lines, total)})


@login_required
@require_permission(VIEW)
def grn_detail(request, grn_id):
    company = request.company
    grn = get_object_or_404(GoodsReceiptNote.objects.for_company(company).select_related(
        "purchase_order__supplier", "warehouse", "received_by"), id=grn_id)
    return render(request, "webapp/purchase_docs/grn.html", {"grn": grn, "lines": grn.lines.select_related("po_line__product")})


# ------------------------------------------------------------------ bills & returns

@login_required
@require_permission(VIEW)
def purchase_detail(request, purchase_id):
    company = request.company
    bill = get_object_or_404(Purchase.objects.for_company(company).select_related("supplier", "purchase_order"), id=purchase_id)
    lines = list(bill.lines.select_related("product"))
    returned = {}
    for ret in bill.returns.prefetch_related("lines"):
        for rl in ret.lines.all():
            returned[rl.product_id] = returned.get(rl.product_id, ZERO) + rl.quantity
    purchased = {}
    for line in lines:
        purchased[line.product_id] = purchased.get(line.product_id, ZERO) + line.quantity
    for line in lines:
        line.can_return = max(purchased[line.product_id] - returned.get(line.product_id, ZERO), ZERO)
    if request.method == "POST" and request.POST.get("action") == "return":
        picked = []
        for line in lines:
            try:
                qty = Decimal(request.POST.get(f"q_{line.id}") or "0")
            except InvalidOperation:
                qty = ZERO
            if qty > 0:
                if qty > line.can_return:
                    messages.error(request, _("You can return at most %(qty)s of %(item)s.") % {
                        "qty": line.can_return.normalize(), "item": line.product.name})
                    return redirect("webapp:purchase_detail", bill.id)
                picked.append({"product": line.product, "quantity": qty, "unit_cost": line.unit_cost})
        method = request.POST.get("refund_method")
        if method not in dict(PurchaseReturn.REFUND_METHOD):
            method = "supplier_credit"
        if not picked:
            messages.error(request, _("Enter the quantity to return."))
        else:
            try:
                ret = purchases.process_purchase_return(
                    company=company, user=request.user, purchase=bill, date=timezone.localdate(), lines=picked,
                    warehouse=_warehouse(company, request.POST.get("warehouse")), refund_method=method,
                    reason=(request.POST.get("reason") or "")[:500])
                messages.success(request, _("Return %(number)s saved. Stock reduced.") % {"number": ret.number})
            except ValidationError as exc:
                _err(request, exc)
        return redirect("webapp:purchase_detail", bill.id)
    returns = list(bill.returns.prefetch_related("lines__product").order_by("-date"))
    return render(request, "webapp/purchase_docs/purchase_detail.html", {
        "bill": bill, "lines": lines, "returns": returns, "payments": bill.payments.order_by("-date"),
        "returned_total": sum((r.total for r in returns), ZERO), "due": bill.total - bill.amount_paid,
        "methods": PurchaseReturn.REFUND_METHOD, "warehouses": Warehouse.objects.for_company(company).filter(is_active=True),
        "any_returnable": any(l.can_return > 0 for l in lines)})

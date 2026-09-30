"""Quotations → sales orders → delivery notes → invoices, and a list of all sales invoices."""
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

from apps.inventory import branch_access
from apps.customers.models import Customer
from apps.inventory.models import Product, Warehouse
from apps.sales import services as sales
from apps.sales.models import DeliveryNote, Quotation, SalesInvoice, SalesOrder

from . import xlsx
from .views import require_permission

CREATE = "sales.create_invoice"
VIEW = "sales.view_invoice"
ZERO = Decimal("0")


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))


def _warehouse(company, warehouse_id=None):
    restricted = branch_access.pick(company, warehouse_id)
    if restricted is not None:
        return restricted
    qs = Warehouse.objects.for_company(company).filter(is_active=True)
    if warehouse_id:
        found = qs.filter(id=warehouse_id).first()
        if found:
            return found
    found = qs.filter(is_default=True).first() or qs.first()
    if found is None:
        found = Warehouse.objects.create(company=company, name="Main Branch", is_active=True, is_default=True)
    return found


def _catalog(company):
    return [{"id": p.id, "name": p.name, "sku": p.sku, "price": f"{p.selling_price:.2f}"}
            for p in Product.objects.for_company(company).filter(is_active=True).order_by("name")[:3000]]


def _parse_lines(request, company):
    """Reads product[] / qty[] / price[] from the editor. Returns (lines, errors)."""
    products = {str(p.id): p for p in Product.objects.for_company(company).filter(
        id__in=[v for v in request.POST.getlist("product") if v.isdigit()])}
    lines, errors = [], []
    for pid, qty, price in zip(request.POST.getlist("product"), request.POST.getlist("qty"), request.POST.getlist("price")):
        if not pid and not qty:
            continue
        try:
            q, p = Decimal(qty or "0"), Decimal(price or "0")
        except InvalidOperation:
            errors.append(_("Quantities and prices must be numbers."))
            continue
        if pid not in products:
            errors.append(_("Choose an item on every line."))
        elif q <= 0 or p < 0:
            errors.append(_("Quantity must be more than zero."))
        else:
            lines.append({"product": products[pid], "quantity": q.quantize(Decimal("0.001")), "unit_price": p.quantize(Decimal("0.01"))})
    if not lines and not errors:
        errors.append(_("Add at least one item."))
    return lines, list(dict.fromkeys(errors))


def _customer(request, company):
    customer_id = request.POST.get("customer")
    if customer_id:
        return Customer.objects.for_company(company).filter(id=customer_id).first()
    name = (request.POST.get("customer_name") or "").strip()
    if name:
        return Customer.objects.create(company=company, name=name[:255], phone=(request.POST.get("customer_phone") or "")[:20])
    return None


def _editor_context(request, company, title, kind, initial_lines=None, **extra):
    rows = initial_lines or [{"product": "", "qty": "1", "price": ""}]
    if request.method == "POST":
        rows = [{"product": p, "qty": q, "price": pr} for p, q, pr in zip(
            request.POST.getlist("product"), request.POST.getlist("qty"), request.POST.getlist("price"))] or rows
    return {"title": title, "kind": kind, "rows": rows, "catalog_json": json.dumps(_catalog(company)),
            "customers": Customer.objects.for_company(company).filter(is_active=True).order_by("name")[:2000],
            "today": timezone.localdate(), "post": request.POST, **extra}


def _share_text(company, title, number, customer, lines, total):
    rows = [f"{company.name}", f"{title} {number}", customer.name]
    for line in lines:
        rows.append(f"• {line.product.name} × {line.quantity.normalize():f} @ {line.unit_price} = {line.line_total:.2f}")
    rows.append(f"{_('Total')}: {company.default_currency} {total:.2f}")
    phone = "".join(ch for ch in (customer.phone or "") if ch.isdigit())
    return f"https://wa.me/{phone}?text={quote(chr(10).join(rows))}"


# ------------------------------------------------------------------ quotations

@login_required
@require_permission(VIEW)
def quotation_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    status = request.GET.get("status") or ""
    qs = Quotation.objects.for_company(company).select_related("customer").annotate(total=Sum("lines__line_total")).order_by("-date", "-id")
    if status:
        qs = qs.filter(status=status)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(number__icontains=query) | Q(customer__name__icontains=query))
    return render(request, "webapp/sales_docs/list.html", {
        "kind": "quotation", "page": Paginator(qs, 30).get_page(request.GET.get("page")), "status": status, "q": query,
        "statuses": Quotation.STATUS, "new_url": "webapp:quotation_add", "detail_url": "webapp:quotation_detail"})


@login_required
@require_permission(CREATE)
def quotation_add(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        lines, errors = _parse_lines(request, company)
        customer = _customer(request, company)
        if customer is None:
            errors.append(_("Choose a customer or type a new customer's name."))
        if not errors:
            try:
                quotation = sales.create_quotation(
                    company=company, user=request.user, customer=customer, lines=lines,
                    date=parse_date(request.POST.get("date") or "") or timezone.localdate(),
                    valid_until=parse_date(request.POST.get("valid_until") or "") or None,
                    notes=(request.POST.get("notes") or "")[:2000])
                messages.success(request, _("Quotation %(number)s created.") % {"number": quotation.number})
                return redirect("webapp:quotation_detail", quotation.id)
            except ValidationError as exc:
                _err(request, exc)
        for error in errors:
            messages.error(request, error)
    return render(request, "webapp/sales_docs/editor.html", _editor_context(
        request, company, _("New quotation"), "quotation", show_valid_until=True))


@login_required
@require_permission(VIEW)
def quotation_detail(request, quotation_id):
    company = request.company
    quotation = get_object_or_404(Quotation.objects.for_company(company).select_related("customer", "created_by"), id=quotation_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "send":
                    sales.send_quotation(company=company, quotation=quotation)
                elif action == "accept":
                    sales.accept_quotation(company=company, quotation=quotation)
                elif action == "reject":
                    sales.reject_quotation(company=company, quotation=quotation)
                elif action == "to_order":
                    if quotation.status != "accepted":
                        sales.accept_quotation(company=company, quotation=quotation)
                    order = sales.create_sales_order(company=company, user=request.user, customer=quotation.customer,
                                                     date=timezone.localdate(), quotation=quotation)
                    messages.success(request, _("Sales order %(number)s created.") % {"number": order.number})
                    return redirect("webapp:sales_order_detail", order.id)
                elif action == "to_invoice":
                    if quotation.status != "accepted":
                        sales.accept_quotation(company=company, quotation=quotation)
                    invoice = sales.create_invoice(
                        company=company, user=request.user, customer=quotation.customer, date=timezone.localdate(),
                        warehouse=_warehouse(company),
                        lines=[{"product": l.product, "quantity": l.quantity, "unit_price": l.unit_price} for l in quotation.lines.all()])
                    messages.success(request, _("Invoice %(number)s created from the quotation.") % {"number": invoice.invoice_number})
                    return redirect("webapp:sales_invoice_list")
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:quotation_detail", quotation.id)
    lines = list(quotation.lines.select_related("product"))
    total = sum((l.line_total for l in lines), ZERO)
    orders = SalesOrder.objects.for_company(company).filter(quotation=quotation)
    return render(request, "webapp/sales_docs/quotation_detail.html", {
        "doc": quotation, "lines": lines, "total": total, "orders": orders, "today": timezone.localdate(),
        "share": _share_text(company, _("Quotation"), quotation.number, quotation.customer, lines, total)})


# ------------------------------------------------------------------ sales orders

@login_required
@require_permission(VIEW)
def sales_order_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    status = request.GET.get("status") or ""
    qs = SalesOrder.objects.for_company(company).select_related("customer").annotate(total=Sum("lines__line_total")).order_by("-date", "-id")
    if status:
        qs = qs.filter(status=status)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(number__icontains=query) | Q(customer__name__icontains=query) | Q(reference__icontains=query))
    return render(request, "webapp/sales_docs/list.html", {
        "kind": "order", "page": Paginator(qs, 30).get_page(request.GET.get("page")), "status": status, "q": query,
        "statuses": SalesOrder.STATUS, "new_url": "webapp:sales_order_add", "detail_url": "webapp:sales_order_detail"})


@login_required
@require_permission(CREATE)
def sales_order_add(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        lines, errors = _parse_lines(request, company)
        customer = _customer(request, company)
        if customer is None:
            errors.append(_("Choose a customer or type a new customer's name."))
        if not errors:
            try:
                with transaction.atomic():
                    order = sales.create_sales_order(
                        company=company, user=request.user, customer=customer, lines=lines,
                        date=parse_date(request.POST.get("date") or "") or timezone.localdate(),
                        reference=(request.POST.get("reference") or "")[:50])
                    sales.confirm_sales_order(company=company, sales_order=order)
                messages.success(request, _("Sales order %(number)s created.") % {"number": order.number})
                return redirect("webapp:sales_order_detail", order.id)
            except ValidationError as exc:
                _err(request, exc)
        for error in errors:
            messages.error(request, error)
    return render(request, "webapp/sales_docs/editor.html", _editor_context(
        request, company, _("New sales order"), "order", show_reference=True))


@login_required
@require_permission(VIEW)
def sales_order_detail(request, order_id):
    company = request.company
    order = get_object_or_404(SalesOrder.objects.for_company(company).select_related("customer", "quotation"), id=order_id)
    lines = list(order.lines.select_related("product"))
    for line in lines:
        line.delivered = sales.delivered_quantity(line)
        line.invoiced = sales.invoiced_quantity(line)
        line.to_deliver = max(line.quantity - line.delivered, ZERO)
        line.to_invoice = max(line.delivered - line.invoiced, ZERO)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "confirm":
                    sales.confirm_sales_order(company=company, sales_order=order)
                elif action == "cancel":
                    sales.cancel_sales_order(company=company, sales_order=order)
                    messages.success(request, _("Order cancelled."))
                elif action in ("deliver", "deliver_invoice"):
                    picked = []
                    for line in lines:
                        try:
                            qty = Decimal(request.POST.get(f"d_{line.id}") or "0")
                        except InvalidOperation:
                            qty = ZERO
                        if qty > 0:
                            picked.append({"so_line": line, "quantity": qty})
                    if not picked:
                        raise ValidationError(_("Enter the quantity to deliver."))
                    note = sales.create_delivery(company=company, user=request.user, sales_order=order, date=timezone.localdate(),
                                                 warehouse=_warehouse(company, request.POST.get("warehouse")), lines=picked)
                    messages.success(request, _("Delivery note %(number)s saved. Stock updated.") % {"number": note.number})
                    if action == "deliver_invoice":
                        invoice = sales.create_invoice_from_order(company=company, user=request.user, sales_order=order,
                                                                  date=timezone.localdate(), lines=picked, warehouse=note.warehouse)
                        messages.success(request, _("Invoice %(number)s created.") % {"number": invoice.invoice_number})
                elif action == "invoice":
                    picked = [{"so_line": line, "quantity": line.to_invoice} for line in lines if line.to_invoice > 0]
                    if not picked:
                        raise ValidationError(_("Nothing delivered is waiting to be invoiced."))
                    invoice = sales.create_invoice_from_order(company=company, user=request.user, sales_order=order,
                                                              date=timezone.localdate(), lines=picked,
                                                              warehouse=_warehouse(company))
                    messages.success(request, _("Invoice %(number)s created.") % {"number": invoice.invoice_number})
        except ValidationError as exc:
            _err(request, exc)
        return redirect("webapp:sales_order_detail", order.id)
    total = sum((l.line_total for l in lines), ZERO)
    return render(request, "webapp/sales_docs/order_detail.html", {
        "doc": order, "lines": lines, "total": total,
        "deliveries": order.deliveries.select_related("warehouse").order_by("-date", "-id"),
        "invoices": SalesInvoice.objects.for_company(company).filter(sales_order=order).order_by("-date"),
        "warehouses": Warehouse.objects.for_company(company).filter(is_active=True),
        "can_deliver": order.status in ("confirmed", "partially_delivered") and any(l.to_deliver > 0 for l in lines),
        "can_invoice": any(l.to_invoice > 0 for l in lines),
        "share": _share_text(company, _("Sales order"), order.number, order.customer, lines, total)})


@login_required
@require_permission(VIEW)
def delivery_note(request, delivery_id):
    company = request.company
    note = get_object_or_404(DeliveryNote.objects.for_company(company).select_related(
        "sales_order__customer", "warehouse", "delivered_by"), id=delivery_id)
    return render(request, "webapp/sales_docs/delivery_note.html", {
        "note": note, "lines": note.lines.select_related("so_line__product")})


# ------------------------------------------------------------------ invoices

@login_required
@require_permission(VIEW)
def sales_invoice_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    qs = SalesInvoice.objects.for_company(company).select_related("customer").order_by("-date", "-id")
    if branch_access.allowed() is not None:
        qs = qs.filter(Q(warehouse_id__in=branch_access.allowed()) | Q(warehouse__isnull=True))
    status = request.GET.get("status") or ""
    if status == "unpaid":
        qs = qs.filter(status__in=["unpaid", "partial"])
    elif status:
        qs = qs.filter(status=status)
    start, end = parse_date(request.GET.get("from") or ""), parse_date(request.GET.get("to") or "")
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(invoice_number__icontains=query) | Q(customer__name__icontains=query) | Q(customer__phone__icontains=query))
    totals = qs.exclude(status="void").aggregate(total=Sum("total"), paid=Sum("amount_paid"))
    if xlsx.wants(request):
        data = [[_("Invoice"), _("Date"), _("Due date"), _("Customer"), _("Phone"), _("Status"), _("Currency"),
                 _("Total"), _("Paid"), _("Balance")]]
        data += [[i.invoice_number, i.date, i.due_date, i.customer.name, i.customer.phone, i.get_status_display(),
                  i.currency, i.total, i.amount_paid, i.total - i.amount_paid] for i in qs[:20000]]
        return xlsx.response(f"invoices-{timezone.localdate()}", [(_("Invoices"), data)])
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "webapp/sales_docs/invoice_list.html", {
        "page": Paginator(qs, 40).get_page(request.GET.get("page")), "status": status, "q": query, "start": start,
        "end": end, "total": totals["total"] or ZERO, "due": (totals["total"] or ZERO) - (totals["paid"] or ZERO),
        "page_query": params.urlencode(), "statuses": SalesInvoice.STATUS})

"""Sports shop: size charts (staff and website) and equipment rental (out with a deposit, back with the bill)."""
import datetime
import math
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.inventory.models import ProductCategory
from apps.verticals.sports_shop.models import Rental, RentalItem, RentalLine, SizeChart

SPORTS = ("sports_shop", "fitness_sports_store", "cycle_shop")


def _company(request):
    company = request.company
    if company is None or company.business_type.code not in SPORTS:
        raise Http404
    return company


def _money(value, default="0"):
    try:
        return max(Decimal("0"), Decimal(str(value or default).strip() or default))
    except InvalidOperation:
        return Decimal("0")


# ------------------------------------------------------------------ size charts

@login_required
def size_charts(request):
    company = _company(request)
    if request.method == "POST":
        chart = None
        if request.POST.get("chart_id"):
            chart = get_object_or_404(SizeChart.objects.for_company(company), id=request.POST["chart_id"])
        if request.POST.get("do") == "delete" and chart:
            chart.delete()
            messages.success(request, _("Size chart deleted."))
            return redirect("webapp:size_charts")
        name, table = (request.POST.get("name") or "").strip()[:120], (request.POST.get("table") or "").strip()[:5000]
        if not name or not table:
            messages.error(request, _("Enter a name and the table."))
            return redirect("webapp:size_charts")
        chart = chart or SizeChart(company=company)
        chart.name, chart.table = name, table
        chart.note = (request.POST.get("note") or "").strip()[:255]
        chart.category = ProductCategory.objects.filter(company=company, id=request.POST.get("category") or 0).first()
        chart.save()
        messages.success(request, _("Size chart saved."))
        return redirect("webapp:size_charts")
    return render(request, "webapp/sports_shop/size_charts.html", {
        "charts": SizeChart.objects.for_company(company).select_related("category"),
        "categories": ProductCategory.objects.filter(company=company).order_by("name"),
        "example": "Size, Chest (cm), Length (cm)\nS, 88–92, 68\nM, 96–100, 71\nL, 104–108, 74\nXL, 112–116, 77"})


def chart_for(product):
    """The size chart for a product (by its category), or None."""
    if not product.category_id:
        return None
    return SizeChart.objects.filter(company_id=product.company_id, category_id=product.category_id).first()


# ------------------------------------------------------------------ rental

def _out_counts(company):
    rows = (RentalLine.objects.for_company(company).filter(rental__status="out")
            .values("item_id").annotate(q=Sum("quantity")))
    return {r["item_id"]: r["q"] for r in rows}


@login_required
def rental_list(request):
    company = _company(request)
    today = timezone.localdate()
    if request.method == "POST":  # add or update a rental item
        item = None
        if request.POST.get("item_id"):
            item = get_object_or_404(RentalItem.objects.for_company(company), id=request.POST["item_id"])
        name = (request.POST.get("name") or "").strip()[:120]
        if not name:
            messages.error(request, _("Enter the item name."))
        else:
            item = item or RentalItem(company=company)
            item.name, item.rate_per_day = name, _money(request.POST.get("rate_per_day"))
            item.deposit = _money(request.POST.get("deposit"))
            try:
                item.quantity_owned = max(0, int(request.POST.get("quantity_owned") or 1))
            except ValueError:
                item.quantity_owned = 1
            item.is_active = request.POST.get("is_active", "on") == "on"
            item.save()
            messages.success(request, _("Rental item saved."))
        return redirect("webapp:sports_rentals")
    show = request.GET.get("show", "out")
    rentals = Rental.objects.for_company(company).select_related("customer").prefetch_related("lines__item")
    rentals = rentals.filter(status="out") if show == "out" else rentals
    out = _out_counts(company)
    items = list(RentalItem.objects.for_company(company))
    for i in items:
        i.out = out.get(i.id, 0)
        i.free = max(0, i.quantity_owned - i.out)
    rentals = list(rentals[:200])
    for r in rentals:
        r.late = r.status == "out" and r.due_back < today
    return render(request, "webapp/sports_shop/rentals.html", {
        "rentals": rentals, "items": items, "show": show, "today": today,
        "overdue": sum(1 for r in rentals if r.late)})


@login_required
def rental_add(request):
    company = _company(request)
    items = list(RentalItem.objects.for_company(company).filter(is_active=True))
    out = _out_counts(company)
    for i in items:
        i.free = max(0, i.quantity_owned - out.get(i.id, 0))
    if request.method == "POST":
        post = request.POST
        customer = Customer.objects.for_company(company).filter(id=post.get("customer") or 0).first()
        name, phone = (post.get("new_name") or "").strip()[:255], (post.get("new_phone") or "").strip()[:20]
        if customer is None and name:
            customer = (Customer.objects.for_company(company).filter(phone=phone).first() if phone else None) or \
                Customer.objects.create(company=company, name=name, phone=phone)
        wanted = []
        for i in items:
            try:
                q = int(post.get(f"qty_{i.id}") or 0)
            except ValueError:
                q = 0
            if q > 0:
                wanted.append((i, q))
        due = parse_date(post.get("due_back") or "") or timezone.localdate() + datetime.timedelta(days=1)
        problem = None
        if customer is None:
            problem = _("Choose the customer or enter a new name.")
        elif not wanted:
            problem = _("Choose at least one item.")
        elif due < timezone.localdate():
            problem = _("The return date can't be in the past.")
        else:
            short = [i.name for i, q in wanted if q > i.free]
            if short:
                problem = _("Not enough free: %(items)s") % {"items": ", ".join(short)}
        if problem:
            messages.error(request, problem)
        else:
            from apps.tenants.services import next_counter_value
            with transaction.atomic():
                deposit = post.get("deposit")
                rental = Rental.objects.create(
                    company=company, number=f"RNT-{next_counter_value(company, 'sports_rental'):05d}", customer=customer,
                    id_document=(post.get("id_document") or "").strip()[:60], out_at=timezone.now(), due_back=due,
                    deposit=_money(deposit) if deposit not in (None, "") else sum((i.deposit * q for i, q in wanted), Decimal("0")),
                    notes=(post.get("notes") or "").strip()[:2000])
                for i, q in wanted:
                    RentalLine.objects.create(company=company, rental=rental, item=i, quantity=q, rate_per_day=i.rate_per_day)
            messages.success(request, _("Rental %(n)s saved.") % {"n": rental.number})
            return redirect("webapp:sports_rental_detail", rental_id=rental.id)
    return render(request, "webapp/sports_shop/rental_form.html", {
        "items": items, "customers": Customer.objects.for_company(company).order_by("name")[:500],
        "tomorrow": timezone.localdate() + datetime.timedelta(days=1)})


def days_for(rental, when=None):
    """Whole days charged: at least one, a started day counts."""
    when = when or timezone.now()
    return max(1, math.ceil((when - rental.out_at).total_seconds() / 86400 - 0.04))  # an hour's grace


@login_required
def rental_detail(request, rental_id):
    company = _company(request)
    rental = get_object_or_404(Rental.objects.for_company(company).select_related("customer", "invoice"), id=rental_id)
    lines = list(rental.lines.select_related("item"))
    days = rental.days_charged if rental.status == "returned" else days_for(rental)
    per_day = sum((l.rate_per_day * l.quantity for l in lines), Decimal("0"))
    from urllib.parse import quote
    from apps.sales.sharing import normalise_phone
    phone = normalise_phone(rental.customer.phone or "", company.country)
    text = _("Hi %(name)s, a reminder from %(shop)s: rental %(n)s is due back on %(date)s. Thank you!") % {
        "name": rental.customer.name, "shop": company.name, "n": rental.number, "date": rental.due_back.strftime("%d %b")}
    return render(request, "webapp/sports_shop/rental_detail.html", {
        "r": rental, "lines": lines, "days": days, "per_day": per_day, "estimate": per_day * days,
        "late": rental.status == "out" and rental.due_back < timezone.localdate(),
        "whatsapp": f"https://wa.me/{phone}?text={quote(text)}" if phone else "", "company": company})


@login_required
@require_POST
def rental_return(request, rental_id):
    from apps.industry.common import default_warehouse, service_product
    from apps.sales.services import create_invoice, record_customer_payment
    company = _company(request)
    with transaction.atomic():
        rental = get_object_or_404(Rental.objects.for_company(company).select_for_update(), id=rental_id)
        if request.POST.get("do") == "cancel" and rental.status == "out":
            rental.status = "cancelled"
            rental.save(update_fields=["status"])
            messages.success(request, _("Rental cancelled."))
            return redirect("webapp:sports_rental_detail", rental_id=rental.id)
        if rental.status != "out":
            messages.error(request, _("This rental is already closed."))
            return redirect("webapp:sports_rental_detail", rental_id=rental.id)
        now = timezone.now()
        days = days_for(rental, now)
        damage = _money(request.POST.get("damage_charge"))
        lines = []
        for l in rental.lines.select_related("item"):
            lines.append({"product": service_product(company, "RENTAL", "Equipment rental"),
                          "quantity": Decimal(l.quantity * days), "unit_price": l.rate_per_day})
        if damage:
            lines.append({"product": service_product(company, "RENTAL-DAMAGE", "Rental damage / missing parts"),
                          "quantity": Decimal("1"), "unit_price": damage})
        invoice = create_invoice(company=company, user=request.user, customer=rental.customer, date=timezone.localdate(),
                                 warehouse=default_warehouse(company), lines=lines)
        from_deposit = min(rental.deposit, invoice.total)
        if from_deposit > 0:
            record_customer_payment(company=company, user=request.user, customer=rental.customer, invoice=invoice,
                                    amount=from_deposit, date=timezone.localdate(), method="cash")
        rental.status, rental.returned_at, rental.days_charged = "returned", now, days
        rental.damage_charge, rental.charge, rental.invoice = damage, invoice.total, invoice
        note = (request.POST.get("return_note") or "").strip()
        if note:
            rental.notes = (rental.notes + "\n" if rental.notes else "") + _("Returned: %(note)s") % {"note": note}
        rental.save()
    refund = rental.deposit - from_deposit
    if refund > 0:
        messages.success(request, _("Returned. Bill %(inv)s paid from the deposit — give back %(cur)s %(amt)s.") % {
            "inv": invoice.invoice_number, "cur": company.default_currency, "amt": f"{refund:.2f}"})
    else:
        messages.success(request, _("Returned. Bill %(inv)s — collect %(cur)s %(amt)s.") % {
            "inv": invoice.invoice_number, "cur": company.default_currency, "amt": f"{invoice.total - from_deposit:.2f}"})
    return redirect("webapp:sports_rental_detail", rental_id=rental.id)

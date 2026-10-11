"""Refill subscriptions: customers who buy the same item every few weeks (protein, vitamins, monthly medicine)."""
import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.industry import expiry_deals
from apps.industry.models import RefillSubscription
from apps.inventory.models import Product
from apps.sales.sharing import normalise_phone


def _company(request):
    if request.company is None:
        raise Http404
    return request.company


def _wa(sub):
    phone = normalise_phone(sub.customer.phone or "", sub.company.country)
    return f"https://wa.me/{phone}?text={quote(expiry_deals.whatsapp_text(sub))}" if phone else ""


@login_required
def refill_list(request):
    company = _company(request)
    today = timezone.localdate()
    show = request.GET.get("show", "due")
    qs = RefillSubscription.objects.for_company(company).select_related("customer", "product", "last_invoice")
    if show == "due":
        qs = qs.filter(is_active=True, next_date__lte=today + datetime.timedelta(days=3))
    elif show == "active":
        qs = qs.filter(is_active=True)
    subs = list(qs[:300])
    for s in subs:
        s.days = (s.next_date - today).days
        s.whatsapp = _wa(s)
    return render(request, "webapp/refills/list.html", {
        "subs": subs, "show": show, "today": today,
        "due_count": RefillSubscription.objects.for_company(company).filter(is_active=True, next_date__lte=today).count(),
        "customers": Customer.objects.for_company(company).order_by("name")[:500],
        "products": Product.objects.for_company(company).filter(is_active=True, variants__isnull=True).distinct().order_by("name")[:500],
    })


@login_required
@require_POST
def refill_add(request):
    company = _company(request)
    post = request.POST
    customer = Customer.objects.for_company(company).filter(id=post.get("customer") or 0).first()
    name, phone = (post.get("new_name") or "").strip()[:255], (post.get("new_phone") or "").strip()[:20]
    if customer is None and name:
        customer = Customer.objects.for_company(company).filter(phone=phone).first() if phone else None
        customer = customer or Customer.objects.create(company=company, name=name, phone=phone)
    product = Product.objects.for_company(company).filter(id=post.get("product") or 0).first()
    try:
        qty = max(1, int(post.get("quantity") or 1))
        every = max(1, min(365, int(post.get("every_days") or 30)))
        discount = max(Decimal("0"), min(Decimal("90"), Decimal(post.get("discount_percent") or "0")))
    except (ValueError, InvalidOperation):
        qty = every = 0
        discount = Decimal("0")
    if customer is None or product is None or not qty:
        messages.error(request, _("Choose the customer and the item, and enter how often."))
        return redirect("webapp:refill_list")
    first = parse_date(post.get("next_date") or "") or timezone.localdate() + datetime.timedelta(days=every)
    RefillSubscription.objects.create(company=company, customer=customer, product=product, quantity=qty, every_days=every,
                                      next_date=first, discount_percent=discount, delivery=bool(post.get("delivery")),
                                      note=(post.get("note") or "").strip()[:255])
    messages.success(request, _("Refill added for %(name)s.") % {"name": customer.name})
    return redirect("webapp:refill_list")


@login_required
@require_POST
def refill_action(request, sub_id):
    company = _company(request)
    sub = get_object_or_404(RefillSubscription.objects.for_company(company), id=sub_id)
    what = request.POST.get("do")
    try:
        if what == "bill":
            sub = expiry_deals.bill_refill(sub, request.user)
            messages.success(request, _("Bill %(inv)s made. Next refill on %(date)s.") % {
                "inv": sub.last_invoice.invoice_number, "date": sub.next_date.strftime("%d %b")})
        elif what == "skip":
            sub = expiry_deals.skip(sub)
            messages.success(request, _("Skipped. Next refill on %(date)s.") % {"date": sub.next_date.strftime("%d %b")})
        elif what in ("pause", "resume"):
            sub.is_active = what == "resume"
            sub.save(update_fields=["is_active"])
        elif what == "delete":
            sub.delete()
            messages.success(request, _("Refill removed."))
        else:
            raise Http404
    except (ValidationError, ValueError) as exc:
        messages.error(request, " ".join(getattr(exc, "messages", [str(exc)])))
    return redirect(request.POST.get("next") or "webapp:refill_list")

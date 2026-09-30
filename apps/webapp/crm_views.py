"""CRM (leads, sales pipeline, follow-ups) and pricing (price lists, offers)."""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.crm import services as crm
from apps.crm.models import Activity, Lead, Opportunity, PipelineStage
from apps.customers.models import Customer
from apps.inventory.models import Product
from apps.sales.models import PriceList, PriceListItem, Promotion
from apps.sales.services import resolve_commercial_price

from .views import require_permission

CRM = "customers.manage"
PRICING = "sales.create_invoice"
DEFAULT_STAGES = [("New", 10, 10, False, False), ("Contacted", 20, 25, False, False), ("Proposal sent", 30, 50, False, False),
                  ("Negotiation", 40, 75, False, False), ("Won", 90, 100, True, True), ("Lost", 99, 0, True, False)]


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)]) if not hasattr(exc, "message_dict") else
                                      [str(v) for v in exc.message_dict.values()]))


def _stages(company):
    if not PipelineStage.objects.for_company(company).exists():
        for name, order, prob, closed, won in DEFAULT_STAGES:
            PipelineStage.objects.get_or_create(company=company, name=name,
                                                defaults={"order": order, "probability": prob, "is_closed": closed, "is_won": won})
    return list(PipelineStage.objects.for_company(company).order_by("order", "id"))


def _users(company):
    from apps.accounts.models import User
    return User.objects.filter(memberships__company=company, memberships__is_active=True).distinct()


def _due(value):
    day = parse_date(value or "")
    return timezone.make_aware(datetime.combine(day, time(10, 0))) if day else None


# ------------------------------------------------------------------ pipeline

@login_required
@require_permission(CRM)
def pipeline(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    stages = _stages(company)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "add":
                    title = (request.POST.get("title") or "").strip()
                    if not title:
                        raise ValidationError(_("Enter what the deal is about."))
                    customer = Customer.objects.for_company(company).filter(id=request.POST.get("customer")).first()
                    Opportunity.objects.create(
                        company=company, title=title[:255], customer=customer, stage=stages[0],
                        expected_value=Decimal(request.POST.get("value") or "0"),
                        expected_close_date=parse_date(request.POST.get("close") or "") or None,
                        assigned_to=request.user, notes=(request.POST.get("notes") or "")[:2000])
                    messages.success(request, _("Deal added."))
                elif action == "move":
                    deal = Opportunity.objects.for_company(company).get(id=request.POST.get("id"))
                    deal.stage = PipelineStage.objects.for_company(company).get(id=request.POST.get("stage"))
                    deal.save(update_fields=["stage", "updated_at"])
                elif action == "done":
                    activity = Activity.objects.for_company(company).get(id=request.POST.get("id"))
                    activity.completed_at = timezone.now()
                    activity.save(update_fields=["completed_at"])
        except (ValidationError, InvalidOperation, Opportunity.DoesNotExist, PipelineStage.DoesNotExist, Activity.DoesNotExist) as exc:
            _err(request, exc)
        return redirect("webapp:crm_pipeline")
    deals = Opportunity.objects.for_company(company).select_related("customer", "lead", "stage", "assigned_to").order_by("expected_close_date", "-id")
    mine = request.GET.get("mine") == "1"
    if mine:
        deals = deals.filter(assigned_to=request.user)
    columns = []
    for stage in stages:
        items = [d for d in deals if d.stage_id == stage.id]
        columns.append({"stage": stage, "deals": items, "total": sum((d.expected_value for d in items), Decimal("0"))})
    open_value = sum((c["total"] for c in columns if not c["stage"].is_closed), Decimal("0"))
    weighted = sum((c["total"] * c["stage"].probability / 100 for c in columns if not c["stage"].is_closed), Decimal("0"))
    todo = (Activity.objects.for_company(company).filter(completed_at__isnull=True)
            .filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
            .select_related("lead", "opportunity").order_by("due_at")[:15])
    return render(request, "webapp/crm/pipeline.html", {
        "columns": columns, "stages": stages, "open_value": open_value, "weighted": weighted, "mine": mine,
        "todo": todo, "now": timezone.now(),
        "customers": Customer.objects.for_company(company).filter(is_active=True).order_by("name")[:2000],
        "won": sum((c["total"] for c in columns if c["stage"].is_won), Decimal("0")),
        "new_leads": Lead.objects.for_company(company).filter(status="open").count()})


# ------------------------------------------------------------------ leads

@login_required
@require_permission(CRM)
def lead_list(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, _("Enter the person's name."))
        else:
            lead = Lead.objects.create(
                company=company, name=name[:255], company_name=(request.POST.get("company_name") or "")[:255],
                phone=(request.POST.get("phone") or "")[:30], email=(request.POST.get("email") or "")[:254],
                source=(request.POST.get("source") or "")[:100], created_by=request.user,
                assigned_to=_users(company).filter(id=request.POST.get("assigned_to")).first() or request.user)
            note = (request.POST.get("note") or "").strip()
            if note:
                Activity.objects.create(company=company, lead=lead, activity_type="note", subject=note[:255],
                                        created_by=request.user, completed_at=timezone.now())
            messages.success(request, _("Lead %(name)s added.") % {"name": lead.name})
            return redirect("webapp:lead_detail", lead.id)
    status = request.GET.get("status", "open")
    leads = Lead.objects.for_company(company).select_related("assigned_to").annotate(
        todo=Count("activities", filter=Q(activities__completed_at__isnull=True))).order_by("-created_at")
    if status:
        leads = leads.filter(status=status)
    query = (request.GET.get("q") or "").strip()
    if query:
        leads = leads.filter(Q(name__icontains=query) | Q(company_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    return render(request, "webapp/crm/leads.html", {
        "leads": leads[:300], "status": status, "q": query, "statuses": Lead.STATUS, "users": _users(company),
        "sources": ["Walk-in", "Phone call", "WhatsApp", "Instagram", "Facebook", "Google", "Referral", "Website", "Exhibition"]})


@login_required
@require_permission(CRM)
def lead_detail(request, lead_id):
    company = request.company
    lead = get_object_or_404(Lead.objects.for_company(company).select_related("assigned_to", "converted_customer"), id=lead_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "activity":
                    subject = (request.POST.get("subject") or "").strip()
                    if not subject:
                        raise ValidationError(_("Enter what happened or what to do."))
                    kind = request.POST.get("type") if request.POST.get("type") in dict(Activity.TYPE) else "note"
                    due = _due(request.POST.get("due"))
                    Activity.objects.create(company=company, lead=lead, activity_type=kind, subject=subject[:255],
                                            notes=(request.POST.get("notes") or "")[:2000], due_at=due, assigned_to=lead.assigned_to,
                                            created_by=request.user, completed_at=None if due else timezone.now())
                    if lead.status == "open" and kind in ("call", "meeting", "email"):
                        lead.status = "qualified"
                        lead.save(update_fields=["status", "updated_at"])
                elif action == "done":
                    Activity.objects.for_company(company).filter(id=request.POST.get("id"), lead=lead).update(completed_at=timezone.now())
                elif action == "lost":
                    lead.status = "lost"
                    lead.save(update_fields=["status", "updated_at"])
                elif action == "reopen":
                    lead.status = "open"
                    lead.save(update_fields=["status", "updated_at"])
                elif action == "convert":
                    existing = Customer.objects.for_company(company).filter(id=request.POST.get("customer")).first()
                    customer, deal, quotation = crm.convert_lead(
                        company=company, lead=lead, user=request.user, existing_customer=existing,
                        resolve_duplicate=bool(request.POST.get("use_match")), create_quotation=False)
                    messages.success(request, _("%(name)s is now a customer. A deal was added to the pipeline.") % {"name": customer.name})
                    if request.POST.get("quote"):
                        return redirect("webapp:quotation_add")
                    return redirect("webapp:crm_pipeline")
        except ValidationError as exc:
            if hasattr(exc, "message_dict") and "duplicate_candidates" in exc.message_dict:
                messages.error(request, _("A customer with the same name, phone or email already exists. Pick them below or confirm to use the match."))
            else:
                _err(request, exc)
        return redirect("webapp:lead_detail", lead.id)
    return render(request, "webapp/crm/lead_detail.html", {
        "lead": lead, "activities": lead.activities.select_related("created_by").order_by("completed_at", "-due_at", "-created_at"),
        "matches": crm.duplicate_customer_candidates(company=company, lead=lead)[:5] if lead.status != "converted" else [],
        "types": Activity.TYPE, "deals": lead.opportunities.select_related("stage")})


# ------------------------------------------------------------------ price lists & offers

@login_required
@require_permission(PRICING)
def pricing(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "list":
                    name = (request.POST.get("name") or "").strip()
                    if not name:
                        raise ValidationError(_("Enter a name for the price list."))
                    plist = PriceList.objects.create(
                        company=company, name=name[:120], priority=int(request.POST.get("priority") or 0),
                        customer=Customer.objects.for_company(company).filter(id=request.POST.get("customer")).first(),
                        start_date=parse_date(request.POST.get("start") or "") or None,
                        end_date=parse_date(request.POST.get("end") or "") or None)
                    return redirect("webapp:price_list_detail", plist.id)
                elif action == "offer":
                    name = (request.POST.get("name") or "").strip()
                    start, end = parse_date(request.POST.get("start") or ""), parse_date(request.POST.get("end") or "")
                    value = Decimal(request.POST.get("value") or "0")
                    kind = "fixed" if request.POST.get("kind") == "fixed" else "percentage"
                    if not name or not start or not end or end < start or value <= 0 or (kind == "percentage" and value > 100):
                        raise ValidationError(_("Enter a name, valid dates and a discount."))
                    Promotion.objects.create(company=company, name=name[:120], discount_type=kind, discount_value=value,
                                             product=Product.objects.for_company(company).filter(id=request.POST.get("product")).first(),
                                             start_date=start, end_date=end, priority=int(request.POST.get("priority") or 0))
                    messages.success(request, _("Offer saved. The POS and new quotes use it automatically."))
                elif action in ("toggle_offer", "toggle_list"):
                    model = Promotion if action == "toggle_offer" else PriceList
                    obj = model.objects.for_company(company).get(id=request.POST.get("id"))
                    obj.is_active = not obj.is_active
                    obj.save(update_fields=["is_active"])
        except (ValidationError, InvalidOperation, ValueError, Promotion.DoesNotExist, PriceList.DoesNotExist) as exc:
            _err(request, exc)
        return redirect("webapp:pricing")
    today = timezone.localdate()
    offers = list(Promotion.objects.for_company(company).select_related("product").order_by("-is_active", "-end_date"))
    for offer in offers:
        offer.live = offer.is_active and offer.start_date <= today <= offer.end_date
    return render(request, "webapp/crm/pricing.html", {
        "lists": PriceList.objects.for_company(company).select_related("customer").annotate(n=Count("items")).order_by("-is_active", "-priority", "name"),
        "offers": offers, "today": today,
        "customers": Customer.objects.for_company(company).filter(is_active=True).order_by("name")[:2000],
        "products": Product.objects.for_company(company).filter(is_active=True).order_by("name")[:3000]})


@login_required
@require_permission(PRICING)
def price_list_detail(request, list_id):
    company = request.company
    plist = get_object_or_404(PriceList.objects.for_company(company).select_related("customer"), id=list_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "item":
                product = Product.objects.for_company(company).get(id=request.POST.get("product"))
                price = Decimal(request.POST.get("price") or "")
                if price < 0:
                    raise ValidationError(_("The price can't be negative."))
                PriceListItem.objects.update_or_create(price_list=plist, product=product, defaults={"unit_price": price})
                messages.success(request, _("%(item)s: %(price)s") % {"item": product.name, "price": f"{price:.2f}"})
            elif action == "remove":
                PriceListItem.objects.filter(price_list=plist, id=request.POST.get("id")).delete()
            elif action == "bulk":
                percent = Decimal(request.POST.get("percent") or "0")
                created = 0
                for product in Product.objects.for_company(company).filter(is_active=True):
                    price = (product.selling_price * (Decimal("100") + percent) / Decimal("100")).quantize(Decimal("0.01"))
                    PriceListItem.objects.update_or_create(price_list=plist, product=product, defaults={"unit_price": max(price, Decimal("0"))})
                    created += 1
                messages.success(request, _("%(count)s prices set.") % {"count": created})
        except (ValidationError, InvalidOperation, Product.DoesNotExist, IntegrityError) as exc:
            _err(request, exc)
        return redirect("webapp:price_list_detail", plist.id)
    items = plist.items.select_related("product").order_by("product__name")
    return render(request, "webapp/crm/price_list.html", {
        "plist": plist, "items": items,
        "products": Product.objects.for_company(company).filter(is_active=True).order_by("name")[:3000]})


@login_required
def price_lookup(request):
    """JSON price for a product (and optional customer) after price lists and offers — used by the quote editor."""
    company = request.company
    if company is None:
        return JsonResponse({"error": "no company"}, status=400)
    product = Product.objects.for_company(company).filter(id=request.GET.get("product")).first()
    if product is None:
        return JsonResponse({"error": "not found"}, status=404)
    customer = Customer.objects.for_company(company).filter(id=request.GET.get("customer")).first()
    price, source, offer = resolve_commercial_price(company=company, customer=customer, product=product, date=timezone.localdate())
    return JsonResponse({"price": f"{price:.2f}", "source": source, "offer": offer.name if offer else ""})

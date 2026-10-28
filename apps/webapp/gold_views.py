"""Jewellery shops: the day's gold rate per karat and item prices from it."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.industry import gold as svc
from apps.industry.models import GoldRate
from apps.inventory.models import Product

from .industry_access import require_industry


@require_industry("gold")
def gold_rates(request):
    company = request.company
    if request.method == "POST":
        values = {k: request.POST.get(f"rate_{k}", "").strip() for k in svc.KARATS}
        try:
            saved = svc.set_rates(company, request.user, values)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("webapp:gold_rates")
        changed = svc.apply_to_products(company) if request.POST.get("apply") else 0
        messages.success(request, _("%(count)s rates saved; %(changed)s item prices updated.") % {
            "count": len(saved), "changed": changed})
        return redirect("webapp:gold_rates")
    rates = svc.current_rates(company)
    items = []
    for product in Product.objects.for_company(company).filter(is_active=True).order_by("name"):
        parts = svc.breakdown(product.attributes, rates)
        if parts or (product.attributes or {}).get("weight_grams"):
            items.append({"p": product, "parts": parts,
                          "stale": bool(parts and parts["total"] != product.selling_price)})
    from django.db.models import Sum
    from apps.industry.models import OldGoldExchange
    month = timezone.localdate().replace(day=1)
    old = OldGoldExchange.objects.for_company(company).select_related("customer", "invoice")
    return render(request, "webapp/industry/gold_rates.html", {
        "old_gold": old[:15],
        "old_gold_month": old.filter(date__gte=month).values("karat").annotate(weight=Sum("weight_grams"), value=Sum("value")).order_by("karat"),
        "karats": [(k, rates.get(k)) for k in svc.KARATS], "items": items,
        "history": GoldRate.objects.for_company(company)[:28], "today": timezone.localdate(),
        "stale_count": sum(1 for i in items if i["stale"])})

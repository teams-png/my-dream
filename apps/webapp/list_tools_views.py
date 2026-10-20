"""Quick changes from a list, without opening each record: a product's price edited in its cell, and the same
change made to many ticked products at once (price up / down by a percent, a new category, stop selling)."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.inventory.models import Product, ProductCategory

PRICE_FIELDS = {"selling_price", "cost_price"}
CENT = Decimal("0.01")


def _money(raw):
    try:
        value = Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return value.quantize(CENT, rounding=ROUND_HALF_UP) if value >= 0 and value < Decimal("1e10") else None


@login_required
@require_POST
def product_quick_update(request, product_id):
    product = get_object_or_404(Product.objects.for_company(request.company), id=product_id)
    field, value = request.POST.get("field"), _money(request.POST.get("value", ""))
    if field not in PRICE_FIELDS or value is None:
        return JsonResponse({"ok": False, "error": _("Enter a price of 0 or more.")}, status=400)
    setattr(product, field, value)
    product.save(update_fields=[field])
    return JsonResponse({"ok": True, "value": f"{value}"})


@login_required
@require_POST
def product_bulk(request):
    company = request.company
    ids = [int(x) for x in request.POST.getlist("ids") if x.isdigit()]
    products = Product.objects.for_company(company).filter(id__in=ids)
    action, count = request.POST.get("action"), products.count()
    back = request.POST.get("next") or "webapp:product_list"
    if not count:
        messages.error(request, _("Tick at least one product first."))
        return redirect(back if back.startswith("/") else "webapp:product_list")
    if action == "price_pct":
        try:
            pct = Decimal(request.POST.get("pct", "").strip())
        except (InvalidOperation, ValueError):
            pct = None
        if pct is None or not Decimal("-90") <= pct <= Decimal("500") or pct == 0:
            messages.error(request, _("Enter a percent between -90 and 500."))
        else:
            factor = 1 + pct / 100
            for p in products:
                p.selling_price = (p.selling_price * factor).quantize(CENT, rounding=ROUND_HALF_UP)
                p.save(update_fields=["selling_price"])
            messages.success(request, _("Selling price changed by %(pct)s%% for %(n)s products.") % {"pct": pct, "n": count})
    elif action == "category":
        raw = request.POST.get("category", "")
        category = (get_object_or_404(ProductCategory.objects.for_company(company), id=int(raw))
                    if raw.isdigit() else None)
        products.update(category=category)
        messages.success(request, _("%(n)s products moved.") % {"n": count})
    elif action == "deactivate":
        products.update(is_active=False)
        messages.success(request, _("%(n)s products will no longer be sold.") % {"n": count})
    else:
        messages.error(request, _("Choose what to do with the ticked products."))
    return redirect(back if back.startswith("/") else "webapp:product_list")

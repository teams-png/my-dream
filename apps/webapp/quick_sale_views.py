"""Restaurant Quick sale counter: tap items, change the rate if needed, take cash or card in one step."""
import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.verticals.restaurant import quick_sale as svc
from apps.verticals.restaurant.models import RestaurantMenuItem, RestaurantProfile

from .views import require_business_group, require_permission


def counter_view(view):
    return login_required(require_business_group("restaurant")(require_permission("restaurant.manage")(view)))


@counter_view
def quick_sale(request):
    company = request.company
    profile = RestaurantProfile.objects.for_company(company).first()
    from apps.verticals.restaurant.services import _restaurant_tax_percent
    tax = _restaurant_tax_percent(company)
    cfg = {"tax": float(tax), "currency": company.default_currency, "company": company.id, "name": company.name,
           "address": company.address, "phone": company.phone, "sync": reverse("webapp:restaurant_offline_sync"), "t": {
        "waiting": _("bills waiting to sync"), "synced": _("offline bills synced"), "savedOffline": _("Saved on this device"),
        "offlineBill": _("Offline bill — invoice number comes after sync"), "total": _("Total"), "thanks": _("Thank you!"),
        "quick": _("Quick"), "all": _("All"), "saved": _("Saved"), "print": _("Print receipt"), "change": _("Change"),
        "short": _("Short"), "needName": _("Type the item name and price."),
        "failed": _("Could not save the sale. Check the connection and try again.")}}
    return render(request, "webapp/restaurant/quick_sale.html", {
        "menu": svc.menu(company), "today": svc.today(company), "tax_percent": tax, "cfg": cfg,
        "currency": company.default_currency, "profile": profile,
    })


@counter_view
@require_POST
def quick_sale_submit(request):
    company = request.company
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": _("Could not read the sale. Try again.")}, status=400)
    try:
        order, invoice = svc.sell(company=company, user=request.user, lines=data.get("lines") or [],
                                  method=data.get("method") or "cash", reference=data.get("reference") or "")
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": " ".join(_(m) for m in exc.messages)}, status=400)
    today = svc.today(company)
    return JsonResponse({"ok": True, "number": order.order_number, "invoice": invoice.invoice_number,
                         "total": f"{invoice.total:.2f}", "receipt": reverse("webapp:restaurant_receipt_print", args=[order.pk]),
                         "today_total": f"{today['total']:.2f}", "today_count": today["count"]})


@counter_view
@require_POST
def quick_sale_pin(request):
    item = RestaurantMenuItem.objects.for_company(request.company).filter(product_id=request.POST.get("product")).first()
    if item is None:
        return JsonResponse({"ok": False}, status=404)
    item.is_quick = not item.is_quick
    item.save(update_fields=["is_quick"])
    return JsonResponse({"ok": True, "quick": item.is_quick})

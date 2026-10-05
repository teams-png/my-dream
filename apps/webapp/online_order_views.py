"""Restaurant website ordering: the switch and settings, and the inbox where staff accept or reject website orders."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy as _l
from django.views.decorators.http import require_POST

from apps.industry import website_kit
from apps.industry.models import SiteDesign
from apps.verticals.restaurant import online_orders as svc
from apps.verticals.restaurant.models import OnlineOrder, RestaurantProfile

from .views import require_business_group, require_permission


def staff_view(view):
    return login_required(require_business_group("restaurant")(require_permission("restaurant.manage")(view)))


class OrderingForm(forms.ModelForm):
    class Meta:
        model = RestaurantProfile
        fields = ["web_orders_enabled", "web_paused", "web_pickup", "web_delivery", "delivery_charge", "delivery_minimum",
                  "web_auto_accept", "web_ready_minutes", "web_note"]
        labels = {"web_orders_enabled": _l("Take orders from my website (cart)"), "web_paused": _l("Pause — not taking orders now"),
                  "web_pickup": _l("Pickup"), "web_delivery": _l("Home delivery"), "delivery_charge": _l("Delivery charge"),
                  "delivery_minimum": _l("Minimum order for delivery"), "web_auto_accept": _l("Send to kitchen without asking"),
                  "web_ready_minutes": _l("Ready in (minutes)"), "web_note": _l("Note in the cart")}
        help_texts = {"web_orders_enabled": _l("Shows “+ Add” on every menu item of your website and a cart."),
                      "web_paused": _l("Use when the kitchen is busy or closed. The menu stays; the cart says “not taking orders now”."),
                      "web_auto_accept": _l("Off: you accept each order first. On: orders go straight to the kitchen."),
                      "delivery_minimum": _l("0 = no minimum."), "web_note": _l("e.g. Delivery only inside Doha · Cash on delivery")}
        widgets = {"web_note": forms.TextInput(attrs={"placeholder": _l("Delivery only inside Doha · Cash on delivery")})}

    def clean(self):
        data = super().clean()
        if data.get("web_orders_enabled") and not (data.get("web_pickup") or data.get("web_delivery")):
            raise ValidationError(_("Choose pickup, delivery or both."))
        return data


@staff_view
def inbox(request):
    company = request.company
    profile = svc.profile_for(company)
    form = OrderingForm(instance=profile)
    qs = OnlineOrder.objects.for_company(company).select_related("order").prefetch_related("order__lines__product")
    since = timezone.now() - timedelta(days=2)
    active = [o for o in qs.filter(status="accepted", created_at__gte=since) if o.stage in ("preparing", "ready")]
    kit = website_kit.kit_for(company)
    design = SiteDesign.objects.filter(company=company).first()
    return render(request, "webapp/restaurant/online_orders.html", {
        "profile": profile, "form": form, "new": list(qs.filter(status="new")), "active": active,
        "recent": qs.exclude(status="new")[:30], "kit": kit, "currency": company.default_currency,
        "site_live": bool(design and design.enabled and design.published)})


@require_POST
@staff_view
def settings_save(request):
    form = OrderingForm(request.POST, instance=svc.profile_for(request.company))
    if form.is_valid():
        form.save()
        messages.success(request, _("Website ordering settings saved."))
    else:
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("webapp:restaurant_online_orders")


@require_POST
@staff_view
def action(request, online_id):
    online = get_object_or_404(OnlineOrder.objects.for_company(request.company).select_related("order"), id=online_id)
    try:
        if request.POST.get("do") == "accept":
            online = svc.accept(online, request.user)
            messages.success(request, _("Order %(no)s accepted and sent to the kitchen.") % {"no": online.order.order_number})
        elif request.POST.get("do") == "reject":
            online = svc.reject(online, request.user, request.POST.get("reason", ""))
            messages.success(request, _("Order %(no)s rejected.") % {"no": online.order.order_number})
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("webapp:restaurant_online_orders")


@login_required
def waiting(request):
    """Polled by the side menu badge on every page, so it never redirects or adds a message."""
    company, role = getattr(request, "company", None), getattr(request, "role", None)
    if company is None or not svc.is_restaurant(company) or (
            role is not None and not role.permissions.filter(permission__code="restaurant.manage").exists()):
        return JsonResponse({"enabled": False, "new": 0})
    profile = RestaurantProfile.objects.for_company(company).first()
    return JsonResponse({"enabled": bool(profile and profile.web_orders_enabled), "new": svc.waiting_count(company)})

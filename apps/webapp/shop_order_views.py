"""Online shop for shops that sell products: the cart switch and settings, and the inbox where staff confirm,
send, bill or reject website orders."""
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _, gettext_lazy as _l
from django.views.decorators.http import require_POST

from apps.industry import shop_orders as svc
from apps.industry import site_builder, website_kit
from apps.industry.models import ShopOrder, SiteDesign
from apps.sales.sharing import normalise_phone


class ShopForm(forms.ModelForm):
    class Meta:
        model = SiteDesign
        fields = ["shop_enabled", "shop_paused", "shop_pickup", "shop_delivery", "shop_delivery_fee",
                  "shop_free_delivery_over", "shop_minimum", "shop_note"]
        labels = {"shop_enabled": _l("Take orders from my website (cart)"), "shop_paused": _l("Pause — not taking orders now"),
                  "shop_pickup": _l("Pickup from the shop"), "shop_delivery": _l("Home delivery"),
                  "shop_delivery_fee": _l("Delivery charge"), "shop_free_delivery_over": _l("Free delivery over"),
                  "shop_minimum": _l("Minimum order for delivery"), "shop_note": _l("Note in the cart")}
        help_texts = {"shop_enabled": _l("Shows “+ Add” on every product in stock and a cart on your website."),
                      "shop_free_delivery_over": _l("0 = always charge delivery."), "shop_minimum": _l("0 = no minimum.")}
        widgets = {"shop_note": forms.TextInput(attrs={"placeholder": _l("Delivery inside Doha in 24 hours · Cash or card on delivery")})}

    def clean(self):
        data = super().clean()
        if data.get("shop_enabled") and not (data.get("shop_pickup") or data.get("shop_delivery")):
            raise ValidationError(_("Choose pickup, delivery or both."))
        return data


def _company_or_404(request):
    if request.company is None or not svc.applies(request.company):
        raise Http404
    return request.company


def _whatsapp(order):
    phone = normalise_phone(order.phone, order.company.country)
    return f"https://wa.me/{phone}?text={quote(svc.whatsapp_text(order))}" if phone else ""


@login_required
def inbox(request):
    company = _company_or_404(request)
    design = site_builder.design_for(company)
    qs = ShopOrder.objects.for_company(company).prefetch_related("lines")
    show = request.GET.get("show", "open")
    orders = qs.filter(status__in=svc.OPEN) if show == "open" else qs
    orders = list(orders[:100])
    for o in orders:
        o.whatsapp = _whatsapp(o)
    kit = website_kit.kit_for(company)
    return render(request, "webapp/shop_orders/inbox.html", {
        "orders": orders, "show": show, "design": design, "form": ShopForm(instance=design, prefix="s"),
        "new_count": qs.filter(status="new").count(), "currency": company.default_currency, "kit": kit,
        "site_url": f"https://{design.custom_domain}" if design.custom_domain and design.domain_status == "live" else
        request.build_absolute_uri(f"/site/{kit.public_id}/")})


@login_required
@require_POST
def settings_save(request):
    company = _company_or_404(request)
    from .role_access import can_open
    if not can_open(request, "shop_order_settings"):
        raise Http404
    form = ShopForm(request.POST, instance=site_builder.design_for(company), prefix="s")
    if form.is_valid():
        form.save()
        messages.success(request, _("Online shop settings saved."))
    else:
        messages.error(request, " ".join(str(e) for errs in form.errors.values() for e in errs))
    return redirect("webapp:shop_orders")


@login_required
@require_POST
def action(request, order_id):
    company = _company_or_404(request)
    order = get_object_or_404(ShopOrder.objects.for_company(company), id=order_id)
    what = request.POST.get("do")
    try:
        if what == "confirm":
            order = svc.confirm(order, request.user)
            messages.success(request, _("Order %(ref)s confirmed. Let the customer know on WhatsApp.") % {"ref": order.number})
        elif what == "ready":
            order = svc.mark_ready(order, request.user)
            messages.success(request, _("Order %(ref)s marked ready.") % {"ref": order.number})
        elif what == "bill":
            order = svc.make_bill(order, request.user)
            messages.success(request, _("Bill %(inv)s made for %(ref)s. Stock is updated.") % {
                "inv": order.invoice.invoice_number, "ref": order.number})
        elif what in ("reject", "cancel"):
            order = svc.reject(order, request.user, request.POST.get("reason", ""),
                               status="rejected" if what == "reject" else "cancelled")
            messages.success(request, _("Order %(ref)s closed.") % {"ref": order.number})
        else:
            raise Http404
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages) + " " + _("You can also bill it from New bill."))
    return redirect(request.POST.get("next") or "webapp:shop_orders")


@login_required
def waiting(request):
    if request.company is None or not svc.applies(request.company):
        return JsonResponse({"count": 0})
    return JsonResponse({"count": svc.waiting_count(request.company)})

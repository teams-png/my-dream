"""Website kit: public feeds and forms for client websites, and the platform admin's kit pages."""
import io
import json
import zipfile

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.industry import careers as careers_svc
from apps.industry import online_booking as booking_svc
from apps.industry import website_kit as svc
from apps.industry.models import BookingSite, CareersSite, OnlineBooking, SiteDesign, WebsiteKit
from apps.tenants.models import Company

from .views import superuser_required

RATE_LIMIT = 10


def _origin(request):
    from urllib.parse import urlsplit
    for header in ("Origin", "Referer"):
        value = request.headers.get(header) or ""
        if value:
            parts = urlsplit(value)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
    return ""


def _kit_or_404(public_id):
    kit = svc.by_public_id(public_id)
    if kit is None:
        raise Http404
    return kit


def _public_json(data, status=200):
    response = JsonResponse(data, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    response["Cache-Control"] = "public, max-age=60"
    return response


# ------------------------------------------------------------------ public feeds

def kit_info(request, public_id):
    kit = _kit_or_404(public_id)
    company = kit.company
    data = svc.info(company, request.build_absolute_uri)
    caps = svc.capabilities(company)
    links = {"enquiry_form_js": request.build_absolute_uri(reverse("webapp:kit_enquiry_js", args=[public_id])),
             "catalogue": request.build_absolute_uri(reverse("webapp:kit_catalogue", args=[public_id]))}
    if caps["booking"]:
        site = booking_svc.site_for(company)
        links["booking_form_js"] = request.build_absolute_uri(reverse("webapp:book_form_js", args=[site.slug]))
        links["booking_page"] = request.build_absolute_uri(reverse("webapp:book_page", args=[site.slug]))
    if caps["careers"]:
        site = careers_svc.site_for(company)
        links["careers_form_js"] = request.build_absolute_uri(reverse("webapp:careers_form_js", args=[site.slug]))
    return _public_json({**data, "capabilities": caps, "links": links})


def _feed_labels(company, wanted):
    """Words a website shows around the live data (WordPress plugin), in the visitor's language."""
    from django.utils import translation
    from django.utils.translation import gettext as _
    with translation.override(site_lang(company, wanted)):
        return {"add": _("+ Add"), "sold_out": _("Sold out"), "veg": _("Veg"), "off": _("off"), "until": _("Until"),
                "unit_hour": _("hour"), "unit_day": _("day"), "unit_night": _("night"), "unit_month": _("month"),
                "unit_monthly": _("month")}


def kit_catalogue(request, public_id):
    kit = _kit_or_404(public_id)
    data = svc.catalogue(kit.company, request.build_absolute_uri)
    if request.GET.get("lang"):
        data["labels"] = _feed_labels(kit.company, request.GET["lang"])
    return _public_json(data)


def kit_offers(request, public_id):
    kit = _kit_or_404(public_id)
    data = svc.offers(kit.company)
    if request.GET.get("lang"):
        data["labels"] = _feed_labels(kit.company, request.GET["lang"])
    return _public_json(data)


def _too_many(request, kit):
    from apps.accounts.services import client_ip
    ip = client_ip(request) or "?"
    key = f"kit-enquiry:{kit.pk}:{ip}"
    if cache.add(key, 1, 3600):
        return False
    try:
        return cache.incr(key) > RATE_LIMIT
    except ValueError:
        cache.set(key, 1, 3600)
        return False


@csrf_exempt  # posted from client websites; honeypot + rate limit (API key for servers)
def kit_enquiry(request, public_id):
    kit = _kit_or_404(public_id)
    origin = _origin(request)
    if request.method == "OPTIONS":
        response = HttpResponse()
    elif request.method != "POST":
        raise Http404
    else:
        data = request.POST
        if request.content_type == "application/json":
            try:
                data = json.loads(request.body or b"{}")
            except ValueError:
                data = {}
        trusted = svc.key_ok(kit.company, request.headers.get("X-Api-Key", ""))
        if data.get("company_website"):
            body, status = {"ok": True}, 201
        elif not trusted and _too_many(request, kit):
            body, status = {"ok": False, "error": "Too many messages. Please call or WhatsApp us."}, 429
        else:
            try:
                lead = svc.create_enquiry(kit, data, source=origin.split("://", 1)[-1] if origin else ("api" if trusted else ""))
                body, status = {"ok": True, "reference": f"L-{lead.pk:05d}"}, 201
            except ValidationError as exc:
                body, status = {"ok": False, "error": " ".join(exc.messages)}, 400
        response = JsonResponse(body, status=status)
    if origin:
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Key"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def _js(request, template, cfg):
    body = render_to_string(template, {"cfg": json.dumps(cfg).replace("</", "<\\/")})
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "public, max-age=120"
    response["Access-Control-Allow-Origin"] = "*"
    return response


def kit_enquiry_js(request, public_id):
    kit = _kit_or_404(public_id)
    from django.utils import translation
    from django.utils.translation import gettext as _
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        t = {"title": _("Send us a message"), "name": _("Your name"), "phone": _("Phone / WhatsApp"), "email": _("Email"),
             "subject": _("Subject"), "message": _("Message"), "send": _("Send"), "sending": _("Sending…"),
             "ok": _("Thank you! We will get back to you soon."), "fail": _("Could not send. Please try again."),
             "req": _("Please enter your name and a phone number or email.")}
        rtl = translation.get_language_bidi()
    return _js(request, "webapp/website_kit/enquiry.js", {
        "endpoint": request.build_absolute_uri(reverse("webapp:kit_enquiry", args=[public_id])),
        "company": kit.company.name, "color": kit.accent_color or "#0f766e", "lang": lang, "t": t, "rtl": rtl})


def kit_catalogue_js(request, public_id):
    kit = _kit_or_404(public_id)
    return _js(request, "webapp/website_kit/catalogue.js", {
        "feed": request.build_absolute_uri(reverse("webapp:kit_catalogue", args=[public_id])),
        "color": kit.accent_color or "#0f766e"})


# ------------------------------------------------------------------ full shop for any website (WordPress, Bootstrap, HTML)

def _shop_design(kit):
    from apps.industry import site_builder
    from apps.industry import shop_orders
    if not shop_orders.applies(kit.company):
        raise Http404
    return site_builder.design_for(kit.company)


def kit_shop_json(request, public_id):
    """Products with filters for shop.js: the same data as the hosted Shop page."""
    from django.utils import translation
    from apps.industry import site_builder
    kit = _kit_or_404(public_id)
    design = _shop_design(kit)
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        data = site_builder.shop_page(design, request.build_absolute_uri, "", lang, False, request.GET)
        facets = data["facets"]
        body = {"currency": kit.company.default_currency, "total": data["total"], "page": data["page"], "pages": data["pages"],
                "category": data["category"].id if data["category"] else None,
                "categories": [{"id": c.id, "name": c.name} for c in data["categories"]],
                "facets": {"brand": facets["brands"], "colour": facets["colours"], "size": facets["sizes"],
                           "attrs": facets["attrs"], "price_lo": facets["price_lo"], "price_hi": facets["price_hi"]},
                "items": [{k: v for k, v in i.items() if k != "url"} for i in data["items"]],
                "ordering": bool(data["ordering"])}
    response = _public_json(body)
    response["Cache-Control"] = "public, max-age=60"
    return response


def kit_product_json(request, public_id, product_id):
    from django.utils import translation
    from apps.industry import site_builder
    kit = _kit_or_404(public_id)
    design = _shop_design(kit)
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        data = site_builder.product_page(design, request.build_absolute_uri, "", lang, False, product_id)
        if data is None:
            raise Http404
        item = {k: v for k, v in data["item"].items() if k not in ("url", "category_url")}
        chart = data.get("size_chart")
        body = {"currency": kit.company.default_currency, "item": item, "ordering": bool(data["ordering"]),
                "specs": [[str(k), str(v)] for k, v in data["specs"]], "photos": data["photos"],
                "options": [{"id": o["id"], "label": o["label"]} for o in data["options"]],
                "size_chart": {"name": chart.name, "rows": chart.rows, "note": chart.note} if chart else None,
                "reviews_on": data["reviews_on"],
                "reviews": [{"name": r.name, "rating": r.rating, "text": r.text, "date": r.created_at.strftime("%d %b %Y")}
                            for r in data["product_reviews"]],
                "related": [{k: v for k, v in i.items() if k != "url"} for i in data["related"]]}
    response = _public_json(body)
    response["Cache-Control"] = "public, max-age=60"
    return response


@csrf_exempt
def kit_review(request, public_id, product_id):
    from apps.industry import shop_orders
    from apps.industry.models import ProductReview
    kit = _kit_or_404(public_id)
    if request.method == "OPTIONS":
        return _cors(request, HttpResponse())
    design = _shop_design(kit)
    if request.method != "POST" or not design.shop_reviews:
        raise Http404
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    product = shop_orders.sellable(kit.company).filter(id=product_id).first()
    name = str(data.get("name") or "").strip()[:80]
    if product and len(name) >= 2 and not data.get("company_website") and not _too_many(request, kit):
        try:
            rating = min(5, max(1, int(data.get("rating") or 5)))
        except (TypeError, ValueError):
            rating = 5
        ProductReview.objects.create(company=kit.company, product=product, name=name, rating=rating,
                                     text=str(data.get("text") or "").strip()[:2000])
    return _cors(request, JsonResponse({"ok": True}, status=201))


def kit_shop_js(request, public_id):
    from django.utils import translation
    from django.utils.translation import gettext as _
    kit = _kit_or_404(public_id)
    _shop_design(kit)
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        t = {k: str(v) for k, v in {
            "all": _("All"), "filters": _("Filters"), "search": _("Search products…"), "price": _("Price"),
            "in_stock": _("In stock only"), "brand": _("Brand"), "colour": _("Colour"), "size": _("Size"),
            "apply": _("Apply"), "clear": _("Clear all"), "sort_name": _("Sort: name"), "sort_low": _("Price: low to high"),
            "sort_high": _("Price: high to low"), "sort_new": _("Newest"), "none": _("No products found."),
            "add": _("+ Add"), "add_cart": _("Add to cart"), "sold_out": _("Sold out"), "sale": _("Sale"),
            "back": _("Back to shop"), "prev": _("Previous"), "next": _("Next"), "reviews": _("Reviews"),
            "write_review": _("Write a review"), "your_name": _("Your name"), "liked": _("What did you like?"),
            "send_review": _("Send review"), "review_thanks": _("Thank you! Your review will show after the shop checks it."),
            "no_reviews": _("No reviews yet. Be the first!"), "size_chart": _("Size chart"), "options": _("Options"),
            "also": _("You may also like"), "in_stock_label": _("In stock"), "wishlist": _("My wishlist"),
            "products": _("products"), "left": _("left"), "ask": _("Ask on WhatsApp")}.items()}
        rtl = translation.get_language_bidi()
    from apps.industry.website_kit import info
    phone = "".join(ch for ch in (kit.company.phone or "") if ch.isdigit())
    cfg = {"shop": request.build_absolute_uri(reverse("webapp:kit_shop_json", args=[public_id])),
           "product": request.build_absolute_uri(reverse("webapp:kit_product_json", args=[public_id, 0])).replace("/0.json", "/{id}.json"),
           "review": request.build_absolute_uri(reverse("webapp:kit_review", args=[public_id, 0])).replace("/0/review/", "/{id}/review/"),
           "order_js": request.build_absolute_uri(reverse("webapp:kit_order_js", args=[public_id])) + f"?lang={lang}",
           "color": kit.accent_color or "#0f766e", "lang": lang, "rtl": rtl, "t": t, "whatsapp": phone,
           "key": f"bp-wish-{public_id}"}
    response = _js(request, "webapp/website_kit/shop.js", cfg)
    response["Cache-Control"] = "public, max-age=300"
    return response


# ------------------------------------------------------------------ website ordering (restaurant cart)

ORDER_LIMIT = 6  # orders per hour from one visitor


def _order_flood(request, kit):
    from apps.accounts.services import client_ip
    ip = client_ip(request) or "?"
    key = f"kit-order:{kit.pk}:{ip}"
    if cache.add(key, 1, 3600):
        return False
    try:
        return cache.incr(key) > ORDER_LIMIT
    except ValueError:
        cache.set(key, 1, 3600)
        return False


def _cors(request, response, methods="POST, OPTIONS"):
    origin = _origin(request)
    if origin:
        response["Access-Control-Allow-Origin"] = origin
        response["Vary"] = "Origin"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-Api-Key"
        response["Access-Control-Allow-Methods"] = methods
    return response


@csrf_exempt  # posted from client websites; prices come from BookPilot, honeypot + rate limit
def kit_order(request, public_id):
    from apps.verticals.restaurant import online_orders
    kit = _kit_or_404(public_id)
    if request.method == "OPTIONS":
        return _cors(request, HttpResponse())
    if request.method != "POST":
        raise Http404
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}
    trusted = svc.key_ok(kit.company, request.headers.get("X-Api-Key", ""))
    origin = _origin(request)
    if data.get("company_website"):
        body, status = {"ok": True, "reference": "ORD-000000"}, 201
    elif not trusted and _order_flood(request, kit):
        body, status = {"ok": False, "error": "Too many orders from this device. Please call us."}, 429
    else:
        from django.utils import translation
        lang = site_lang(kit.company, str(data.get("lang") or ""))
        try:
            source = origin.split("://", 1)[-1] if origin else ("api" if trusted else "")
            with translation.override(lang):
                if online_orders.is_restaurant(kit.company):
                    online = online_orders.place(kit.company, data, source=source)
                    reference, accepted = online.order.order_number, online.status == "accepted"
                else:
                    from apps.industry import shop_orders
                    online = shop_orders.place(kit.company, data, source=source)
                    reference, accepted = online.number, False
                    pay = shop_orders.pay_url(online, request.build_absolute_uri)
            track = request.build_absolute_uri(reverse("webapp:kit_order_status", args=[public_id, online.token])) + f"?lang={lang}"
            body, status = {"ok": True, "reference": reference, "total": f"{online.total:.2f}",
                            "track_url": track, "accepted": accepted}, 201
            if not online_orders.is_restaurant(kit.company) and pay:
                body["pay_url"] = pay
        except ValidationError as exc:
            with translation.override(lang):
                body, status = {"ok": False, "error": " ".join(str(m) for m in exc.messages)}, 400
    return _cors(request, JsonResponse(body, status=status))


def site_lang(company, wanted=None):
    """The visitor's language for public widgets: ?lang= if BookPilot has it, else the website's main language."""
    from django.conf import settings
    codes = dict(settings.LANGUAGES)
    if wanted and wanted.lower() in codes:
        return wanted.lower()
    design = SiteDesign.objects.filter(company=company).first()
    return design.language if design and design.language in codes else "en"


def cart_labels(shop=False):
    from django.utils.translation import gettext as _
    labels = _cart_labels()
    if shop:  # a shop, not a restaurant
        labels.update(coupon=_("Coupon code"), apply=_("Apply"), pay_cod=_("Pay on delivery / pickup"),
                      pay_online=_("Pay online now (card)"), pay_now=_("Pay now"), discount=_("Discount"),
                      terms=_("By ordering you agree to our terms."), going_to_pay=_("Taking you to the secure payment page…"))
        labels.update(will_confirm=_("The shop will confirm your order shortly."), pickup_from=_("Pickup from the shop"),
                      empty=_("Your cart is empty. Tap “+ Add” on a product."),
                      note=_("Note, e.g. colour, model, best time to call"), email=_("Email (optional)"),
                      free_over=_("Free delivery over %s"))
    return labels


def _cart_labels():
    from django.utils.translation import gettext as _
    return {"your_order": _("Your order"), "view_order": _("View order"), "order_sent": _("Order sent"),
            "thanks": _("Thank you!"), "in_kitchen": _("Your order is in the kitchen."),
            "will_confirm": _("The restaurant will confirm your order shortly."),
            "ready_in": _("Usually ready in about %s minutes."), "total": _("Total"), "items": _("Items"),
            "pay_delivery": _("Pay on delivery"), "pay_pickup": _("Pay on pickup"), "track": _("Track my order"),
            "empty": _("Your cart is empty. Tap “+ Add” on the menu."), "pickup": _("Pickup"), "delivery": _("Delivery"),
            "pickup_from": _("Pickup from the restaurant"), "home_delivery": _("Home delivery"), "close": _("Close"),
            "closed": _("Sorry, we are not taking online orders right now."), "call": _("Please call %s."),
            "minimum": _("Minimum for delivery:"), "name": _("Your name"),
            "phone": _("Phone / WhatsApp, e.g. +974 5555 1234"),
            "address": _("Delivery address (zone, street, building, flat)"), "note": _("Note, e.g. less spicy, no onion"),
            "sending": _("Sending…"), "place": _("Place order"), "need_name": _("Please enter your name."),
            "need_phone": _("Please enter your phone number."), "need_address": _("Please enter the delivery address."),
            "failed": _("Could not send the order. Please try again."), "offline": _("No connection. Please try again."),
            "added": _("Added:")}


def kit_order_js(request, public_id):
    from django.utils import translation
    from apps.verticals.restaurant import online_orders
    kit = _kit_or_404(public_id)
    lang = site_lang(kit.company, request.GET.get("lang"))
    cfg = online_orders.config(kit.company)
    shop = cfg is None
    if shop:
        from apps.industry import shop_orders
        cfg = shop_orders.config(kit.company)
    cfg = cfg or {"enabled": False}
    with translation.override(lang):
        cfg.update(t=cart_labels(shop=shop), lang=lang, rtl=translation.get_language_bidi())
    if cfg.get("terms_url"):
        cfg["terms_url"] = request.build_absolute_uri(reverse("webapp:site_public", args=[public_id]) + cfg["terms_url"])
    if cfg.get("coupons"):
        cfg["coupon_endpoint"] = request.build_absolute_uri(reverse("webapp:kit_coupon", args=[public_id]))
    cfg.update(endpoint=request.build_absolute_uri(reverse("webapp:kit_order", args=[public_id])),
               color=kit.accent_color or "#0f766e", key=f"bp-cart-{public_id}", phone=kit.company.phone or "")
    response = _js(request, "webapp/website_kit/order.js", cfg)
    response["Cache-Control"] = "public, max-age=60"
    return response


def kit_coupon(request, public_id):
    """Checks a coupon for the website cart: {ok, discount} for the given subtotal (the order re-checks it)."""
    from decimal import Decimal, InvalidOperation
    from django.utils import timezone, translation
    from apps.industry import shop_orders
    from django.utils.translation import gettext as _
    from apps.sales.services import validate_coupon
    kit = _kit_or_404(public_id)
    from apps.accounts.services import client_ip
    ip = client_ip(request) or "?"
    key = f"kit-coupon:{kit.pk}:{ip}"
    if not cache.add(key, 1, 3600):
        try:
            tries = cache.incr(key)
        except ValueError:
            tries = 1
    else:
        tries = 1
    cfg = shop_orders.config(kit.company)
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        if not cfg or not cfg.get("coupons") or tries > 30:  # no guessing codes
            return _public_json({"ok": False, "error": _("This coupon code is not valid.")}, 400)
        try:
            subtotal = Decimal(request.GET.get("subtotal") or "0")
            _c, discount = validate_coupon(company=kit.company, code=request.GET.get("code") or "", subtotal=subtotal,
                                           date=timezone.localdate())
        except (ValidationError, InvalidOperation):
            return _public_json({"ok": False, "error": _("This coupon code is not valid.")}, 400)
    response = _public_json({"ok": True, "discount": f"{discount:.2f}"})
    response["Cache-Control"] = "no-store"
    return response


def kit_order_status(request, public_id, token):
    from apps.industry.models import ShopOrder
    from apps.verticals.restaurant.models import OnlineOrder
    kit = _kit_or_404(public_id)
    shop_order = ShopOrder._base_manager.select_related("company").filter(token=token, company=kit.company).first()
    if shop_order is not None:
        return _shop_order_status(request, kit, shop_order)
    online = get_object_or_404(OnlineOrder._base_manager.select_related("order", "company"), token=token, company=kit.company)
    lines = [line for line in online.order.lines.select_related("product") if line.product.sku != "DELIVERY-FEE"]
    fee = sum((line.total for line in online.order.lines.all() if line.product.sku == "DELIVERY-FEE"), 0)
    if request.GET.get("format") == "json":
        return _public_json({"reference": online.order.order_number, "stage": online.stage})
    from django.utils import translation
    lang = site_lang(kit.company, request.GET.get("lang"))
    with translation.override(lang):
        return render(request, "webapp/restaurant/online_status.html", {"lang": lang, "lang_bidi": translation.get_language_bidi(),
        "online": online, "order": online.order, "company": kit.company, "lines": lines, "fee": fee,
        "color": kit.accent_color or "#0f766e", "steps": _steps(online.stage)})


def _shop_order_status(request, kit, order):
    from django.utils import translation
    if request.GET.get("format") == "json":
        return _public_json({"reference": order.number, "stage": order.status})
    lang = site_lang(kit.company, request.GET.get("lang"))
    names = ["new", "confirmed", "ready", "done"]
    reached = names.index(order.status) if order.status in names else -1
    with translation.override(lang):
        return render(request, "webapp/site/shop_order_status.html", {
            "lang": lang, "lang_bidi": translation.get_language_bidi(), "order": order, "company": kit.company,
            "lines": order.lines.all(), "color": kit.accent_color or "#0f766e",
            "steps": [(name, i <= reached) for i, name in enumerate(names)]})


def _steps(stage):
    names = ["new", "preparing", "ready", "done"]
    reached = names.index(stage) if stage in names else -1
    return [(name, i <= reached) for i, name in enumerate(names)]


# ------------------------------------------------------------------ platform admin

class KitForm(forms.ModelForm):
    class Meta:
        model = WebsiteKit
        fields = ["public_id", "enquiry_enabled", "accent_color", "allowed_origins", "notes"]
        widgets = {"allowed_origins": forms.Textarea(attrs={"rows": 2, "placeholder": "https://www.client.com"}),
                   "notes": forms.Textarea(attrs={"rows": 3}), "accent_color": forms.TextInput(attrs={"type": "color"})}
        labels = {"public_id": "Public ID (used in URLs)"}

    def clean_public_id(self):
        from django.utils.text import slugify
        value = slugify(self.cleaned_data["public_id"])[:60]
        if not value:
            raise ValidationError("Enter a short ID.")
        if WebsiteKit.objects.filter(public_id=value).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This ID is taken.")
        return value

    def clean_allowed_origins(self):
        from urllib.parse import urlsplit
        out = []
        for line in self.cleaned_data["allowed_origins"].replace(",", "\n").splitlines():
            line = line.strip()
            if not line:
                continue
            if "://" not in line:
                line = "https://" + line
            parts = urlsplit(line)
            if not parts.netloc:
                raise ValidationError("Enter website addresses like https://www.client.com")
            origin = f"{parts.scheme}://{parts.netloc.lower()}"
            if origin not in out:
                out.append(origin)
        return "\n".join(out)


@login_required
@superuser_required
def kit_list(request):
    query = (request.GET.get("q") or "").strip()
    companies = Company.objects.filter(is_active=True).select_related("business_type").order_by("name")
    if query:
        companies = companies.filter(Q(name__icontains=query) | Q(business_type__name__icontains=query) | Q(email__icontains=query))
    page = Paginator(companies, 40).get_page(request.GET.get("page"))
    kits = {k.company_id: k for k in WebsiteKit._base_manager.filter(company__in=page.object_list)}
    rows = [{"company": c, "kit": kits.get(c.id), "caps": svc.capabilities(c)} for c in page.object_list]
    return render(request, "webapp/website_kit/list.html", {"page": page, "rows": rows, "q": query})


def _abs(request, name, *args):
    return request.build_absolute_uri(reverse(name, args=args))


@login_required
@superuser_required
def kit_detail(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    kit = svc.kit_for(company)
    caps = svc.capabilities(company)
    booking_site = booking_svc.site_for(company) if caps["booking"] else None
    careers_site = careers_svc.site_for(company) if caps["careers"] else None
    form = KitForm(request.POST if request.POST.get("action") == "kit" else None, instance=kit, prefix="kit")
    from .careers_views import SiteForm as CareersForm
    from .online_booking_views import SiteForm as BookingForm
    bform = BookingForm(request.POST if request.POST.get("action") == "booking" else None, instance=booking_site,
                        prefix="b") if booking_site else None
    cform = CareersForm(request.POST if request.POST.get("action") == "careers" else None, instance=careers_site,
                        prefix="c") if careers_site else None
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("connect", "disconnect", "test"):
            if action == "connect":
                origins = _normalise_origins(request.POST.get("domain") or "")
                if not origins:
                    messages.error(request, "Enter the client's website address, e.g. www.client.com")
                    return redirect("webapp:kit_detail", company.id)
                kit.allowed_origins = "\n".join(origins)
                kit.connected_at = timezone.now()
                kit.save(update_fields=["allowed_origins", "connected_at"])
            elif action == "disconnect":
                kit.allowed_origins, kit.connected_at, kit.last_check, kit.last_check_ok = "", None, "", False
                kit.save(update_fields=["allowed_origins", "connected_at", "last_check", "last_check_ok"])
            if careers_site:  # one list of client domains for every form
                CareersSite.objects.filter(pk=careers_site.pk).update(allowed_origins=kit.allowed_origins)
            if action != "disconnect" and kit.allowed_origins:
                ok, text = check_connection(request, kit, request.POST.get("page") or "")
                messages.success(request, text) if ok else messages.warning(request, text)
            elif action == "disconnect":
                messages.success(request, "Website disconnected.")
            return redirect("webapp:kit_detail", company.id)
        if action == "ordering":
            from apps.verticals.restaurant import online_orders
            if online_orders.is_restaurant(company):
                profile = online_orders.profile_for(company)
                profile.web_orders_enabled = not profile.web_orders_enabled
                if profile.web_orders_enabled and not (profile.web_pickup or profile.web_delivery):
                    profile.web_pickup = True
                profile.save(update_fields=["web_orders_enabled", "web_pickup"])
                messages.success(request, "Website ordering is now " + ("ON." if profile.web_orders_enabled else "OFF."))
            return redirect("webapp:kit_detail", company.id)
        target = {"kit": form, "booking": bform, "careers": cform}.get(action)
        if action == "new_key":
            import secrets
            kit.api_key = secrets.token_urlsafe(32)[:48]
            kit.save(update_fields=["api_key"])
            messages.success(request, "New API key created. Update it in the client's website.")
            return redirect("webapp:kit_detail", company.id)
        if target is not None and target.is_valid():
            target.save()
            if action == "kit" and careers_site:  # one list of client domains for every form
                CareersSite.objects.filter(pk=careers_site.pk).update(allowed_origins=kit.allowed_origins)
            messages.success(request, "Saved.")
            return redirect("webapp:kit_detail", company.id)
    pid = kit.public_id
    urls = {"info": _abs(request, "webapp:kit_info", pid), "catalogue": _abs(request, "webapp:kit_catalogue", pid),
            "enquiry": _abs(request, "webapp:kit_enquiry", pid), "enquiry_js": _abs(request, "webapp:kit_enquiry_js", pid),
            "catalogue_js": _abs(request, "webapp:kit_catalogue_js", pid)}
    from apps.industry import shop_orders
    if shop_orders.applies(company):
        urls["shop_js"] = _abs(request, "webapp:kit_shop_js", pid)
    if booking_site:
        urls.update(booking_js=_abs(request, "webapp:book_form_js", booking_site.slug),
                    booking_page=_abs(request, "webapp:book_page", booking_site.slug),
                    booking_submit=_abs(request, "webapp:book_submit", booking_site.slug),
                    booking_options=_abs(request, "webapp:book_options", booking_site.slug))
    if careers_site:
        urls.update(careers_js=_abs(request, "webapp:careers_form_js", careers_site.slug),
                    careers_apply=_abs(request, "webapp:careers_apply", careers_site.slug),
                    careers_jobs=_abs(request, "webapp:careers_jobs_json", careers_site.slug),
                    careers_page=_abs(request, "webapp:careers_home", careers_site.slug),
                    connect_js=_abs(request, "webapp:careers_connect_js", careers_site.slug))
    stats = {"leads": _count_leads(company), "bookings": OnlineBooking._base_manager.filter(company=company).count(),
             "applications": _count_applications(company)}
    ctx = {"company": company, "kit": kit, "caps": caps, "form": form, "bform": bform, "cform": cform, "urls": urls,
           "booking_site": booking_site, "careers_site": careers_site, "stats": stats,
           "base": request.build_absolute_uri("/").rstrip("/"),
           "site_design": SiteDesign.objects.filter(company=company).first(), "ordering": _ordering_profile(company)}
    ctx["snippets"] = _snippets(ctx)
    return render(request, "webapp/website_kit/detail.html", ctx)


def _ordering_profile(company):
    from apps.verticals.restaurant import online_orders
    return online_orders.profile_for(company) if online_orders.is_restaurant(company) else None


def _normalise_origins(text):
    from urllib.parse import urlsplit
    out = []
    for line in text.replace(",", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        if "://" not in line:
            line = "https://" + line
        parts = urlsplit(line)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or "." not in host:
            continue
        port = f":{parts.port}" if parts.port else ""
        for h in (host, host[4:] if host.startswith("www.") else (f"www.{host}" if host.count(".") == 1 else None)):
            if h and f"{parts.scheme}://{h}{port}" not in out:
                out.append(f"{parts.scheme}://{h}{port}")
    return out


def check_connection(request, kit, page=""):
    """Opens the client's website and looks for the BookPilot form / plugin on it."""
    import requests
    base = request.build_absolute_uri("/").rstrip("/")
    first = sorted(svc.origins(kit))[0] if svc.origins(kit) else ""
    url = page.strip() or first
    if url and "://" not in url:
        url = "https://" + url
    markers = [f"/kit/{kit.public_id}/"]
    company = kit.company
    for model, prefix in ((BookingSite, "/book/"), (CareersSite, "/careers/")):
        site = model.objects.filter(company=company).first()
        if site:
            markers.append(f"{prefix}{site.slug}/")
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "BookPilot-connection-check/1.0"})
        html = resp.text[:2_000_000]
        found = [m for m in markers if m in html]
        if resp.status_code >= 400:
            ok, text = False, f"{url} answered with HTTP {resp.status_code}."
        elif found:
            ok, text = True, f"Connected ✓ — {url} has the BookPilot form ({', '.join(found)})."
        elif base.split("://", 1)[-1] in html or "bookpilot-" in html:
            ok, text = True, f"Connected ✓ — {url} loads BookPilot."
        else:
            ok, text = False, (f"{url} is reachable, but no BookPilot form was found on that page yet. "
                               "Add the plugin shortcode or the code, then test the page where the form is.")
    except requests.RequestException as exc:
        ok, text = False, f"Could not open {url}: {exc.__class__.__name__}."
    kit.last_checked_at, kit.last_check, kit.last_check_ok = timezone.now(), text[:255], ok
    kit.save(update_fields=["last_checked_at", "last_check", "last_check_ok"])
    return ok, text


def _count_leads(company):
    from apps.crm.models import Lead
    return Lead._base_manager.filter(company=company, source__startswith="Website").count()


def _count_applications(company):
    from apps.industry.models import Candidate
    return Candidate._base_manager.filter(company=company, source="website").count()


def _snippets(ctx):
    urls = ctx["urls"]
    out = [("Contact / enquiry form", f'<div class="bookpilot-enquiry"></div>\n<script src="{urls["enquiry_js"]}" defer></script>'),
           ("Catalogue list (" + ctx["caps"]["catalogue"] + ")",
            f'<div class="bookpilot-catalogue"></div>\n<script src="{urls["catalogue_js"]}" defer></script>')]
    if "shop_js" in urls:
        out.insert(0, ("Full online shop (filters, product pages, cart)",
                       f'<div class="bookpilot-shop"></div>\n<script src="{urls["shop_js"]}" defer></script>'))
    if "booking_js" in urls:
        out.insert(0, ("Booking form", f'<div class="bookpilot-booking"></div>\n<script src="{urls["booking_js"]}" defer></script>'))
    if "careers_js" in urls:
        out.insert(0, ("Job application form", f'<div class="bookpilot-form"></div>\n<script src="{urls["careers_js"]}" defer></script>'))
        out.append(("Connect an existing career form", f'<script src="{urls["connect_js"]}" defer></script>'))
    return out


def _plugin_context(request, company):
    kit = svc.kit_for(company)
    caps = svc.capabilities(company)
    ctx = {"company": company.name, "base": request.build_absolute_uri("/").rstrip("/"), "kit_id": kit.public_id,
           "booking_slug": booking_svc.site_for(company).slug if caps["booking"] else "",
           "careers_slug": careers_svc.site_for(company).slug if caps["careers"] else "", "api_key": kit.api_key,
           "color": kit.accent_color or "#0f766e", "lang": site_lang(company)}
    from django.conf import settings
    ctx["languages"] = settings.LANGUAGES
    return ctx


@login_required
@superuser_required
def kit_wp_plugin(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    ctx = _plugin_context(request, company)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bookpilot-connect/bookpilot-connect.php", render_to_string("webapp/website_kit/wp_connect.php.txt", ctx))
        z.writestr("bookpilot-connect/readme.txt", render_to_string("webapp/website_kit/wp_connect_readme.txt", ctx))
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="bookpilot-connect-{ctx["kit_id"]}.zip"'
    return response


@login_required
@superuser_required
def kit_bootstrap_starter(request, company_id):
    """A ready Bootstrap 5 website (home, shop, contact) with the BookPilot widgets in place, to upload to any
    hosting and then change freely."""
    from apps.industry import shop_orders
    company = get_object_or_404(Company, id=company_id)
    kit = svc.kit_for(company)
    pid = kit.public_id
    lang = site_lang(company)
    urls = {"catalogue_js": _abs(request, "webapp:kit_catalogue_js", pid) + f"?lang={lang}",
            "enquiry_js": _abs(request, "webapp:kit_enquiry_js", pid) + f"?lang={lang}"}
    shop = shop_orders.applies(company)
    if shop:
        urls["shop_js"] = _abs(request, "webapp:kit_shop_js", pid) + f"?lang={lang}"
    booking = BookingSite.objects.filter(company=company, enabled=True).first()
    if booking:
        urls["booking_js"] = _abs(request, "webapp:book_form_js", booking.slug) + f"?lang={lang}"
    from django.utils import translation
    ctx = {"name": company.name, "phone": company.phone, "email": company.email, "address": company.address,
           "color": kit.accent_color or "#0f766e", "urls": urls, "shop": shop, "lang": lang,
           "rtl": translation.get_language_info(lang).get("bidi", False) if lang else False, "offers": True}
    folder = f"{pid}-website"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("index.html", "contact.html") + (("shop.html",) if shop else ()):
            z.writestr(f"{folder}/{name}", render_to_string(f"webapp/website_kit/starter/{name}", ctx))
        z.writestr(f"{folder}/assets/style.css", render_to_string("webapp/website_kit/starter/style.css", ctx))
        z.writestr(f"{folder}/README.txt", render_to_string("webapp/website_kit/starter/README.txt", ctx))
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{folder}.zip"'
    return response


@login_required
@superuser_required
def kit_python_client(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    body = render_to_string("webapp/website_kit/bookpilot_client.py.txt", _plugin_context(request, company))
    response = HttpResponse(body, content_type="text/x-python; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="bookpilot_client.py"'
    return response

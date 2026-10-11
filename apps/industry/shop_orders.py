"""
Online shop: a customer adds products to the cart on a shop's website (BookPilot website, the client's own
domain or the WordPress plugin) and sends the order. It arrives in BookPilot's "Website orders" inbox; staff
confirm it, pack or send it, and make the bill (stock goes out then) — or reject it with a reason.
Prices and stock always come from BookPilot, never from the website. Restaurants use their own ordering
(apps.verticals.restaurant.online_orders).
"""
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import ShopOrder, ShopOrderLine, SiteDesign

MAX_LINES = 40
MAX_QTY = 50
FEE_SKU = "DELIVERY-FEE"
OPEN = ("new", "confirmed", "ready")


def applies(company):
    """Shops that sell products. Restaurants have their own ordering; service and booking businesses don't sell a cart."""
    from apps.verticals.restaurant.online_orders import is_restaurant
    from .website_kit import catalogue_kind
    return not is_restaurant(company) and catalogue_kind(company) == "products"


def settings_for(company):
    return SiteDesign.objects.filter(company=company).first()


def config(company):
    """What the website cart needs to know. None when the online shop is off."""
    design = settings_for(company)
    if (not design or design.package != "shop" or not design.shop_enabled or not applies(company)
            or not (design.shop_pickup or design.shop_delivery)):
        return None
    return {"enabled": True, "open": not design.shop_paused, "pickup": design.shop_pickup,
            "delivery": design.shop_delivery, "delivery_fee": f"{design.shop_delivery_fee:.2f}",
            "free_over": f"{design.shop_free_delivery_over:.2f}", "minimum": f"{design.shop_minimum:.2f}",
            "ready_minutes": 0, "note": design.shop_note, "currency": company.default_currency, "shop": True,
            "coupons": design.shop_coupons, "pay_online": online_ready(company) and design.shop_online_payment,
            "terms_url": terms_url(company)}


def online_ready(company):
    from apps.sales import online_pay
    config = online_pay.settings_for(company)
    return bool(config and config.ready)


def terms_url(company):
    """The website's own Terms page, if the owner made one (shown at checkout)."""
    from .models import SitePage
    page = SitePage.objects.filter(company=company, published=True, slug__in=("terms", "terms-and-conditions", "terms-conditions")).first()
    return f"p/{page.slug}/" if page else ""


def price_rules(company):
    """product -> (price, offer name): the walk-in price (price lists, offers, near-expiry), same as the POS."""
    from apps.webapp.views import _price_rules
    rules = _price_rules(company)

    def resolve(product):
        price, offer = rules(product)
        return (product.selling_price if price is None else price), offer
    return resolve


def stock_for(company, products):
    """{product_id: quantity on hand} for stocked products."""
    from apps.inventory.models import StockMovement
    ids = [p.id for p in products if p.is_stock_tracked]
    rows = (StockMovement.objects.for_company(company).filter(product_id__in=ids)
            .values("product_id").annotate(q=Sum("quantity")))
    return {r["product_id"]: r["q"] or 0 for r in rows}


def sellable(company):
    """Products the website can sell: active, and not the parent of variants (each size / colour is sold)."""
    from apps.inventory.models import Product
    return (Product.objects.for_company(company).filter(is_active=True, variants__isnull=True)
            .exclude(sku__in=[FEE_SKU]).distinct())


def delivery_fee(design, subtotal):
    fee = design.shop_delivery_fee or Decimal("0")
    if design.shop_free_delivery_over and subtotal >= design.shop_free_delivery_over:
        return Decimal("0")
    return fee


def _clean_phone(value):
    phone = re.sub(r"[^\d+ ]", "", str(value or "")).strip()[:30]
    if len(re.sub(r"\D", "", phone)) < 7:
        raise ValidationError(_("Enter a phone number we can call."))
    return phone


def _number(company):
    from apps.tenants.services import next_counter_value
    return f"WEB-{next_counter_value(company, 'shop_order'):05d}"


@transaction.atomic
def place(company, data, source=""):
    """data: {name, phone, email, mode, address, note, items: [{id, qty}]} → ShopOrder."""
    from apps.customers.models import Customer
    cfg = config(company)
    if not cfg:
        raise ValidationError(_("Online ordering is switched off."))
    if not cfg["open"]:
        raise ValidationError(_("Sorry, we are not taking online orders right now. Please call us."))
    design = settings_for(company)
    name = str(data.get("name") or "").strip()[:150]
    if len(name) < 2:
        raise ValidationError(_("Enter your name."))
    phone = _clean_phone(data.get("phone"))
    email = str(data.get("email") or "").strip()[:254]
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        email = ""
    mode = data.get("mode") if data.get("mode") in ("pickup", "delivery") else ("pickup" if design.shop_pickup else "delivery")
    if (mode == "pickup" and not design.shop_pickup) or (mode == "delivery" and not design.shop_delivery):
        raise ValidationError(_("This order type is not available."))
    address = str(data.get("address") or "").strip()[:500]
    if mode == "delivery" and len(address) < 5:
        raise ValidationError(_("Enter the delivery address."))
    note = str(data.get("note") or "").strip()[:255]

    rows = data.get("items") or []
    if not isinstance(rows, list) or not rows:
        raise ValidationError(_("Your cart is empty."))
    if len(rows) > MAX_LINES:
        raise ValidationError(_("Too many items in one order. Please call us for big orders."))
    wanted = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError(_("Your cart is not valid. Please refresh the page."))
        try:
            pid, qty = int(row.get("id")), int(row.get("qty", 1))
        except (TypeError, ValueError):
            raise ValidationError(_("Your cart is not valid. Please refresh the page."))
        if qty < 1 or qty > MAX_QTY:
            raise ValidationError(_("You can order 1 to %(n)s of each item.") % {"n": MAX_QTY})
        wanted[pid] = wanted.get(pid, 0) + qty
    products = {p.id: p for p in sellable(company).filter(id__in=wanted)}
    stock = stock_for(company, products.values())
    priced = price_rules(company)
    prices = {}
    subtotal = Decimal("0")
    for pid, qty in wanted.items():
        product = products.get(pid)
        if product is None:
            raise ValidationError(_("An item in your cart is no longer sold online. Please refresh the page."))
        if product.is_stock_tracked:
            have = int(stock.get(pid, 0))
            if have <= 0:
                raise ValidationError(_("Sorry, %(item)s is out of stock.") % {"item": product.name})
            if qty > have:
                raise ValidationError(_("Only %(n)s of %(item)s left.") % {"n": have, "item": product.name})
        prices[pid] = priced(product)[0]
        subtotal += prices[pid] * qty
    if mode == "delivery" and design.shop_minimum and subtotal < design.shop_minimum:
        raise ValidationError(_("The minimum order for delivery is %(amount)s.") % {"amount": f"{company.default_currency} {design.shop_minimum:.2f}"})
    fee = delivery_fee(design, subtotal) if mode == "delivery" else Decimal("0")
    code, discount = str(data.get("coupon") or "").strip()[:30], Decimal("0")
    if code and design.shop_coupons:
        from apps.sales.services import validate_coupon
        try:
            _coupon, discount = validate_coupon(company=company, code=code, subtotal=subtotal, date=timezone.localdate())
        except ValidationError:
            raise ValidationError(_("This coupon code is not valid."))
    else:
        code = ""
    pay_online = data.get("payment") == "online" and cfg.get("pay_online")

    customer = Customer.objects.for_company(company).filter(phone=phone).first()
    if not customer:
        customer = Customer.objects.create(company=company, name=name, phone=phone, email=email,
                                           address=address if mode == "delivery" else "")
    order = ShopOrder.objects.create(
        company=company, number=_number(company), mode=mode, customer=customer, customer_name=name, phone=phone,
        email=email, address=address if mode == "delivery" else "", note=note, source=source[:120],
        subtotal=subtotal, delivery_fee=fee, coupon_code=code, discount=discount, total=subtotal + fee - discount,
        payment_method="online" if pay_online else "cod")
    for pid, qty in wanted.items():
        p = products[pid]
        label = f"{p.name} — {p.variant_label}" if p.variant_label else p.name
        ShopOrderLine.objects.create(order=order, product=p, name=label[:255], quantity=qty, unit_price=prices[pid],
                                     line_total=prices[pid] * qty)
    if pay_online:  # the bill is made now so the customer pays it online; stock goes out with it
        _bill(order, _owner(company))
    _tell_staff(order)
    _email_customer(order)
    return order


def _owner(company):
    m = (company.memberships.filter(is_active=True, role__name="Owner").select_related("user").first()
         or company.memberships.select_related("user").first())
    return m.user if m else None


def pay_url(order, absolute):
    """Where the customer pays an online order: the invoice page with its Pay-now button."""
    if not order.invoice_id:
        return ""
    from django.urls import reverse
    from apps.sales import sharing
    return absolute(reverse("webapp:public_invoice", args=[sharing.share_token(order.invoice)]))


def _email_customer(order):
    """A copy of the order to the customer's email (when given and email is set up)."""
    if not order.email:
        return
    try:
        from django.conf import settings
        from django.core.mail import send_mail
        from apps.notifications.services import email_configured
        if not email_configured():
            return
        lines = "\n".join(f"{l.quantity} x {l.name} — {order.company.default_currency} {l.line_total:.2f}" for l in order.lines.all())
        body = _("Thank you for your order %(ref)s at %(shop)s.") % {"ref": order.number, "shop": order.company.name}
        body += f"\n\n{lines}\n"
        if order.delivery_fee:
            body += f"{_('Delivery')}: {order.delivery_fee:.2f}\n"
        if order.discount:
            body += f"{_('Discount')}: -{order.discount:.2f}\n"
        body += f"{_('Total')}: {order.company.default_currency} {order.total:.2f}\n\n{order.company.phone or ''}"
        send_mail(_("Your order %(ref)s — %(shop)s") % {"ref": order.number, "shop": order.company.name}, body,
                  getattr(settings, "DEFAULT_FROM_EMAIL", None), [order.email], fail_silently=True)
    except Exception:  # never lose an order over an email
        pass


def _tell_staff(order):
    try:
        from apps.notifications.services import notify
        notify(company=order.company, title=f"New website order {order.number}",
               message=f"{order.customer_name} · {order.phone} · {order.get_mode_display()} · "
                       f"{order.company.default_currency} {order.total:.2f}",
               idempotency_key=f"shop-order:{order.pk}")
    except Exception:  # a mail problem must never lose the order
        pass


def _lock(order, allowed):
    order = ShopOrder.objects.select_for_update().get(pk=order.pk)  # double taps
    if order.status not in allowed:
        raise ValidationError(_("This order was already handled."))
    return order


@transaction.atomic
def confirm(order, user):
    order = _lock(order, ("new",))
    order.status, order.handled_by, order.handled_at = "confirmed", user, timezone.now()
    order.save(update_fields=["status", "handled_by", "handled_at"])
    return order


@transaction.atomic
def mark_ready(order, user):
    order = _lock(order, ("new", "confirmed"))
    order.status = "ready"
    if not order.handled_by_id:
        order.handled_by, order.handled_at = user, timezone.now()
    order.save(update_fields=["status", "handled_by", "handled_at"])
    return order


@transaction.atomic
def make_bill(order, user, warehouse=None):
    """Creates the sales invoice (stock goes out now) and closes the order. Payment is taken at pickup / delivery.
    An order paid online already has its bill: this only closes it."""
    order = _lock(order, OPEN)
    if not order.invoice_id:
        order = _bill(order, user, warehouse)
    order.status = "done"
    if not order.handled_by_id:
        order.handled_by, order.handled_at = user, timezone.now()
    order.save(update_fields=["status", "handled_by", "handled_at"])
    return order


def _bill(order, user, warehouse=None):
    from apps.industry.common import default_warehouse, service_product
    from apps.sales.services import create_invoice
    lines = [{"product": l.product, "quantity": Decimal(l.quantity), "unit_price": l.unit_price}
             for l in order.lines.select_related("product")]
    if order.delivery_fee:
        lines.append({"product": service_product(order.company, FEE_SKU, "Delivery charge"),
                      "quantity": Decimal("1"), "unit_price": order.delivery_fee})
    try:
        invoice = create_invoice(company=order.company, user=user, customer=order.customer, date=timezone.localdate(),
                                 warehouse=warehouse or default_warehouse(order.company), lines=lines,
                                 discount_amount=order.discount, coupon_code=order.coupon_code)
    except ValueError as exc:  # e.g. a phone that needs its IMEI picked, or stock that ran out
        raise ValidationError(str(exc))
    if order.coupon_code:
        from apps.sales.models import Coupon
        from apps.sales.services import redeem_coupon_usage
        coupon = Coupon.objects.for_company(order.company).filter(code__iexact=order.coupon_code).first()
        if coupon:
            redeem_coupon_usage(coupon)
    order.invoice = invoice
    order.save(update_fields=["invoice"])
    return order


@transaction.atomic
def reject(order, user, reason, status="rejected"):
    order = _lock(order, OPEN)
    order.status = status
    order.reject_reason = (reason or "").strip()[:255] or _("The shop could not take this order.")
    order.handled_by, order.handled_at = user, timezone.now()
    order.save(update_fields=["status", "reject_reason", "handled_by", "handled_at"])
    return order


def waiting_count(company):
    return ShopOrder.objects.for_company(company).filter(status="new").count()


def stage(order):
    """What the customer sees: new → confirmed → ready → done (or rejected / cancelled)."""
    return order.status


def whatsapp_text(order):
    shop = order.company.name
    if order.status == "new":
        return _("Hi %(name)s, we received your order %(ref)s at %(shop)s. We will confirm it shortly.") % {
            "name": order.customer_name, "ref": order.number, "shop": shop}
    if order.status == "confirmed":
        return _("Hi %(name)s, your order %(ref)s at %(shop)s is confirmed. Total %(total)s.") % {
            "name": order.customer_name, "ref": order.number, "shop": shop,
            "total": f"{order.company.default_currency} {order.total:.2f}"}
    if order.status == "ready":
        if order.mode == "delivery":
            return _("Hi %(name)s, your order %(ref)s from %(shop)s is on the way.") % {
                "name": order.customer_name, "ref": order.number, "shop": shop}
        return _("Hi %(name)s, your order %(ref)s is ready for pickup at %(shop)s.") % {
            "name": order.customer_name, "ref": order.number, "shop": shop}
    if order.status in ("rejected", "cancelled"):
        return _("Hi %(name)s, sorry — we could not complete your order %(ref)s at %(shop)s. %(reason)s") % {
            "name": order.customer_name, "ref": order.number, "shop": shop, "reason": order.reject_reason}
    return _("Hi %(name)s, thank you for shopping at %(shop)s!") % {"name": order.customer_name, "shop": shop}

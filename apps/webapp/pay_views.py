"""Customers paying online: the Pay-now button on shared invoices, the customer portal
(bills, statement, pay the balance) and the owner's payment-gateway settings."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.sales import online_pay, sharing
from apps.sales.allocation import invoice_due, open_invoices
from apps.sales.models import CustomerPayment, SalesInvoice, OnlinePayment, OnlinePaymentSettings
from apps.tenants.models import Company

from .receivables_views import _balances, _statement
from .views import require_permission

COMPANY_SALT = "bookpilot.pay-company"
PAYMENT_SALT = "bookpilot.pay-attempt"


def company_token(company):
    return signing.Signer(salt=COMPANY_SALT).sign(str(company.id))


def _company_from_token(token):
    try:
        return Company.objects.filter(id=int(signing.Signer(salt=COMPANY_SALT).unsign(token))).first()
    except (signing.BadSignature, ValueError):
        return None


def portal_url(request, customer):
    return request.build_absolute_uri(reverse("webapp:customer_portal", args=[online_pay.portal_token(customer)]))


def _return_url(request, company, payment):
    url = reverse("webapp:pay_return", args=[company_token(company)])
    return request.build_absolute_uri(f"{url}?p={signing.dumps(payment.id, salt=PAYMENT_SALT)}")


def _public(response):
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _status_message(request):
    status = request.GET.get("paid")
    if status == "1":
        return {"message": _("Payment received — thank you!"), "level": "ok"}
    if status == "0":
        return {"message": _("The payment was not completed. No money was taken."), "level": "warn"}
    if status == "wait":
        return {"message": _("Your payment is being confirmed. Refresh this page in a minute."), "level": "warn"}
    return {}


# ------------------------------------------------------------------ public invoice page

@xframe_options_sameorigin
def public_invoice(request, token):
    """Customer-facing invoice page; no login, protected by the signed token."""
    invoice = sharing.invoice_from_token(token)
    if invoice is None:
        raise Http404("This invoice link is invalid or has expired.")
    if request.GET.get("format") == "pdf":
        pdf = sharing.render_invoice_pdf(invoice)
        if pdf:
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}.pdf"'
            return response
    config = online_pay.settings_for(invoice.company)
    pay = _status_message(request)
    due = invoice_due(invoice) if invoice.status not in ("paid", "void") else 0
    if config and (config.ready or config.instructions.strip()):
        pay.update({"amount": due, "currency": invoice.currency, "online": config.ready,
                    "instructions": config.instructions.strip(),
                    "action": reverse("webapp:pay_invoice", args=[token])})
    if config and config.portal_enabled:
        pay["portal_url"] = reverse("webapp:customer_portal", args=[online_pay.portal_token(invoice.customer)])
    public_url = request.build_absolute_uri(request.path)
    return _public(HttpResponse(sharing.render_invoice_html(invoice, public_url=public_url, pay=pay or None)))


@csrf_exempt  # a public page opened from WhatsApp/email; the signed token is the protection
@require_POST
def pay_invoice(request, token):
    invoice = sharing.invoice_from_token(token)
    if invoice is None:
        raise Http404
    back = reverse("webapp:public_invoice", args=[token])
    due = invoice_due(invoice) if invoice.status not in ("paid", "void") else 0
    if due <= 0:
        return redirect(back)
    return _start(request, invoice.company, invoice.customer, due, invoice, back)


def _start(request, company, customer, amount, invoice, back):
    try:
        _payment, url = online_pay.start(company=company, customer=customer, amount=amount, invoice=invoice,
                                         return_url_for=lambda payment: _return_url(request, company, payment))
    except online_pay.PaymentError:
        return redirect(f"{back}?paid=0")
    return redirect(url)


# ------------------------------------------------------------------ gateway return + webhook

def pay_return(request, company_token_value):
    company = _company_from_token(company_token_value)
    if company is None:
        raise Http404
    payment = None
    signed = request.GET.get("p")
    if signed:
        try:
            payment = OnlinePayment._base_manager.filter(company=company, id=signing.loads(signed, salt=PAYMENT_SALT)).first()
        except signing.BadSignature:
            payment = None
    if payment is None:  # SkipCash returns ?id=<payment id>&transId=<our transaction id>
        gateway_id = request.GET.get("id") or request.GET.get("paymentId") or ""
        trans = request.GET.get("transId") or request.GET.get("transactionId") or ""
        qs = OnlinePayment._base_manager.filter(company=company)
        payment = (qs.filter(gateway_payment_id=gateway_id).first() if gateway_id else None) or \
                  (qs.filter(transaction_id=trans).first() if trans else None)
    if payment is None:
        raise Http404
    payment = online_pay.settle(payment)
    flag = {"paid": "1", "failed": "0"}.get(payment.status, "wait")
    if payment.invoice_id:
        back = reverse("webapp:public_invoice", args=[sharing.share_token(payment.invoice)])
    else:
        back = reverse("webapp:customer_portal", args=[online_pay.portal_token(payment.customer)])
    return redirect(f"{back}?paid={flag}")


@csrf_exempt
@require_POST
def pay_webhook(request, company_token_value):
    company = _company_from_token(company_token_value)
    if company is None:
        return HttpResponse(status=404)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=400)
    signature = request.META.get("HTTP_AUTHORIZATION") or request.META.get("HTTP_X_SIGNATURE") or ""
    payment = online_pay.settle_skipcash_webhook(company, payload, signature)
    if payment is None:
        return HttpResponse(status=401)
    return JsonResponse({"received": True, "status": payment.status})


# ------------------------------------------------------------------ customer portal

@xframe_options_sameorigin
def customer_portal(request, token):
    customer = online_pay.customer_from_portal_token(token)
    if customer is None:
        raise Http404("This link is invalid or has expired.")
    company = customer.company
    config = online_pay.settings_for(company)
    if config and not config.portal_enabled:
        raise Http404("This link is no longer active.")
    _opening, lines, closing = _statement(company, customer)
    lines = lines[-60:]
    for line in lines:
        if line["invoice"]:
            line["link"] = reverse("webapp:public_invoice", args=[sharing.share_token(line["invoice"])])
    invoices = open_invoices(company, customer)
    for inv in invoices:
        inv.link = reverse("webapp:public_invoice", args=[sharing.share_token(inv)])
    balance = _balances(company).get(customer.id, 0)
    recent = (SalesInvoice.objects.for_company(company).filter(customer=customer)
              .order_by("-date", "-id")[:30])
    for inv in recent:
        inv.link = reverse("webapp:public_invoice", args=[sharing.share_token(inv)])
    return _public(render(request, "webapp/pay/portal.html", {
        "company": company, "customer": customer, "lines": lines, "closing": closing, "balance": balance,
        "open_invoices": invoices, "recent": recent, "status": _status_message(request),
        "online": bool(config and config.ready), "instructions": (config.instructions.strip() if config else ""),
        "pay_action": reverse("webapp:portal_pay", args=[token]), "today": timezone.localdate(),
        "paid_total": CustomerPayment.objects.for_company(company).filter(customer=customer).aggregate(t=Sum("amount"))["t"] or 0,
    }))


@csrf_exempt  # public page; the signed token is the protection
@require_POST
def portal_pay(request, token):
    customer = online_pay.customer_from_portal_token(token)
    if customer is None:
        raise Http404
    back = reverse("webapp:customer_portal", args=[token])
    balance = _balances(customer.company).get(customer.id, 0)
    if balance <= 0:
        return redirect(back)
    return _start(request, customer.company, customer, balance, None, back)


# ------------------------------------------------------------------ owner settings

@login_required
@require_permission("banking.manage")
def online_payment_settings(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    config = OnlinePaymentSettings.load(company)
    is_owner = getattr(request.role, "name", None) == "Owner"
    if request.method == "POST":
        if not is_owner:
            messages.error(request, _("Only the business owner can change payment settings."))
            return redirect("webapp:online_payment_settings")
        provider = request.POST.get("provider") or ""
        config.provider = provider if provider in dict(OnlinePaymentSettings.PROVIDERS) else ""
        config.test_mode = bool(request.POST.get("test_mode"))
        config.key_id = (request.POST.get("key_id") or "").strip()[:255]
        config.client_id = (request.POST.get("client_id") or "").strip()[:255]
        for field in ("secret", "webhook_key"):
            value = (request.POST.get(field) or "").strip()
            if value:  # blank keeps the saved secret
                config.set_secret(field, value)
        config.deposit_to = "cash" if request.POST.get("deposit_to") == "cash" else "bank"
        config.instructions = (request.POST.get("instructions") or "").strip()[:2000]
        config.portal_enabled = bool(request.POST.get("portal_enabled"))
        config.save()
        if config.provider and not config.ready:
            messages.warning(request, _("Saved, but some keys are missing — the Pay now button stays hidden until they are filled in."))
        else:
            messages.success(request, _("Payment settings saved."))
        return redirect("webapp:online_payment_settings")
    token = company_token(company)
    return render(request, "webapp/pay/settings.html", {
        "config": config, "is_owner": is_owner, "providers": OnlinePaymentSettings.PROVIDERS,
        "return_url": request.build_absolute_uri(reverse("webapp:pay_return", args=[token])),
        "webhook_url": request.build_absolute_uri(reverse("webapp:pay_webhook", args=[token])),
        "payments": OnlinePayment.objects.for_company(company).select_related("customer", "invoice")[:40],
    })

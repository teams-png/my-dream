"""Platform admin: client billing — expiry dates, invoices, payments and money owed per client."""
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.subscriptions import billing
from apps.subscriptions.models import Subscription, SubscriptionInvoice
from apps.tenants.models import Company
from apps.common.ids import pick_id

from .guide_views import support_details
from .views import superuser_required

SHOW = [("all", "All clients"), ("expiring", "Expiring in 30 days"), ("expired", "Expired"), ("trial", "On trial"),
        ("unpaid", "Unpaid invoices"), ("paying", "Paying clients")]


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        raise ValidationError("Enter a valid date.")


@login_required
@superuser_required
def platform_billing(request):
    show = request.GET.get("show") if request.GET.get("show") in dict(SHOW) else "all"
    q = (request.GET.get("q") or "").strip()
    return render(request, "webapp/platform_admin/billing.html", {
        "rows": billing.overview(show=show, q=q), "totals": billing.totals(), "show": show, "q": q, "tabs": SHOW,
        "expiring_days": billing.EXPIRING_DAYS,
    })


@login_required
@superuser_required
def platform_billing_client(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    sub = Subscription.objects.select_related("plan").filter(company=company).first()
    if sub is None:
        messages.error(request, "This client has no subscription yet.")
        return redirect("webapp:platform_billing")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "issue":
                inv = billing.issue_invoice(sub, user=request.user, amount=request.POST.get("amount"),
                                            due_on=_date(request.POST.get("due_on")), notes=request.POST.get("notes", ""))
                messages.success(request, f"Invoice {inv.number} is ready. Print it or send it on WhatsApp.")
            elif action == "pay":
                invoice = None
                if request.POST.get("invoice"):
                    invoice = get_object_or_404(SubscriptionInvoice, subscription=sub, id=pick_id(request.POST.get("invoice")))
                billing.record_payment(sub, amount=request.POST.get("amount"), method=request.POST.get("method", "bank"),
                                       reference=request.POST.get("reference", ""), paid_on=_date(request.POST.get("paid_on")),
                                       invoice=invoice, user=request.user)
                sub.refresh_from_db()
                messages.success(request, f"Payment recorded. The subscription now runs until {sub.end_date:%d %b %Y}.")
            elif action == "void":
                billing.void_invoice(get_object_or_404(SubscriptionInvoice, subscription=sub, id=pick_id(request.POST.get("invoice"))))
                messages.success(request, "Invoice cancelled.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("webapp:platform_billing_client", company.id)

    invoices = list(sub.invoices.select_related("payment"))
    open_invoices = [i for i in invoices if i.status == "unpaid"]
    start, end = billing.next_period(sub)
    app_url = request.build_absolute_uri("/billing/")
    return render(request, "webapp/platform_admin/billing_client.html", {
        "company": company, "sub": sub, "days": (sub.end_date - date.today()).days,
        "invoices": invoices, "open_invoices": open_invoices,
        "payments": sub.payments.select_related("invoice").order_by("-paid_on", "-id"),
        "renewals": sub.renewals.order_by("-renewed_at")[:12],
        "price": billing.price(sub), "next_start": start, "next_end": end, "methods": billing.METHODS,
        "reminder": billing.reminder_link(sub, open_invoices[0] if open_invoices else None, app_url),
        "paid_total": sum((p.amount for p in sub.payments.filter(is_confirmed=True)), 0),
        "unpaid_total": sum((i.amount for i in open_invoices), 0), "today": date.today(),
    })


def _invoice_page(request, invoice):
    sub = invoice.subscription
    return render(request, "webapp/platform_admin/billing_invoice.html", {
        "inv": invoice, "sub": sub, "client": sub.company, "seller": support_details(),
        "brand": getattr(settings, "LEGAL_COMPANY_NAME", "") or "BookPilot",
    })


@login_required
@superuser_required
def platform_billing_invoice(request, invoice_id):
    return _invoice_page(request, get_object_or_404(SubscriptionInvoice.objects.select_related("subscription__company", "payment"),
                                                    id=invoice_id))


@login_required
def client_billing_invoice(request, invoice_id):
    """A client's own BookPilot invoice (owner only)."""
    company = getattr(request, "company", None)
    if company is None or getattr(request.role, "name", None) != "Owner":
        raise Http404
    invoice = get_object_or_404(SubscriptionInvoice.objects.select_related("subscription__company", "payment"),
                                id=invoice_id, subscription__company=company)
    if invoice.status == "void":
        raise Http404
    return _invoice_page(request, invoice)

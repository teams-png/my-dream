"""Money customers owe: who owes what (with ageing), customer accounts and statements,
receiving payments against credit invoices, reminders and follow-up notes."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.collections import services as collections
from apps.collections.models import CollectionNote
from apps.customers.models import Customer
from apps.sales import services as sales
from apps.sales.online_pay import portal_token
from apps.sales.allocation import allocate_payment, invoice_due, open_invoices
from apps.sales.models import CustomerPayment, SalesInvoice, SalesReturn

from . import xlsx
from .views import require_permission

PERMISSION = "sales.view_invoice"
RECEIVE = "sales.create_invoice"
ZERO = Decimal("0")
CENT = Decimal("0.01")
METHODS = [("cash", "Cash"), ("card", "Card"), ("bank", "Bank transfer"), ("cheque", "Cheque")]


_due = invoice_due
_open_invoices = open_invoices


def _balances(company):
    """{customer_id: balance in company currency} from invoices, payments, store-credit returns and opening balances."""
    balances = {}
    for cid, total in (SalesInvoice.objects.for_company(company).values_list("customer_id")
                       .annotate(t=Sum("total"))):
        balances[cid] = balances.get(cid, ZERO) + (total or ZERO)
    for cid, total in CustomerPayment.objects.for_company(company).values_list("customer_id").annotate(t=Sum("amount")):
        balances[cid] = balances.get(cid, ZERO) - (total or ZERO)
    for cid, total in (SalesReturn.objects.for_company(company).filter(refund_method="store_credit")
                       .values_list("invoice__customer_id").annotate(t=Sum("total"))):
        balances[cid] = balances.get(cid, ZERO) - (total or ZERO)
    for cid, opening in Customer.objects.for_company(company).exclude(opening_balance=0).values_list("id", "opening_balance"):
        balances[cid] = balances.get(cid, ZERO) + opening
    return balances


def _statement(company, customer, start=None, end=None):
    """Chronological lines with a running balance. Returns (opening, lines, closing)."""
    events = []
    for inv in SalesInvoice.objects.for_company(company).filter(customer=customer):
        events.append((inv.date, 0, inv.id, _("Invoice"), inv.invoice_number, inv.total, ZERO, inv))
    for pay in CustomerPayment.objects.for_company(company).filter(customer=customer).select_related("invoice"):
        ref = pay.invoice.invoice_number if pay.invoice_id else _("On account")
        events.append((pay.date, 1, pay.id, _("Payment") + f" ({pay.method})", ref, ZERO, pay.amount, None))
    for ret in SalesReturn.objects.for_company(company).filter(invoice__customer=customer, refund_method="store_credit").select_related("invoice"):
        events.append((ret.date, 2, ret.id, _("Return (credit)"), ret.invoice.invoice_number, ZERO, ret.total, None))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    opening = customer.opening_balance or ZERO
    lines, running = [], opening
    for day, _k, _id, kind, ref, debit, credit, invoice in events:
        running += debit - credit
        if start and day < start:
            opening = running
            continue
        if end and day > end:
            continue
        lines.append({"date": day, "kind": kind, "ref": ref, "debit": debit, "credit": credit, "balance": running,
                      "invoice": invoice})
    closing = lines[-1]["balance"] if lines else opening
    return opening, lines, closing


def _reminder_link(company, customer, balance, invoices, portal=""):
    currency = getattr(company, "default_currency", "")
    lines = [_("Dear %(name)s,") % {"name": customer.name},
             _("This is a friendly reminder from %(company)s.") % {"company": company.name},
             _("Amount due: %(cur)s %(amount)s") % {"cur": currency, "amount": f"{balance:.2f}"}]
    for inv in invoices[:6]:
        lines.append(f"• {inv.invoice_number} ({inv.date:%d %b}): {inv.currency} {inv.due:.2f}")
    if portal:
        lines.append(_("View your bills and pay online: %(url)s") % {"url": portal})
    lines.append(_("Thank you."))
    phone = "".join(ch for ch in (customer.phone or "") if ch.isdigit())
    return f"https://wa.me/{phone}?text={quote(chr(10).join(lines))}"


# ------------------------------------------------------------------ overview

@login_required
@require_permission(PERMISSION)
def receivables(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    collections.seed_default_ageing_buckets(company)
    summary = collections.ar_ageing_summary(company)
    detail = collections.ar_ageing_detail(company)
    today = timezone.localdate()
    per_customer = {}
    for row in detail:
        entry = per_customer.setdefault(row["party"].id, {"customer": row["party"], "outstanding": ZERO, "overdue": ZERO,
                                                          "oldest": None, "count": 0})
        entry["outstanding"] += row["outstanding"]
        entry["count"] += 1
        if row["days_overdue"]:
            entry["overdue"] += row["outstanding"]
            entry["oldest"] = max(entry["oldest"] or 0, row["days_overdue"])
    balances = _balances(company)
    query = (request.GET.get("q") or "").strip()
    rows = list(per_customer.values())
    # customers with an opening balance or on-account credit but no open invoice
    for cid, balance in balances.items():
        if cid not in per_customer and balance:
            customer = Customer.objects.for_company(company).filter(id=cid).first()
            if customer:
                rows.append({"customer": customer, "outstanding": ZERO, "overdue": ZERO, "oldest": None, "count": 0})
    for row in rows:
        row["balance"] = balances.get(row["customer"].id, row["outstanding"])
    if query:
        rows = [r for r in rows if query.lower() in r["customer"].name.lower() or query in (r["customer"].phone or "")]
    show = request.GET.get("show", "owing")
    if show == "overdue":
        rows = [r for r in rows if r["overdue"] > 0]
    elif show == "credit":
        rows = [r for r in rows if r["balance"] < 0]
    else:
        rows = [r for r in rows if r["balance"] > 0 or r["outstanding"] > 0]
    rows.sort(key=lambda r: (-(r["overdue"]), -(r["balance"])))
    if xlsx.wants(request):
        data = [[_("Customer"), _("Phone"), _("Open bills"), _("Outstanding"), _("Overdue"), _("Oldest (days overdue)"), _("Balance")]]
        data += [[r["customer"].name, r["customer"].phone, r["count"], r["outstanding"], r["overdue"], r["oldest"], r["balance"]]
                 for r in rows]
        return xlsx.response(f"receivables-{today}", [(_("Receivables"), data)])
    overdue_total = sum((b["total"] for b in summary["buckets"]), ZERO) + summary["unbucketed_overdue"]
    notes_due = (CollectionNote.objects.for_company(company).filter(party_type="customer", follow_up_date__lte=today)
                 .select_related("customer").order_by("follow_up_date")[:10])
    return render(request, "webapp/receivables/home.html", {
        "summary": summary, "rows": rows, "q": query, "show": show, "overdue_total": overdue_total,
        "notes_due": notes_due, "today": today,
        "received_month": CustomerPayment.objects.for_company(company).filter(
            date__year=today.year, date__month=today.month).aggregate(t=Sum("amount"))["t"] or ZERO,
    })


# ------------------------------------------------------------------ customer account

@login_required
@require_permission(PERMISSION)
def customer_account(request, customer_id):
    company = request.company
    customer = get_object_or_404(Customer.objects.for_company(company), id=customer_id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "note":
            text = (request.POST.get("note") or "").strip()
            if text:
                collections.record_collection_note(
                    company=company, user=request.user, party_type="customer", note=text[:2000], customer=customer,
                    follow_up_date=parse_date(request.POST.get("follow_up") or "") or None)
                messages.success(request, _("Note saved."))
        elif action == "credit_limit":
            try:
                customer.credit_limit = max(Decimal(request.POST.get("credit_limit") or "0"), ZERO)
                customer.payment_terms_days = max(int(request.POST.get("terms") or 0), 0)
                customer.save(update_fields=["credit_limit", "payment_terms_days"])
                messages.success(request, _("Credit settings saved."))
            except (InvalidOperation, ValueError):
                messages.error(request, _("Enter valid numbers."))
        return redirect("webapp:customer_account", customer.id)
    start = parse_date(request.GET.get("from") or "")
    end = parse_date(request.GET.get("to") or "")
    opening, lines, closing = _statement(company, customer, start, end)
    open_invoices = _open_invoices(company, customer)
    balance = _balances(company).get(customer.id, ZERO)
    if xlsx.wants(request):
        data = [[company.name, customer.name, _("Statement")],
                [_("Date"), _("Type"), _("Reference"), _("Billed"), _("Paid"), _("Balance")],
                [start, _("Opening balance"), "", None, None, opening]]
        data += [[l["date"], str(l["kind"]), l["ref"], l["debit"] or None, l["credit"] or None, l["balance"]] for l in lines]
        return xlsx.response(f"statement-{customer.name}", [(_("Statement"), data, 2)])
    credit = collections.customer_credit_status(company, customer)
    portal = request.build_absolute_uri(reverse("webapp:customer_portal", args=[portal_token(customer)]))
    return render(request, "webapp/receivables/customer.html", {
        "customer": customer, "opening": opening, "lines": lines, "closing": closing, "start": start, "end": end,
        "open_invoices": open_invoices, "balance": balance, "credit": credit, "methods": METHODS,
        "today": timezone.localdate(), "portal": portal,
        "reminder": _reminder_link(company, customer, balance, open_invoices, portal),
        "notes": CollectionNote.objects.for_company(company).filter(customer=customer).select_related("created_by")
        .order_by("-created_at")[:20],
        "payments": CustomerPayment.objects.for_company(company).filter(customer=customer).select_related("invoice")
        .order_by("-date", "-id")[:15],
        "statement_only": request.GET.get("print") == "1",
    })


@login_required
@require_permission(RECEIVE)
def receive_payment(request, customer_id):
    """Allocates a payment to the oldest open invoices first (or to one chosen invoice); anything left
    over is kept as an advance on the customer's account."""
    company = request.company
    customer = get_object_or_404(Customer.objects.for_company(company), id=customer_id)
    if request.method != "POST":
        return redirect("webapp:customer_account", customer.id)
    try:
        amount = Decimal(request.POST.get("amount") or "0").quantize(CENT)
    except InvalidOperation:
        amount = ZERO
    day = parse_date(request.POST.get("date") or "") or timezone.localdate()
    method = request.POST.get("method") if request.POST.get("method") in dict(METHODS) else "cash"
    ledger_method = "cash" if method == "cash" else method
    if amount <= 0:
        messages.error(request, _("Enter the amount received."))
        return redirect("webapp:customer_account", customer.id)
    try:
        with transaction.atomic():
            receipts, left = allocate_payment(company=company, user=request.user, customer=customer, amount=amount,
                                              date=day, method=ledger_method, invoice_id=request.POST.get("invoice"))
    except (ValidationError, KeyError) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("webapp:customer_account", customer.id)
    text = _("Payment of %(amount)s received from %(name)s.") % {"amount": f"{amount:.2f}", "name": customer.name}
    if receipts:
        text += " " + _("Applied to: %(list)s.") % {"list": ", ".join(receipts)}
    if left > 0:
        text += " " + _("%(amount)s kept as advance on account.") % {"amount": f"{left:.2f}"}
    messages.success(request, text)
    return redirect("webapp:customer_account", customer.id)

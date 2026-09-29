"""
Share invoices with customers: signed public links, WhatsApp and email.

A share link carries a signed token (company + invoice id), so customers can
open their invoice without an account while nobody can guess other invoices.
"""
import re

from django.core import signing
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from .models import SalesInvoice, SalesInvoiceLine

SHARE_SALT = "bookpilot.invoice-share"
SHARE_MAX_AGE = 60 * 60 * 24 * 180  # links stay valid for about six months

COUNTRY_DIAL_CODES = {
    "qatar": "974", "india": "91", "uae": "971", "united arab emirates": "971",
    "saudi arabia": "966", "ksa": "966", "oman": "968", "kuwait": "965", "bahrain": "973",
    "united kingdom": "44", "uk": "44", "united states": "1", "usa": "1",
    "pakistan": "92", "bangladesh": "880", "sri lanka": "94", "nepal": "977", "egypt": "20",
}


def share_token(invoice):
    return signing.dumps({"i": invoice.id, "c": invoice.company_id}, salt=SHARE_SALT, compress=True)


def invoice_from_token(token):
    """Returns the invoice for a valid token, or None (expired, tampered or deleted)."""
    try:
        data = signing.loads(token, salt=SHARE_SALT, max_age=SHARE_MAX_AGE)
    except signing.BadSignature:
        return None
    return (SalesInvoice._base_manager.select_related("customer", "company")
            .filter(id=data.get("i"), company_id=data.get("c")).first())


def render_invoice_html(invoice, *, public_url=""):
    lines = SalesInvoiceLine.objects.filter(invoice=invoice).select_related("product")
    return render_to_string("webapp/invoice_pdf.html", {
        "company": invoice.company, "invoice": invoice, "lines": lines,
        "mobile_units": invoice.mobile_units.select_related("product").all(),
        "balance_due": invoice.total - invoice.amount_paid,
        "public_url": public_url,
    })


def render_invoice_pdf(invoice):
    """PDF bytes, or None when WeasyPrint (or its system libraries) is unavailable."""
    try:
        from weasyprint import HTML
        return HTML(string=render_invoice_html(invoice)).write_pdf()
    except Exception:
        return None


def normalise_phone(phone, country=""):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if (phone or "").strip().startswith("+") or digits.startswith("00"):
        return digits[2:] if digits.startswith("00") else digits
    code = COUNTRY_DIAL_CODES.get((country or "").strip().lower(), "")
    if code and not digits.startswith(code):
        digits = code + digits.lstrip("0")
    return digits


def share_message(invoice, url):
    company = invoice.company
    balance = invoice.total - invoice.amount_paid
    text = (f"Hello {invoice.customer}, here is your invoice {invoice.invoice_number} from {company.name} "
            f"for {invoice.currency} {invoice.total:.2f}.")
    if balance > 0:
        text += f" Balance due: {invoice.currency} {balance:.2f}."
    return f"{text}\n{url}\nThank you!"


def whatsapp_url(invoice, url, phone=None):
    from urllib.parse import quote
    number = normalise_phone(phone if phone is not None else invoice.customer.phone, invoice.company.country)
    return f"https://wa.me/{number}?text={quote(share_message(invoice, url))}"


def email_invoice(invoice, *, to, url, note=""):
    company = invoice.company
    body = share_message(invoice, url)
    if note.strip():
        body = note.strip() + "\n\n" + body
    message = EmailMessage(
        subject=f"Invoice {invoice.invoice_number} from {company.name}",
        body=body, to=[to], reply_to=[company.email] if company.email else None,
    )
    pdf = render_invoice_pdf(invoice)
    if pdf:
        message.attach(f"{invoice.invoice_number}.pdf", pdf, "application/pdf")
    else:
        message.attach(f"{invoice.invoice_number}.html", render_invoice_html(invoice), "text/html")
    message.send()
    return bool(pdf)

"""
Saudi Arabia (ZATCA / Fatoorah) simplified e-invoice QR code.

Phase 1 requires a QR code on every simplified tax invoice holding five
TLV-encoded fields: seller name, VAT number, invoice timestamp, invoice
total (with VAT) and VAT total, Base64-encoded. Phase 2 (XML clearance
with ZATCA's API) needs a ZATCA onboarding certificate per business and is
not covered here.
"""
import base64
from datetime import datetime, time

from django.utils import timezone

KSA_NAMES = {"saudi arabia", "ksa", "kingdom of saudi arabia"}


def _tlv(tag, value):
    data = str(value).encode("utf-8")
    if len(data) > 255:
        data = data[:255]
    return bytes([tag, len(data)]) + data


def zatca_payload(*, seller, vat_number, timestamp, total, vat_total):
    raw = b"".join([
        _tlv(1, seller), _tlv(2, vat_number), _tlv(3, timestamp),
        _tlv(4, f"{total:.2f}"), _tlv(5, f"{vat_total:.2f}"),
    ])
    return base64.b64encode(raw).decode("ascii")


def applies(company):
    return (company.country or "").strip().lower() in KSA_NAMES and bool((company.vat_number or "").strip())


def invoice_qr_svg(invoice):
    """Inline SVG QR for a KSA company with a VAT number; None otherwise."""
    company = invoice.company
    if not applies(company):
        return None
    issued = timezone.make_aware(datetime.combine(invoice.date, time(0, 0)))
    total = invoice.transaction_total if invoice.transaction_total is not None else invoice.total
    vat = invoice.transaction_tax_amount if invoice.transaction_tax_amount is not None else invoice.tax_amount
    payload = zatca_payload(seller=company.name, vat_number=company.vat_number.strip(),
                            timestamp=issued.isoformat(), total=total, vat_total=vat)
    import qrcode
    import qrcode.image.svg
    return qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=6, border=1).to_string(encoding="unicode")

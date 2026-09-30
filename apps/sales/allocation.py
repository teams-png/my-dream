"""Applying a customer's payment to their open invoices, oldest due first."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from . import services as sales
from .models import SalesInvoice

ZERO = Decimal("0")


def invoice_due(invoice):
    """What is still owed on an invoice, in the invoice's own currency."""
    total = invoice.transaction_total if invoice.transaction_total is not None else invoice.total
    return max(total - (invoice.transaction_amount_paid or ZERO), ZERO)


def open_invoices(company, customer=None):
    qs = SalesInvoice.objects.for_company(company).exclude(status__in=["paid", "void"]).select_related("customer")
    if customer is not None:
        qs = qs.filter(customer=customer)
    rows = []
    for invoice in qs.order_by("due_date", "date", "id"):
        due = invoice_due(invoice)
        if due > 0:
            invoice.due = due
            rows.append(invoice)
    return rows


def allocate_payment(*, company, user, customer, amount, date, method, invoice_id=None):
    """Pays the chosen invoice (or the oldest open ones first); anything left over stays on account.
    Returns (invoice numbers paid, amount left on account). Call inside a transaction."""
    currency = company.default_currency.upper()
    receipts, left = [], amount
    targets = open_invoices(company, customer)
    if invoice_id:
        targets = [inv for inv in targets if str(inv.id) == str(invoice_id)]
        if not targets:
            raise ValidationError(_("This invoice is already paid."))
        if targets[0].currency.upper() != currency and amount > targets[0].due:
            raise ValidationError(_("The amount is more than the invoice balance."))
    for invoice in targets:
        if left <= 0:
            break
        if invoice.currency.upper() != currency and not invoice_id:
            continue  # foreign-currency invoices are paid one by one, in their own currency
        pay = min(left, invoice.due)
        sales.record_customer_payment(company=company, user=user, customer=customer, amount=pay,
                                      date=date, invoice=invoice, method=method)
        receipts.append(invoice.invoice_number)
        left -= pay
    if left > 0:
        sales.record_customer_payment(company=company, user=user, customer=customer, amount=left,
                                      date=date, invoice=None, method=method)
    return receipts, left

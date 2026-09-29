import calendar
from datetime import date as _date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry

from .models import DepreciationEntry, FixedAsset, PostDatedCheque, RecurringInvoice

MONEY = Decimal("0.01")

EXTRA_ACCOUNTS = [
    ("1500", "Fixed Assets", "asset"),
    ("1590", "Accumulated Depreciation", "asset"),
    ("4100", "Gain on Asset Disposal", "income"),
    ("5300", "Depreciation Expense", "expense"),
    ("5310", "Loss on Asset Disposal", "expense"),
]


def ensure_finance_accounts(company):
    for code, name, type_ in EXTRA_ACCOUNTS:
        Account.objects.get_or_create(company=company, code=code, defaults={"name": name, "type": type_, "is_system_account": True})
    return {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1000", "1010", "2000", "3000", "1500", "1590", "4100", "5300", "5310"])}


def add_months(day, months, anchor_day=None):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return _date(year, month, min(anchor_day or day.day, calendar.monthrange(year, month)[1]))


def month_end(day):
    return _date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


# --------------------------------------------------------------- cheques

def register_cheque(*, company, user, direction, amount, cheque_number, cheque_date, received_on=None,
                    customer=None, supplier=None, invoice=None, purchase=None, bank_name="", notes=""):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValidationError("Cheque amount must be more than zero.")
    if direction == "received" and customer is None:
        raise ValidationError("Choose the customer who gave the cheque.")
    if direction == "issued" and supplier is None:
        raise ValidationError("Choose the supplier the cheque is for.")
    for obj in (customer, supplier, invoice, purchase):
        if obj is not None and obj.company_id != company.id:
            raise ValidationError("Records must belong to the active company.")
    if invoice and customer and invoice.customer_id != customer.id:
        raise ValidationError("That invoice belongs to a different customer.")
    if purchase and supplier and purchase.supplier_id != supplier.id:
        raise ValidationError("That bill belongs to a different supplier.")
    return PostDatedCheque.objects.create(
        company=company, direction=direction, amount=amount, cheque_number=cheque_number.strip(),
        cheque_date=cheque_date, received_on=received_on or timezone.localdate(), customer=customer,
        supplier=supplier, invoice=invoice, purchase=purchase, bank_name=bank_name, notes=notes, created_by=user,
    )


@transaction.atomic
def update_cheque_status(*, company, user, cheque, status, on=None, reason=""):
    """pending -> deposited -> cleared, or -> bounced / cancelled. Clearing books the payment."""
    on = on or timezone.localdate()
    allowed = {
        "pending": {"deposited", "cleared", "bounced", "cancelled"},
        "deposited": {"cleared", "bounced"},
        "bounced": {"deposited", "cancelled"},
    }
    if cheque.company_id != company.id or status not in allowed.get(cheque.status, set()):
        raise ValidationError(f"A {cheque.get_status_display().lower()} cheque cannot be marked {status}.")
    if status == "cleared":
        if cheque.direction == "received":
            from apps.sales.services import record_customer_payment
            record_customer_payment(company=company, user=user, customer=cheque.customer, amount=cheque.amount,
                                    date=on, invoice=cheque.invoice, method="cheque")
        else:
            from apps.purchases.services import record_supplier_payment
            record_supplier_payment(company=company, user=user, supplier=cheque.supplier, amount=cheque.amount,
                                    date=on, purchase=cheque.purchase, method="cheque")
        cheque.cleared_on = on
    if status == "deposited":
        cheque.deposited_on = on
    if status == "bounced":
        cheque.bounce_reason = reason.strip() or "Returned by bank"
        from apps.notifications.services import notify
        notify(company=company, title=f"Cheque {cheque.cheque_number} bounced",
               message=f"{cheque.party} · {cheque.amount} · {cheque.bounce_reason}")
    cheque.status = status
    cheque.save()
    from apps.audit.services import log_action
    log_action(company=company, user=user, action=f"cheque_{status}", model_name="PostDatedCheque",
               object_id=cheque.id, changes={"status": status, "reason": reason})
    return cheque


def cheques_due(company, within_days=7, today=None):
    today = today or timezone.localdate()
    return PostDatedCheque.objects.for_company(company).filter(
        status__in=["pending", "deposited"], cheque_date__lte=today + timedelta(days=within_days),
    )


def send_cheque_reminders(today=None):
    """Daily: one reminder per cheque that becomes due within 3 days."""
    from apps.notifications.services import notify
    today = today or timezone.localdate()
    sent = 0
    for cheque in PostDatedCheque._base_manager.select_related("company", "customer", "supplier").filter(
        status="pending", cheque_date__lte=today + timedelta(days=3), reminder_sent_on__isnull=True,
    ):
        when = "today" if cheque.cheque_date <= today else f"on {cheque.cheque_date:%d %b}"
        notify(company=cheque.company, title=f"Cheque {cheque.cheque_number} is due {when}",
               message=f"{cheque.get_direction_display()} · {cheque.party} · {cheque.amount}")
        cheque.reminder_sent_on = today
        cheque.save(update_fields=["reminder_sent_on"])
        sent += 1
    return sent


# ------------------------------------------------------ recurring invoices

def next_date(day, frequency, anchor_day=None):
    if frequency == "weekly":
        return day + timedelta(days=7)
    return add_months(day, {"monthly": 1, "quarterly": 3, "yearly": 12}[frequency], anchor_day)


@transaction.atomic
def run_recurring_invoice(recurring, *, today=None, request_base_url=""):
    """Creates every invoice that is due (catching up missed periods)."""
    from apps.sales.services import create_invoice
    today = today or timezone.localdate()
    created = []
    recurring = RecurringInvoice.objects.select_for_update().get(pk=recurring.pk)
    lines = [{"product": l.product, "quantity": l.quantity, "unit_price": l.unit_price} for l in recurring.lines.select_related("product")]
    if not lines:
        raise ValidationError("Add at least one line to the recurring invoice.")
    if not recurring.anchor_day:
        recurring.anchor_day = recurring.next_run_date.day
    while recurring.is_active and recurring.next_run_date <= today:
        if recurring.end_date and recurring.next_run_date > recurring.end_date:
            recurring.is_active = False
            break
        invoice = create_invoice(
            company=recurring.company, user=recurring.created_by, customer=recurring.customer,
            date=recurring.next_run_date, lines=lines, warehouse=recurring.warehouse,
            tax_rate=recurring.tax_percent / Decimal("100"),
        )
        created.append(invoice)
        recurring.invoices_created += 1
        recurring.last_invoice = invoice
        recurring.next_run_date = next_date(recurring.next_run_date, recurring.frequency, recurring.anchor_day)
    if recurring.end_date and recurring.next_run_date > recurring.end_date:
        recurring.is_active = False
    recurring.save()
    if recurring.email_customer and recurring.customer.email:
        from django.conf import settings
        from django.urls import reverse
        from apps.sales import sharing
        base = request_base_url or getattr(settings, "SITE_URL", "")
        for invoice in created:
            url = base.rstrip("/") + reverse("webapp:public_invoice", args=[sharing.share_token(invoice)]) if base else ""
            transaction.on_commit(lambda inv=invoice, u=url: _safe_email(inv, recurring.customer.email, u))
    return created


def _safe_email(invoice, to, url):
    from apps.sales import sharing
    try:
        sharing.email_invoice(invoice, to=to, url=url)
    except Exception:
        pass  # email problems must never block billing; the invoice exists either way


def run_all_recurring_invoices(today=None):
    today = today or timezone.localdate()
    total = 0
    for recurring in RecurringInvoice._base_manager.filter(is_active=True, next_run_date__lte=today):
        try:
            total += len(run_recurring_invoice(recurring, today=today))
        except ValidationError:
            continue
    return total


# ----------------------------------------------------------- fixed assets

@transaction.atomic
def register_asset(*, company, user, **fields):
    cost = Decimal(str(fields["cost"]))
    salvage = Decimal(str(fields.get("salvage_value") or 0))
    if cost <= 0 or salvage < 0 or salvage >= cost:
        raise ValidationError("Cost must be positive and more than the salvage value.")
    if not fields.get("useful_life_months"):
        raise ValidationError("Enter the useful life in months.")
    asset = FixedAsset.objects.create(company=company, **fields)
    accounts = ensure_finance_accounts(company)
    credit = {"bank": "1010", "cash": "1000", "payable": "2000", "none": "3000"}[asset.paid_from]
    asset.purchase_entry = post_journal_entry(
        company=company, date=asset.purchase_date, user=user,
        lines=[(accounts["1500"], asset.cost, Decimal("0")), (accounts[credit], Decimal("0"), asset.cost)],
        reference=f"Asset#{asset.id}", memo=f"Fixed asset: {asset.name}", source_type="fixed_asset", source_id=asset.id,
    )
    asset.save(update_fields=["purchase_entry"])
    return asset


@transaction.atomic
def run_depreciation(*, company, user, up_to=None):
    """Posts straight-line depreciation for every full month not yet posted, up to `up_to`."""
    up_to = month_end(up_to or timezone.localdate())
    accounts = ensure_finance_accounts(company)
    posted = []
    for asset in FixedAsset.objects.for_company(company).filter(status="active").prefetch_related("depreciation_entries"):
        done = {d.period_end for d in asset.depreciation_entries.all()}
        remaining = asset.cost - asset.salvage_value - asset.accumulated_depreciation
        period = month_end(asset.purchase_date)
        while period <= up_to and remaining > 0:
            if period not in done:
                amount = min(asset.monthly_depreciation, remaining)
                if amount <= 0:
                    break
                entry = post_journal_entry(
                    company=company, date=period, user=user,
                    lines=[(accounts["5300"], amount, Decimal("0")), (accounts["1590"], Decimal("0"), amount)],
                    reference=f"Depr#{asset.id}-{period:%Y%m}", memo=f"Depreciation {asset.name} {period:%b %Y}",
                    source_type="depreciation", source_id=asset.id,
                )
                posted.append(DepreciationEntry.objects.create(asset=asset, period_end=period, amount=amount, journal_entry=entry))
                remaining -= amount
            period = month_end(add_months(period.replace(day=1), 1))
    return posted


@transaction.atomic
def dispose_asset(*, company, user, asset, on, amount, received_in="bank"):
    if asset.company_id != company.id or asset.status != "active":
        raise ValidationError("Only an asset in use can be disposed.")
    amount = Decimal(str(amount or 0))
    run_depreciation(company=company, user=user, up_to=on)
    asset.refresh_from_db()
    accounts = ensure_finance_accounts(company)
    accumulated = asset.accumulated_depreciation
    book_value = asset.cost - accumulated
    lines = [(accounts["1590"], accumulated, Decimal("0")), (accounts["1500"], Decimal("0"), asset.cost)]
    if amount:
        lines.append((accounts["1000" if received_in == "cash" else "1010"], amount, Decimal("0")))
    difference = amount - book_value
    if difference > 0:
        lines.append((accounts["4100"], Decimal("0"), difference))
    elif difference < 0:
        lines.append((accounts["5310"], -difference, Decimal("0")))
    post_journal_entry(company=company, date=on, user=user, lines=lines, reference=f"Dispose#{asset.id}",
                       memo=f"Disposal of {asset.name}", source_type="asset_disposal", source_id=asset.id)
    asset.status, asset.disposed_on, asset.disposal_amount = "disposed", on, amount
    asset.save(update_fields=["status", "disposed_on", "disposal_amount"])
    return asset

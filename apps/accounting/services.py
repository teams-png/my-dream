"""
The ledger's single sanctioned write path (Phase 0 Section 9 / Phase 1
Section 5). No other app should ever create a JournalLine directly —
every financially-relevant action calls post_journal_entry().
"""
from decimal import Decimal
from datetime import date as _date
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import JournalEntry, JournalLine, Account, FiscalYear


DEFAULT_CHART_OF_ACCOUNTS = [
    # (code, name, type, is_system_account)
    ("1000", "Cash", "asset", True),
    ("1010", "Bank", "asset", True),
    ("1100", "Accounts Receivable", "asset", True),
    ("1200", "Inventory", "asset", True),
    ("2000", "Accounts Payable", "liability", True),
    ("2050", "Goods Received Not Invoiced (GRNI)", "liability", True),
    ("2100", "Tax Payable", "liability", True),
    ("2200", "Payroll Payable", "liability", True),
    ("2250", "Payroll Deductions Payable", "liability", True),
    ("3000", "Owner's Equity", "equity", True),
    ("3900", "Retained Earnings", "equity", True),
    ("4000", "Sales Revenue", "income", True),
    ("4050", "Realized Exchange Gain", "income", True),
    ("5000", "Cost of Goods Sold", "expense", True),
    ("5100", "General Expenses", "expense", True),
    ("5150", "Realized Exchange Loss", "expense", True),
    ("5200", "Salary and Payroll Expense", "expense", True),
]


def seed_chart_of_accounts(company):
    """Called once at company creation, alongside role/module seeding (Phase 0 Section 9)."""
    Account.objects.bulk_create(
        [
            Account(company=company, code=code, name=name, type=type_, is_system_account=system)
            for code, name, type_, system in DEFAULT_CHART_OF_ACCOUNTS
        ],
        ignore_conflicts=True,
    )


def get_fiscal_year_for_date(company, date):
    """Returns the FiscalYear row covering `date` for this company, or None
    if fiscal years haven't been configured for this company/date (kept
    permissive on purpose — see post_journal_entry's docstring)."""
    return (
        FiscalYear.objects.for_company(company)
        .filter(start_date__lte=date, end_date__gte=date)
        .first()
    )


@transaction.atomic
def post_journal_entry(
    *, company, date, lines, user, reference="", memo="",
    source_type="manual", source_id=None, override_lock=False,
):
    """
    lines: list of (account, debit, credit) tuples — one of debit/credit is
    normally 0 per line. Rejects the whole entry if debits != credits
    (Phase 0 Section 9). Wrapped in a DB transaction alongside the
    originating record by the caller (e.g. sales.services.create_invoice).

    Phase 28: also enforces fiscal-year period locking. If a FiscalYear
    row covers `date`, posting is blocked when that year is closed, or
    when `date` falls on/before its lock_date — unless `override_lock=True`
    is passed by a caller that has already checked the poster's role has
    the accounting.override_period_lock permission (see
    apps.tenants.permissions.HasCompanyPermission). Companies/dates with
    no matching FiscalYear row are allowed through unchanged, so existing
    data that predates fiscal-year configuration keeps working exactly as
    before this phase.
    """
    fiscal_year = get_fiscal_year_for_date(company, date)
    if fiscal_year and not override_lock:
        # `date` may arrive as a "YYYY-MM-DD" string (existing callers across
        # the codebase pass either) — normalise before comparing to a real
        # date object so this doesn't blow up with a TypeError.
        compare_date = date if isinstance(date, _date) else parse_date(str(date))
        if fiscal_year.is_closed:
            raise ValidationError(
                f"Cannot post on {date}: fiscal year {fiscal_year.start_date}–"
                f"{fiscal_year.end_date} is closed."
            )
        if fiscal_year.lock_date and compare_date is not None and compare_date <= fiscal_year.lock_date:
            raise ValidationError(
                f"Cannot post on {date}: this period is locked for posting "
                f"on or before {fiscal_year.lock_date}."
            )

    total_debit = sum((Decimal(d) for _, d, _ in lines), Decimal("0"))
    total_credit = sum((Decimal(c) for _, _, c in lines), Decimal("0"))

    if total_debit != total_credit:
        raise ValidationError(
            f"Journal entry does not balance: debits={total_debit} credits={total_credit}"
        )
    if total_debit == 0:
        raise ValidationError("Journal entry has no amount.")

    entry = JournalEntry.objects.create(
        company=company, date=date, reference=reference, memo=memo,
        source_type=source_type, source_id=source_id, posted_by=user,
    )
    JournalLine.objects.bulk_create(
        [
            JournalLine(journal_entry=entry, account=account, debit=debit, credit=credit)
            for account, debit, credit in lines
        ]
    )
    return entry


@transaction.atomic
def close_fiscal_year(*, company, fiscal_year, user):
    """
    Phase 28 year-end close. Zeroes every income/expense account's balance
    for the fiscal year via a reversing journal entry and moves the net
    result into the Retained Earnings equity account (3900) — the standard
    closing-entry mechanic, so profit/loss from a closed year lives in
    Equity going forward instead of being recomputed live every time (see
    balance_sheet()'s "current_year_profit" handling below).

    Idempotent: calling this again on an already-closed year is a no-op
    that returns the original closing entry rather than posting a second
    one (acceptance criteria: "closing does not duplicate entries when
    repeated").
    """
    if fiscal_year.company_id != company.id:
        raise ValidationError("This fiscal year does not belong to the active company.")

    if fiscal_year.is_closed:
        return JournalEntry.objects.filter(
            company=company, source_type="fiscal_year_close",
            source_id=fiscal_year.id, is_void=False,
        ).first()

    # Defensive — guarantees the Retained Earnings account exists even for
    # companies created before Phase 28 added it to the default chart.
    seed_chart_of_accounts(company)
    retained_earnings = Account.objects.for_company(company).get(code="3900")

    pl = profit_and_loss(company, date_from=fiscal_year.start_date, date_to=fiscal_year.end_date)
    net_profit = pl["net_profit"]

    lines = []
    for account, balance in pl["income"]:
        lines.append((account, balance, Decimal("0")))   # debit zeroes a credit-normal balance
    for account, balance in pl["expenses"]:
        lines.append((account, Decimal("0"), balance))   # credit zeroes a debit-normal balance
    if net_profit > 0:
        lines.append((retained_earnings, Decimal("0"), net_profit))
    elif net_profit < 0:
        lines.append((retained_earnings, -net_profit, Decimal("0")))

    entry = None
    if lines:
        entry = post_journal_entry(
            company=company, date=fiscal_year.end_date, lines=lines, user=user,
            reference=f"FY-CLOSE-{fiscal_year.id}",
            memo=f"Year-end close {fiscal_year.start_date} to {fiscal_year.end_date}",
            source_type="fiscal_year_close", source_id=fiscal_year.id,
            override_lock=True,  # the close itself must be able to post on end_date
        )

    fiscal_year.is_closed = True
    fiscal_year.closed_at = timezone.now()
    fiscal_year.closed_by = user
    fiscal_year.save(update_fields=["is_closed", "closed_at", "closed_by"])

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="close_fiscal_year",
        model_name="FiscalYear", object_id=fiscal_year.id,
        changes={"net_profit": str(net_profit), "journal_entry_id": entry.id if entry else None},
    )
    return entry


def reopen_fiscal_year(*, company, fiscal_year, user):
    """
    Explicit, audited reopen (acceptance criteria). Deliberately does NOT
    reverse/void the closing entry automatically — reversing it is a
    separate, equally auditable action left to a future phase, so a
    reopen can never silently rewrite the ledger. Idempotent when the
    year is already open.
    """
    if fiscal_year.company_id != company.id:
        raise ValidationError("This fiscal year does not belong to the active company.")

    if not fiscal_year.is_closed:
        return fiscal_year

    fiscal_year.is_closed = False
    fiscal_year.save(update_fields=["is_closed"])

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="reopen_fiscal_year",
        model_name="FiscalYear", object_id=fiscal_year.id, changes={},
    )
    return fiscal_year


def account_balance(account, as_of=None):
    """Sum of debits minus credits (or credits minus debits, per type) for one account."""
    from django.db.models import Sum

    qs = JournalLine.objects.filter(account=account, journal_entry__is_void=False)
    if as_of:
        qs = qs.filter(journal_entry__date__lte=as_of)

    agg = qs.aggregate(debit=Sum("debit"), credit=Sum("credit"))
    debit = agg["debit"] or Decimal("0")
    credit = agg["credit"] or Decimal("0")

    if account.type in ("asset", "expense"):
        return debit - credit
    return credit - debit


def trial_balance(company, as_of=None):
    """Returns [(account, balance), ...] for every active account — the raw report data."""
    accounts = Account.objects.for_company(company).filter(is_active=True).order_by("code")
    return [(a, account_balance(a, as_of)) for a in accounts]


def profit_and_loss(company, date_from=None, date_to=None):
    """
    Sums JournalLine activity for income/expense accounts only, over a date
    range — never re-derived from SalesInvoice.total or Expense.amount
    directly, so it always reconciles with the ledger (Phase 0 Section 9).
    """
    from django.db.models import Sum

    qs = JournalLine.objects.filter(
        account__company=company, account__type__in=["income", "expense"],
        journal_entry__is_void=False,
    )
    if date_from:
        qs = qs.filter(journal_entry__date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__date__lte=date_to)

    accounts = Account.objects.for_company(company).filter(
        type__in=["income", "expense"], is_active=True
    ).order_by("type", "code")

    income_lines, expense_lines = [], []
    total_income = total_expense = Decimal("0")

    for account in accounts:
        agg = qs.filter(account=account).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        debit = agg["debit"] or Decimal("0")
        credit = agg["credit"] or Decimal("0")
        balance = (credit - debit) if account.type == "income" else (debit - credit)
        if balance == 0:
            continue
        if account.type == "income":
            income_lines.append((account, balance))
            total_income += balance
        else:
            expense_lines.append((account, balance))
            total_expense += balance

    return {
        "income": income_lines,
        "expenses": expense_lines,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": total_income - total_expense,
    }


def balance_sheet(company, as_of=None):
    """
    Asset/Liability/Equity balances as of a date.

    Phase 28: prior-year profit is now a real, permanent balance sitting
    in the Retained Earnings (3900) equity account once close_fiscal_year()
    has run — it's already included in total_equity below like any other
    equity account. What's shown separately here as "retained_earnings" is
    only the *current, not-yet-closed* fiscal year's profit-to-date, so the
    two never overlap or get double-counted (acceptance criteria: "current
    year P&L and prior retained earnings are separated"). Companies with no
    FiscalYear configured for `as_of` fall back to the pre-Phase-28
    behaviour (all-time net profit) so they keep working unchanged.
    """
    accounts = Account.objects.for_company(company).filter(
        type__in=["asset", "liability", "equity"], is_active=True
    ).order_by("type", "code")

    assets, liabilities, equity = [], [], []
    total_assets = total_liabilities = total_equity = Decimal("0")

    for account in accounts:
        balance = account_balance(account, as_of)
        if balance == 0:
            continue
        if account.type == "asset":
            assets.append((account, balance)); total_assets += balance
        elif account.type == "liability":
            liabilities.append((account, balance)); total_liabilities += balance
        else:
            equity.append((account, balance)); total_equity += balance

    reference_date = as_of or timezone.localdate()
    current_fy = get_fiscal_year_for_date(company, reference_date)
    if current_fy and not current_fy.is_closed:
        pl = profit_and_loss(company, date_from=current_fy.start_date, date_to=as_of)
    else:
        pl = profit_and_loss(company, date_to=as_of)
    retained_earnings = pl["net_profit"]

    return {
        "assets": assets, "liabilities": liabilities, "equity": equity,
        "total_assets": total_assets, "total_liabilities": total_liabilities,
        "total_equity": total_equity, "retained_earnings": retained_earnings,
        "total_liabilities_and_equity": total_liabilities + total_equity + retained_earnings,
    }

"""
Phase 29 — Bank and Cash Management + Reconciliation, built on top of the
existing chart of accounts and apps.accounting.services.post_journal_entry
(the ledger's only write path — nothing here ever creates a JournalLine
directly).
"""
import csv
import hashlib
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounting.services import post_journal_entry, account_balance

from .models import BankAccount, StatementImportBatch, StatementTransaction


# ---------------------------------------------------------------- deposits /
# withdrawals / transfers


@transaction.atomic
def record_deposit(
    *, company, bank_account, contra_account, amount, date, user,
    reference="", memo="", statement_transaction=None,
):
    """Money coming into a bank/cash account from `contra_account` (e.g. a
    customer receipt sitting in Accounts Receivable, or Sales Revenue for a
    till deposit). Debits the bank account, credits the contra account.

    If `statement_transaction` is given, the new entry is immediately
    matched to it (the common real-world flow: "create the missing entry
    for this unmatched statement row") — matching still goes through
    match_transaction() so the same amount/ownership checks apply.
    """
    amount = Decimal(amount)
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=[
            (bank_account.ledger_account, amount, Decimal("0")),
            (contra_account, Decimal("0"), amount),
        ],
        reference=reference, memo=memo,
        source_type="bank_deposit", source_id=bank_account.id,
    )
    if statement_transaction is not None:
        match_transaction(company=company, statement_transaction=statement_transaction, journal_entry=entry, user=user)
    return entry


@transaction.atomic
def record_withdrawal(
    *, company, bank_account, contra_account, amount, date, user,
    reference="", memo="", statement_transaction=None,
):
    """Money leaving a bank/cash account to `contra_account` (e.g. a
    supplier payment reducing Accounts Payable, or straight to an expense
    account). Credits the bank account, debits the contra account."""
    amount = Decimal(amount)
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=[
            (contra_account, amount, Decimal("0")),
            (bank_account.ledger_account, Decimal("0"), amount),
        ],
        reference=reference, memo=memo,
        source_type="bank_withdrawal", source_id=bank_account.id,
    )
    if statement_transaction is not None:
        match_transaction(company=company, statement_transaction=statement_transaction, journal_entry=entry, user=user)
    return entry


@transaction.atomic
def transfer_between_accounts(
    *, company, from_account, to_account, amount, date, user, reference="", memo="",
):
    """
    One balanced journal entry moving money between two of the company's
    own bank/cash accounts. Both legs are asset accounts, so this never
    touches an income/expense account — profit_and_loss() is provably
    unaffected (Phase 29 acceptance criteria: "transfer does not affect
    profit").
    """
    if from_account.company_id != company.id or to_account.company_id != company.id:
        raise ValidationError("Both accounts must belong to the active company.")
    if from_account.id == to_account.id:
        raise ValidationError("Cannot transfer an account to itself.")

    amount = Decimal(amount)
    return post_journal_entry(
        company=company, date=date, user=user,
        lines=[
            (to_account.ledger_account, amount, Decimal("0")),
            (from_account.ledger_account, Decimal("0"), amount),
        ],
        reference=reference, memo=memo or f"Transfer {from_account.name} → {to_account.name}",
        source_type="bank_transfer", source_id=from_account.id,
    )


# ---------------------------------------------------------------- statement
# import (CSV)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_fingerprint(bank_account_id, date, amount, description, reference):
    return _hash(f"{bank_account_id}|{date}|{amount}|{description}|{reference}")


REQUIRED_CSV_COLUMNS = {"date", "description", "amount"}


@transaction.atomic
def import_statement_csv(*, company, bank_account, file_name, csv_text, user):
    """
    Expects a CSV with at least `date` (YYYY-MM-DD), `description`,
    `amount` (signed — positive in, negative out) columns, and an optional
    `reference` column. Column names are matched case-insensitively.

    Two layers of duplicate protection (Phase 29 rule):
    1. Whole-file fingerprint on StatementImportBatch — re-uploading the
       exact same file for this bank account is rejected outright.
    2. Per-row fingerprint on StatementTransaction — a row identical to
       one already imported for this bank account (even from a different
       file, e.g. an overlapping date-range re-export) is silently
       skipped rather than duplicated, and counted in
       skipped_duplicate_count.
    """
    if bank_account.company_id != company.id:
        raise ValidationError("This bank account does not belong to the active company.")

    fingerprint = _hash(csv_text)
    if StatementImportBatch.objects.filter(
        company=company, bank_account=bank_account, fingerprint=fingerprint
    ).exists():
        raise ValidationError("This exact statement file has already been imported for this account.")

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValidationError("The CSV file has no header row.")
    normalized = {name.strip().lower(): name for name in reader.fieldnames}
    missing = REQUIRED_CSV_COLUMNS - set(normalized)
    if missing:
        raise ValidationError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")

    batch = StatementImportBatch.objects.create(
        company=company, bank_account=bank_account, file_name=file_name,
        fingerprint=fingerprint, imported_by=user,
    )

    existing_fingerprints = set(
        StatementTransaction.objects.filter(company=company, bank_account=bank_account)
        .values_list("row_fingerprint", flat=True)
    )

    to_create = []
    row_count = 0
    skipped = 0
    for row in reader:
        row_count += 1
        raw_date = row[normalized["date"]].strip()
        row_date = parse_date(raw_date)
        if row_date is None:
            raise ValidationError(f"Row {row_count}: unrecognised date '{raw_date}' (expected YYYY-MM-DD).")
        description = row[normalized["description"]].strip()
        reference = row.get(normalized.get("reference", ""), "").strip() if "reference" in normalized else ""
        try:
            amount = Decimal(row[normalized["amount"]].strip())
        except (InvalidOperation, KeyError):
            raise ValidationError(f"Row {row_count}: invalid amount '{row.get(normalized['amount'])}'.")

        fp = _row_fingerprint(bank_account.id, row_date, amount, description, reference)
        if fp in existing_fingerprints:
            skipped += 1
            continue
        existing_fingerprints.add(fp)  # guards against duplicate rows within the same file too

        to_create.append(StatementTransaction(
            company=company, bank_account=bank_account, import_batch=batch,
            date=row_date, description=description, reference=reference,
            amount=amount, row_fingerprint=fp,
        ))

    StatementTransaction.objects.bulk_create(to_create)
    batch.row_count = row_count
    batch.skipped_duplicate_count = skipped
    batch.save(update_fields=["row_count", "skipped_duplicate_count"])
    return batch


# ---------------------------------------------------------------- matching


def suggest_matches(*, company, statement_transaction, date_tolerance_days=5):
    """
    Read-only. Returns JournalEntry objects touching this bank account's
    ledger account whose net signed effect on that account equals the
    statement transaction's amount, within `date_tolerance_days` of its
    date, and not already claimed by another matched StatementTransaction.
    Never changes any state — "assisted matching... without
    auto-confirming uncertain matches" (Phase 29 rule).
    """
    from datetime import timedelta
    from django.db.models import Sum, Q
    from apps.accounting.models import JournalEntry

    if statement_transaction.company_id != company.id:
        raise ValidationError("This statement transaction does not belong to the active company.")

    bank_account = statement_transaction.bank_account
    window_start = statement_transaction.date - timedelta(days=date_tolerance_days)
    window_end = statement_transaction.date + timedelta(days=date_tolerance_days)

    already_matched_ids = StatementTransaction.objects.filter(
        company=company, bank_account=bank_account, status="matched",
    ).exclude(pk=statement_transaction.pk).values_list("matched_journal_entry_id", flat=True)

    candidates = (
        JournalEntry.objects.filter(
            company=company, lines__account=bank_account.ledger_account,
            date__gte=window_start, date__lte=window_end, is_void=False,
        )
        .exclude(id__in=list(already_matched_ids))
        .distinct()
    )

    matches = []
    for entry in candidates:
        agg = entry.lines.filter(account=bank_account.ledger_account).aggregate(
            debit=Sum("debit"), credit=Sum("credit")
        )
        net = (agg["debit"] or Decimal("0")) - (agg["credit"] or Decimal("0"))
        if net == statement_transaction.amount:
            matches.append(entry)
    return matches


@transaction.atomic
def match_transaction(*, company, statement_transaction, journal_entry, user):
    """
    Explicit confirmation only — never called automatically by import or
    suggest_matches(). Requires the journal entry's net effect on this
    statement transaction's bank ledger account to exactly equal its
    amount, so a mismatched match can't be silently confirmed.
    """
    from django.db.models import Sum

    if statement_transaction.company_id != company.id or journal_entry.company_id != company.id:
        raise ValidationError("Statement transaction and journal entry must both belong to the active company.")
    if statement_transaction.status == "matched":
        raise ValidationError("This statement transaction is already matched — unmatch it first.")

    bank_account = statement_transaction.bank_account
    agg = journal_entry.lines.filter(account=bank_account.ledger_account).aggregate(
        debit=Sum("debit"), credit=Sum("credit")
    )
    net = (agg["debit"] or Decimal("0")) - (agg["credit"] or Decimal("0"))
    if net != statement_transaction.amount:
        raise ValidationError(
            f"Journal entry's effect on {bank_account.name} ({net}) does not match "
            f"the statement transaction amount ({statement_transaction.amount})."
        )

    statement_transaction.status = "matched"
    statement_transaction.matched_journal_entry = journal_entry
    statement_transaction.matched_at = timezone.now()
    statement_transaction.matched_by = user
    statement_transaction.save(update_fields=["status", "matched_journal_entry", "matched_at", "matched_by"])

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="match_statement_transaction",
        model_name="StatementTransaction", object_id=statement_transaction.id,
        changes={"journal_entry_id": journal_entry.id},
    )
    return statement_transaction


def unmatch_transaction(*, company, statement_transaction, user):
    """Idempotent — unmatching an already-unmatched row is a safe no-op."""
    if statement_transaction.company_id != company.id:
        raise ValidationError("This statement transaction does not belong to the active company.")
    if statement_transaction.status == "unmatched":
        return statement_transaction

    statement_transaction.status = "unmatched"
    statement_transaction.matched_journal_entry = None
    statement_transaction.matched_at = None
    statement_transaction.matched_by = None
    statement_transaction.save(update_fields=["status", "matched_journal_entry", "matched_at", "matched_by"])

    from apps.audit.services import log_action
    log_action(
        company=company, user=user, action="unmatch_statement_transaction",
        model_name="StatementTransaction", object_id=statement_transaction.id, changes={},
    )
    return statement_transaction


# ---------------------------------------------------------------- reconciliation


def reconciliation_summary(*, company, bank_account, as_of=None):
    """
    statement_balance = opening balance + every imported statement row to
    date (matched or not — the statement doesn't care about our ledger).
    ledger_balance comes from the real chart-of-accounts balance. The gap
    between them is exactly the unmatched activity on one side or the
    other; once every real movement is both recorded in the ledger and
    matched to its statement row, difference reaches zero (Phase 29
    acceptance criteria).
    """
    from django.db.models import Sum

    if bank_account.company_id != company.id:
        raise ValidationError("This bank account does not belong to the active company.")

    qs = StatementTransaction.objects.filter(company=company, bank_account=bank_account)
    if as_of:
        qs = qs.filter(date__lte=as_of)

    activity_total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    statement_balance = bank_account.opening_balance + activity_total
    ledger_balance = account_balance(bank_account.ledger_account, as_of)

    return {
        "bank_account": bank_account,
        "ledger_balance": ledger_balance,
        "statement_balance": statement_balance,
        "difference": ledger_balance - statement_balance,
        "unmatched_count": qs.filter(status="unmatched").count(),
        "matched_count": qs.filter(status="matched").count(),
    }

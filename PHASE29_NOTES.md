# PHASE 29 — Bank and Cash Management + Reconciliation

## 1. New app — `apps/banking`

A new app rather than bolting onto `accounting`, since it owns its own
models/lifecycle (bank accounts, statement imports, reconciliation) even
though every posting still goes through `accounting.services.post_journal_entry`
— nothing here ever creates a `JournalLine` directly.

Models (`apps/banking/models.py`):
- `BankAccount` — maps 1:1 to an asset `Account` (`ledger_account`) via
  `OneToOneField`. No stored balance field — the ledger is always the
  source of truth, exactly like the rest of the system.
- `StatementImportBatch` — one CSV upload. `fingerprint` = sha256 of the
  raw file content, unique per `(company, bank_account)` — re-uploading
  the exact same file is rejected before any row is parsed.
- `StatementTransaction` — one imported row. Never posts an accounting
  entry by itself. `row_fingerprint` = sha256 of
  `(bank_account, date, amount, description, reference)`, unique per
  `(company, bank_account)` — catches duplicate rows even across
  different files (e.g. an overlapping-date-range re-export), not just
  an identical whole-file re-upload.

## 2. Services — `apps/banking/services.py`

- `record_deposit()` / `record_withdrawal()` — post one balanced entry
  each (bank ledger account vs. a caller-supplied contra account).
  Optional `statement_transaction=` immediately matches the new entry to
  that row via `match_transaction()` — the common "create the missing
  entry for this unmatched row" flow.
- `transfer_between_accounts()` — one entry between two of the company's
  own bank/cash ledger accounts, both asset-side, so it never touches
  income/expense. Verified by a test that `profit_and_loss()`'s
  `net_profit` is unchanged before/after a transfer (acceptance
  criteria: "transfer does not affect profit").
- `import_statement_csv()` — parses `date`/`description`/`amount`
  (signed) + optional `reference` columns (case-insensitive header
  match). Two-layer dedup as above; returns the batch with
  `row_count` / `skipped_duplicate_count`.
- `suggest_matches()` — **read-only**. Finds journal entries touching
  the bank account's ledger account with the exact same net signed
  amount, within ±5 days, not already claimed by another matched
  statement row. Never changes state (Phase 29 rule: "assisted matching
  ... without auto-confirming uncertain matches").
- `match_transaction()` — explicit confirmation only. Recomputes the
  journal entry's net effect on the bank ledger account and rejects the
  match if it doesn't exactly equal the statement transaction's amount.
  Rejects re-matching an already-matched row (unmatch first). Audited.
- `unmatch_transaction()` — idempotent, audited.
- `reconciliation_summary()` — `statement_balance` (opening balance +
  every imported row to date) vs. `ledger_balance` (real chart-of-accounts
  balance); `difference` is exactly the unreconciled gap. A test drives
  it to zero once every statement row has a matching ledger entry
  (acceptance criteria: "reconciliation difference can reach zero").

## 3. RBAC — `apps/tenants/services.py`

Two new permissions: `banking.manage` (accounts, deposit/withdraw/
transfer, import, match/unmatch) and `banking.view` (read-only,
including reconciliation). Both granted to **Owner** and **Accountant**
only — **Staff gets neither**, per "keep tenant isolation and
permissions strict." Existing companies backfilled via
`apps/tenants/migrations/0005_backfill_banking_permissions.py` (same
pattern as Phase 28's fiscal-year permission backfill).

## 4. API — `apps/banking/views.py` + `urls.py`, mounted at `/api/banking/`

- `GET/POST /bank-accounts/`, `GET/PATCH /bank-accounts/{id}/`
- `POST /bank-accounts/{id}/deposit/`
- `POST /bank-accounts/{id}/withdraw/`
- `POST /bank-accounts/{id}/transfer/` (body: `to_bank_account`, `amount`, `date`, ...)
- `POST /bank-accounts/{id}/import-statement/` (`file` upload or raw `csv_text`)
- `GET /bank-accounts/{id}/reconciliation/?as_of=YYYY-MM-DD`
- `GET /statement-transactions/?bank_account=&status=`
- `GET /statement-transactions/{id}/suggestions/`
- `POST /statement-transactions/{id}/match/` (body: `journal_entry`)
- `POST /statement-transactions/{id}/unmatch/`

`ledger_account` on `BankAccountSerializer` is validated to belong to
the active company and be an asset account — an IDOR guard at the
serializer layer, same pattern used elsewhere for cross-app foreign
keys (`contra_account`, `to_bank_account` similarly validated).

## 5. Tests — `apps/banking/tests/test_banking.py` (20 tests, new file)

Covers: deposit/withdrawal ledger effects, transfer leaving
`net_profit` unchanged, cross-tenant and same-account transfer
rejection; CSV import creating rows, whole-file duplicate rejection,
cross-file overlapping-row dedup, missing-column validation; match
requiring an exact amount, match/unmatch round-trip (idempotent
unmatch), rejecting a re-match on an already-matched row, the
`statement_transaction=` auto-match convenience path, `suggest_matches`
finding a candidate without changing any state; reconciliation
difference reaching exactly zero once fully matched vs. showing the
right gap when the ledger entry is missing; and API-level RBAC (Owner
can create+deposit, Staff blocked entirely), cross-tenant 404, and the
ledger-account-ownership IDOR guard.

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 203 passed (183 existing + 20 new)
```

## Phase 29 status: complete

## Known limitations / next open items

- No bank fee/interest auto-posting helper — a bank fee shown on a
  statement still needs a manual `record_withdrawal()` (or a matching
  entry created some other way) before it can be matched; there's no
  one-click "post this unmatched row straight to Bank Charges" shortcut
  yet.
- `suggest_matches()` matches on exact amount within a date window only
  — no fuzzy matching on description/reference text yet.
- Multi-currency bank accounts are out of scope here — `currency` is
  stored on `BankAccount` for display only; Phase 36 (Multi-Currency and
  Exchange Differences) is where real FX handling belongs.
- Phase 30 (Accounts Receivable and Payable Maturity Management) is next
  per the recommended order — unchanged from Phase 28's notes.

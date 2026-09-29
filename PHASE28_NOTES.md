# PHASE 28 — Fiscal Years, Period Locking and Year-End Close

## 1. Model — `apps/accounting/models.py`

`FiscalYear` gained three fields on top of the existing `start_date` /
`end_date` / `is_closed`:

- `lock_date` (nullable) — ordinary users can't post on/before this date,
  independent of `is_closed`.
- `closed_at`, `closed_by` — set by `close_fiscal_year()`, for display/audit
  convenience (the authoritative record is still `AuditLog`).

Migration: `apps/accounting/migrations/0002_alter_fiscalyear_options_fiscalyear_closed_at_and_more.py`.

`DEFAULT_CHART_OF_ACCOUNTS` gained `3900 Retained Earnings` (equity,
system account). `seed_chart_of_accounts()` already uses
`bulk_create(ignore_conflicts=True)`, so it's safe to call again for
companies that existed before this phase — `close_fiscal_year()` does
exactly that defensively before it needs the account.

## 2. Services — `apps/accounting/services.py`

- `get_fiscal_year_for_date(company, date)` — new helper, the single
  place that resolves "which fiscal year covers this date".
- `post_journal_entry()` — now takes `override_lock: bool = False` and
  raises `ValidationError` when the entry's date falls in a closed
  fiscal year or on/before its `lock_date`, unless `override_lock=True`.
  **Backward compatible**: a company/date with no matching `FiscalYear`
  row posts exactly as before this phase — nothing breaks for existing
  data that predates fiscal-year configuration.
- `close_fiscal_year(*, company, fiscal_year, user)` — the year-end
  close. Computes `profit_and_loss()` for the fiscal year, posts one
  balanced journal entry that zeroes every income/expense account
  active in that year and moves the net profit/loss into Retained
  Earnings (3900), marks the year closed, and writes an `AuditLog`
  entry. **Idempotent**: calling it again on an already-closed year
  returns the original closing entry instead of posting a duplicate.
  Years with zero activity close cleanly with no journal entry at all.
- `reopen_fiscal_year(*, company, fiscal_year, user)` — sets
  `is_closed=False` and writes an `AuditLog` entry. Deliberately does
  **not** auto-reverse the closing entry (see "Known limitations"
  below). Idempotent on an already-open year.
- `balance_sheet()` — fixed to stop double-counting: before this phase
  it recomputed all-time net profit as a bolt-on "retained_earnings"
  figure every time, since there was no closing mechanism. Now that
  `close_fiscal_year()` posts a real entry into the Retained Earnings
  equity account, that account's balance is already included in
  `total_equity` like any other equity account. `retained_earnings` in
  the response now means **only the current, not-yet-closed** fiscal
  year's profit-to-date. Companies with no `FiscalYear` configured for
  the requested date fall back to the old all-time behaviour, so
  nothing breaks for them.

## 3. RBAC — `apps/tenants/services.py`

Two new permissions:

- `accounting.manage_fiscal_years` — create fiscal years, close them.
  Granted to **Owner** and **Accountant** by default.
- `accounting.override_period_lock` — post into a locked/closed period,
  and reopen a closed fiscal year. Granted to **Owner** only — this is
  the "high-privilege override" the phase spec calls for.

**Existing companies** (created before this phase) get these
retroactively via a new data migration —
`apps/tenants/migrations/0004_backfill_fiscal_year_permissions.py` —
so the feature works immediately without a manual fixup script.

## 4. API — `apps/accounting/views.py` + `urls.py`

New `FiscalYearViewSet` at `/api/accounting/fiscal-years/`:

- `GET /` `GET /{id}/` — list/retrieve (`accounting.view_reports`)
- `POST /` — create (`accounting.manage_fiscal_years`)
- `POST /{id}/close/` — close (`accounting.manage_fiscal_years`)
- `POST /{id}/reopen/` — reopen (`accounting.override_period_lock` —
  stricter on purpose)

Tenant-scoped via `.for_company()` as usual — a fiscal year id from
another company 404s before the action body runs.

## 5. Tests — `apps/accounting/tests/test_fiscal_year.py` (18 tests, new file)

Covers: posting allowed with no fiscal year configured (backward
compat), blocked in a closed year, blocked on/before lock_date, allowed
after it, `override_lock` bypassing both checks, a closed prior year not
blocking the next year; year-end close computing correct
profit/loss into Retained Earnings for both a profit and a loss case,
idempotency (no duplicate journal entry on a second close call),
zero-activity years closing without a journal entry, cross-company
rejection; reopen idempotency and audit logging; balance sheet
correctly separating prior (closed, now in Equity) from current
(open) year profit; and API-level RBAC (Owner can close+reopen,
Accountant can close but not reopen, Staff can do neither) plus
cross-tenant 404 on close.

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 183 passed (165 existing + 18 new)
```

## Phase 28 status: complete

## Known limitations / next open items

- `reopen_fiscal_year()` does not reverse the closing journal entry
  automatically — after a reopen, the closing entry from the previous
  close is still sitting in the ledger. Re-closing will correctly
  re-zero the year's accounts again on top of it, but a true "undo the
  close" flow (voiding the specific closing entry) is left for a future
  pass if it turns out to be needed in practice.
- `override_lock=True` is only wired into `close_fiscal_year()` itself
  so far. No other app (sales/purchases/expenses/manual entry) yet has
  a UI/API path that lets an Owner pass `override_lock=True` through to
  `post_journal_entry()` for an ordinary correcting entry into a locked
  period — the permission (`accounting.override_period_lock`) and the
  service-level parameter both exist and are tested, but nothing calls
  them together outside of closing yet.
- Phase 29 (Bank and Cash Management + Reconciliation) — no
  `BankAccount`/reconciliation model exists at all yet, unchanged from
  Phase 27's notes.

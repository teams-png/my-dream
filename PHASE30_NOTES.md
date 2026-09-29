# PHASE 30 — Accounts Receivable and Payable Maturity Management

## 1. New app — `apps/collections`

Models (`apps/collections/models.py`):
- `AgeingBucket` — configurable per company, seeded with the standard
  0-30 / 31-60 / 61-90 / 90+ (days past due) at signup. `max_days=None`
  means open-ended.
- `CollectionNote` — a follow-up note against a customer or supplier,
  optionally tied to a specific invoice/bill.
- `OverdueNotification` — dedup marker, one row per `(document, bucket)`
  already notified on. This is what makes the daily overdue check safe
  to run every day without spamming.

## 2. Model additions to existing apps

- `customers.Customer`: `credit_limit` (0 = no limit), `payment_terms_days` (default 30).
- `suppliers.Supplier`: `payment_terms_days` (default 30).
- `purchases.Purchase`: `due_date` — Purchase never had one before this
  phase (`sales.SalesInvoice` already did).
- `sales.services.create_invoice()` / `purchases.services.create_purchase()`:
  `due_date` now defaults from the customer's/supplier's
  `payment_terms_days` when not passed explicitly — backward compatible,
  no existing caller/test touched `due_date`.

## 3. Services — `apps/collections/services.py`

- **Everything is computed from posted documents** (`SalesInvoice.total`/
  `amount_paid`/`status`, `Purchase` likewise) — never from
  `Customer.opening_balance` or any cached balance field, per the phase's
  explicit rule.
- `ar_ageing_summary()` / `ar_ageing_detail()` and their AP mirrors —
  every non-paid/non-void document is bucketed into exactly one of:
  `not_due` (due date hasn't arrived yet — **never** counted as
  overdue, acceptance criteria), `no_due_date` (legacy rows with no due
  date), one of the configured day-buckets, or `unbucketed_overdue` (a
  safety net if a company's custom bucket config has a gap — so the
  grand total always reconciles no matter how buckets are configured).
- `customer_credit_status()` — reconciled outstanding vs. `credit_limit`.
  **Not wired into `create_invoice()`** — deliberately additive/
  informational only in this phase (see Known limitations).
- `record_collection_note()` — validates exactly one of customer/supplier
  matches `party_type` and belongs to the active company.
- `generate_overdue_notifications()` — the bucket-transition-dedup engine
  behind the fix in section 4 below.

## 4. Fixed: overdue notifications no longer spam daily

`apps.notifications.services.check_overdue_invoices_and_notify()` (called
by the existing Celery beat task and `apps/webapp/views.py` — **no
call-site changes needed**) previously deduped only by "already notified
today", meaning a single overdue invoice generated a fresh notification
every single day until paid — the exact problem this phase's spec calls
out ("without creating duplicates every day"). It now delegates to
`generate_overdue_notifications()`, which notifies once per
`(document, ageing bucket)` — a document sitting in the same bucket for
two weeks notifies once; it only fires again when it escalates into the
next bucket. Also now covers overdue **supplier bills** (AP) via a new
`notify_bill_overdue()`, not just customer invoices.

## 5. RBAC — `apps/tenants/services.py`

Two new permissions: `collections.view` (ageing reports, credit status —
**Owner, Accountant, and Staff**) and `collections.manage` (add
collection notes, edit bucket config — **Owner and Accountant only**).
Existing companies backfilled via
`apps/tenants/migrations/0006_backfill_collections_permissions.py`.
Existing companies' ageing buckets backfilled via
`apps/collections/migrations/0002_backfill_ageing_buckets.py`.

## 6. API — mounted at `/api/collections/`

- `GET/POST /ageing-buckets/` — view/reconfigure the buckets
- `GET /ar-ageing/summary/` `GET /ar-ageing/detail/` (`?as_of=YYYY-MM-DD`)
- `GET /ap-ageing/summary/` `GET /ap-ageing/detail/`
- `GET /customers/{id}/credit-status/`
- `GET/POST /notes/` (`?customer=` / `?supplier=` filters)

## 7. Tests — `apps/collections/tests/test_collections.py` (18 tests, new file)

Covers: due-date defaulting from payment terms for both invoices and
bills; future-due invoices never appearing as overdue; correct bucket
placement; partial payments moving only the remaining balance into
ageing; fully-paid invoices excluded; ageing totals reconciling exactly
with a raw `total - amount_paid` sum computed independently in the test;
AP mirroring AR; credit-limit over/under detection and the
zero-limit-means-unlimited case; cross-tenant credit-status rejection;
collection notes requiring the matching party field and belonging to the
active company; **the notification dedup itself** — same bucket doesn't
re-notify, escalating to the next bucket does; and API-level RBAC (Staff
can view ageing but not create notes) plus default-bucket-seeding
verification via the API.

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 221 passed (203 existing + 18 new)
```

## Phase 30 status: complete

## Known limitations / next open items

- `customer_credit_status()` exists and is queryable via API, but is
  **not enforced** at invoice-creation time — `sales.services.create_invoice()`
  will still happily create an invoice that pushes a customer over their
  credit limit. Whether that should be a hard block, a soft warning, or
  configurable per company is a business decision left for whoever wires
  it in; the check itself is ready to call from that view/service.
- `AgeingBucket` editing has no validation yet against gaps/overlaps
  between buckets — a misconfigured set of buckets is caught at query
  time by the `unbucketed_overdue` safety net (so totals still
  reconcile) rather than being rejected at configuration time.
- Store-credit sales returns (Phase 27) credit Accounts Receivable
  directly but don't update `SalesInvoice.amount_paid` — a pre-existing
  gap from Phase 27, not introduced here, but worth knowing: an invoice
  with a store-credit return against it will still show its pre-return
  outstanding in AR ageing until that's reconciled in a future phase.
- Phase 31 (Advanced Inventory: Batch, Expiry, Serial and Stock Counts)
  is next per the recommended order.

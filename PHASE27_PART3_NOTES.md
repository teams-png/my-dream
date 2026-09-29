# Phase 27 (part 3) — Sales-side record_return API parity

Closes the gap flagged as "still open" at the end of PHASE27_NOTES.md
(part 2): `sales.services.process_return` already existed and was
already exercised from the webapp/Django-template views, but had no DRF
action and no dedicated API-level test coverage — unlike the purchase
side, which part 2 just brought to full parity (service + API + tests).

## Drop-in files (same paths as your existing project root)

```
apps/sales/serializers.py                       (modified)
apps/sales/views.py                              (modified)
apps/sales/tests/test_sales_return_api.py        (new — 5 tests)
```

No model or migration changes — `SalesReturn`/`SalesReturnLine` already
had every field the API needed (`refund_method`, `journal_entry`).

## 1. `apps/sales/serializers.py`

Added `SalesReturnSerializer` (read) and `ProcessReturnInputSerializer` /
`SalesReturnLineInputSerializer` (write) — same shape as
`apps.purchases.serializers`'s equivalents from part 2.

## 2. API — `POST /api/sales/invoices/{id}/record_return/`

Same shape as `record_payment` and as purchases' `record_return` from
part 2: input serializer → IDOR guard (`warehouse`/`product` ids must
belong to `request.company`, same pattern `create()` uses) → the
existing `process_return()` service call. `get_object()` already scopes
`SalesInvoice` to `request.company`, so a cross-tenant invoice id 404s
before the action body runs.

## 3. Tests — `apps/sales/tests/test_sales_return_api.py` (5 tests, new file)

API-level only — happy path, stock reduction through the endpoint,
cross-tenant warehouse/product rejection, and cross-tenant invoice id →
404. Service-level side effects (totals, journal balance) for
`process_return` already had partial coverage via
`apps/inventory/tests/test_non_stock_products.py`; not duplicated here.

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 165 passed (160 existing + 5 new)
```

## Phase 27 status: complete

Both sides (sales and purchases) now have service + API + tests for
returns. Next open items, unchanged from part 2's notes:

- Phase 28 (Fiscal Years, Period Locking, Year-End Close) — `FiscalYear`
  has an `is_closed` flag but nothing in `apps/accounting/services.py`
  enforces it yet.
- Phase 29 (Bank and Cash Management + Reconciliation) — no
  `BankAccount`/reconciliation model exists at all.

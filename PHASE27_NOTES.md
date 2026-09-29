# Phase 27 (part 2) — Purchase-side return processing

Closes a gap that survived every phase since `PurchaseReturn` was first
modeled: the model existed, but there was no service function, no API
endpoint, and no test coverage for it — `apps/purchases/services.py` had
no `process_*_return` counterpart to `sales.services.process_return`, and
`apps/purchases/tests/` didn't exist at all. Found via a full audit of
the repo against the phase-order in the development report — Phase 26
(document numbering, all vertical invoice-linkage parts) turned out to
already be complete and fully tested; this was the actual next open gap,
not what PHASE26_NOTES.md's "still open" section flagged.

Part 1 (sales-side) is unchanged — `sales.services.process_return`
already existed. Wiring a `record_return` DRF action onto
`SalesInvoiceViewSet` for parity (it currently only runs from the
webapp/Django-template views) is still open — natural next chunk if
you want full API parity between sales and purchase returns.

## Drop-in files (same paths as your existing project root)

```
apps/purchases/models.py                                          (modified)
apps/purchases/services.py                                        (modified)
apps/purchases/serializers.py                                     (modified)
apps/purchases/views.py                                           (modified)
apps/purchases/migrations/0003_purchasereturn_journal_entry_and_more.py  (new)
apps/purchases/tests/__init__.py                                  (new)
apps/purchases/tests/test_purchase_return.py                      (new — 11 tests)
```

Run `python manage.py migrate` after dropping these in — one new
migration (`PurchaseReturnLine` model + `refund_method`/`journal_entry`
fields on `PurchaseReturn`, both nullable/defaulted, safe on existing data).

## 1. `apps/purchases/services.py` — `process_purchase_return()`

Mirror of `sales.services.process_return`, opposite direction:

- Adds the returned quantity **back out** of stock (negative
  `StockMovement`, reason `"purchase_return"`) — same
  `is_stock_tracked` guard the rest of the codebase uses, so service
  "products" created by the vertical apps don't get a meaningless
  movement.
- Posts a balanced journal entry reversing the original purchase:
  **Dr Accounts Payable (2000) / Cr Inventory (1200)** when
  `refund_method="supplier_credit"` (the default — most purchase
  returns net off against the next bill rather than a literal cash
  refund), or **Dr Cash (1000) / Cr Inventory (1200)** when
  `refund_method="cash"`.
- Same accepted simplification as the sales side: `total` isn't
  decomposed to reverse the tax portion separately — sales' own
  `process_return` doesn't either, so this stays consistent rather
  than fixing one side of a symmetric gap.
- Wrapped in `@transaction.atomic` — a failed journal-posting step
  rolls back the return row, its lines, and the stock movement
  together (tested via the same `monkeypatch` pattern as
  `test_invoice_flow.py`'s atomicity test).

## 2. API — `POST /api/purchases/purchases/{id}/record_return/`

Same shape as the existing `record_payment` action: input serializer,
then the same IDOR guard `create()` uses (`warehouse`/`product` ids must
belong to `request.company`), then the service call. `get_object()`
already scopes `Purchase` to `request.company`, so a cross-tenant
purchase id 404s before the action body ever runs — verified by test.

## 3. Tests — `apps/purchases/tests/test_purchase_return.py` (11 tests, new file)

Covers: totals/lines, stock decrement, balanced journal entry for both
`refund_method` values (asserted via `account_balance()` on AP/Inventory/
Cash, not just "a journal entry exists"), the non-stock-tracked skip,
atomicity on a simulated journal-posting failure, and three API-level
cases (happy path, cross-tenant warehouse, cross-tenant product,
cross-tenant purchase id → 404).

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 160 passed (149 existing + 11 new)
```

## Still open, next

- Wire `record_return` onto `SalesInvoiceViewSet` too (service already
  exists, API action doesn't) — closes the same gap Phase 27 just closed
  for purchases, on the sales side.
- Phase 28 (Fiscal Years, Period Locking, Year-End Close) — `FiscalYear`
  has an `is_closed` flag but nothing in `apps/accounting/services.py`
  enforces it; `post_journal_entry()` will happily post into a closed
  period.
- Phase 29 (Bank and Cash Management + Reconciliation) — no
  `BankAccount`/reconciliation model exists at all yet; Cash (1000) and
  Bank (1010) are plain chart-of-accounts entries with no reconciliation
  workflow behind them.

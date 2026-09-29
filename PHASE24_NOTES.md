# Phase 24 — Non-stock product distinction + bugs found while verifying

Picks up after Phase 23 (spa invoice linkage). Started as the "non-stock
product" fix both Phase 22 and Phase 23 flagged as their obvious next
item; running the full suite to verify it surfaced three more real,
pre-existing bugs, fixed here too (same "verify before/after, fix what
you find" process Phase 20-22 used).

## Drop-in files (same paths as your existing project root)

```
apps/inventory/models.py                                             (modified — Product.is_stock_tracked)
apps/inventory/migrations/0004_product_is_stock_tracked.py           (new)
apps/inventory/tests/__init__.py                                     (new)
apps/inventory/tests/test_non_stock_products.py                      (new)

apps/sales/services.py                                               (modified — skip StockMovement for non-tracked products)
apps/reports/services.py                                             (modified — stock_report excludes non-tracked products)
apps/reports/views.py                                                (modified — see Bug 1)
apps/notifications/services.py                                       (modified — low-stock sweep excludes non-tracked products)

apps/verticals/gym/services.py                                       (modified — create_membership_plan marks its product non-stock)
apps/verticals/gym/migrations/0003_mark_membership_products_non_stock.py   (new — data migration for existing rows)

apps/verticals/spa/services.py                                       (modified — same, for SpaService/ServicePackage)
apps/verticals/spa/migrations/0003_mark_service_products_non_stock.py     (new)
apps/verticals/spa/tests/test_appointment_invoicing.py               (modified — see Bug 3)

apps/subscriptions/middleware.py                                     (modified — see Bug 2)
```

Run `python manage.py migrate` after dropping these in.

## 1. Non-stock / service product distinction

`Product` gained `is_stock_tracked` (default `True`). When `False`:

- `sales.services.create_invoice()` and `process_return()` skip writing a
  `StockMovement` for that line — a membership or session invoiced through
  the normal sales path no longer drifts `current_stock()` negative.
- `reports.services.stock_report()` excludes it — a gym membership no
  longer shows up as a "product" with negative stock in the stock report.
- `notifications.services.check_low_stock_and_notify()` excludes it — no
  more spurious "low stock" notifications for services.

`gym.services.create_membership_plan()` and `spa.services.create_spa_service()`
/ `create_service_package()` now create their linked Product with
`is_stock_tracked=False`. Two data migrations backfill existing rows
created before this field existed.

**Verified**: `apps/inventory/tests/test_non_stock_products.py` (7 tests) —
invoicing a non-stock product writes no `StockMovement`, a tracked product
still does, returns follow the same rule, `stock_report` excludes
non-stock products, the low-stock sweep doesn't fire for one at 0 stock /
0 reorder level, and both gym's and spa's product-creation helpers mark
their products correctly.

## Bugs found while verifying (running `pytest` + `manage.py check` before/after, same as every phase since 20)

**Bug 1 — `apps/reports/views.py` imported P&L and Balance Sheet from the
wrong module.** `ProfitAndLossView`/`BalanceSheetView` called
`services.profit_and_loss(...)` / `services.balance_sheet(...)` —
but those functions live in `apps.accounting.services` (they read the
ledger directly), not `apps.reports.services` (Section 5's cross-app
aggregation module) — `apps/reports/services.py` never had them. Every
call to `GET /api/reports/profit-and-loss/` or `/balance-sheet/` was a
500. Fixed by importing both from `apps.accounting.services`, same as
the file already did for `trial_balance`. This is very likely the same
class of reassembly-order issue Phase 22's "Bug 0" flagged (an older
snapshot's `views.py` and a newer `services.py`, or vice versa, getting
mixed) — worth keeping in mind for the next reassembly.

**Bug 2 — `SubscriptionGuardMiddleware._is_usable()` ignored `status`
entirely**, checking only `end_date >= today`. A subscription explicitly
marked `"expired"` or `"cancelled"` (by an admin action, a payment-webhook
handler, or — how this was caught — a test setting `status` directly)
with an `end_date` still in the future kept granting full access. Fixed
to treat `status in ("expired", "cancelled")` as unusable outright, date
check unchanged as the fallback for the case the file's own docstring
already covers (status not yet flipped by the daily Celery task).

**Bug 3 — `apps/verticals/spa/tests/test_appointment_invoicing.py`'s own
`spa_fixtures` fixture created its `Employee` with `position="Therapist"`
— the model's actual field is `role_title`.** Every test in that file
errored at fixture setup. Fixed the one line; no behavior changed in
`apps.employees` or `apps.verticals.spa` itself.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 80 passed (74 from Phase 23 + 1 renamed-field fix
                                            #   revealing 10 previously-erroring spa tests + 7 new)
```

## Still open — found today, not fixed here (scope)

- **`apps/reports/services.py` is missing most of what `apps/reports/views.py`
  actually calls.** Beyond the two functions Bug 1 fixed, `views.py` also
  calls `services.cash_flow`, `services.purchase_report`,
  `services.expense_report`, `services.tax_report`, `services.stock_valuation`
  — none of which exist in `reports/services.py` — and calls
  `services.customer_outstanding` / `services.supplier_outstanding` where
  the actual functions are named `customer_outstanding_report` /
  `supplier_outstanding_report` and return a different shape (`rows`/
  `total_outstanding` vs. what the view expects: a `"customers"`/`"suppliers"`
  key). `sales_report()` is also missing the `customer_id` filter and
  `"by_status"` key the view passes/expects, and `stock_report()`'s `"rows"`
  key doesn't match the view's `data["products"]`. **No test currently
  exercises any of these six report types**, which is why `pytest` stayed
  green through all of this — same blind spot Phase 20's own notes flagged
  for the untested verticals. This is a real, separate reassembly-mismatch
  bug (same shape as Bug 1, just bigger) and deserves its own reviewed
  phase rather than a rushed fix bundled into this one.
- The 6-vertical invoice-linkage gap flagged earlier this session (saloon,
  textile, vehicle_wash, cycle_shop, medical_shop, protein_shop never
  actually call `create_invoice()` despite their own docstrings saying they
  should) — unchanged, still open.
- Everything Phase 22/23 already flagged as open (CompanyCounter true
  concurrency test, `general_retail` not a separate vertical) — unchanged.

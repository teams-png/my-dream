# Phase 25 — Reports engine: fill in the missing functions, wire the missing URLs, fix the missing renderer

Picks up the two "Still open" items PHASE24_NOTES.md flagged for
`apps/reports`: `services.py` was missing most of what `views.py` calls,
and none of the six report types were exercised by any test — which is
exactly why the gap went unnoticed through every phase since the views
were written. Fixed all of it, then found two more bugs the new tests
surfaced that PHASE24's notes didn't know about.

## Drop-in files (same paths as your existing project root)

```
apps/reports/services.py                              (rewritten)
apps/reports/views.py                                  (modified — see Bug 2)
apps/reports/urls.py                                    (modified — see Bug 1)
apps/reports/tests/__init__.py                         (new)
apps/reports/tests/test_reports.py                     (new — 24 tests)
apps/inventory/tests/test_non_stock_products.py        (modified — one key rename, see below)
```

Run `python manage.py check` after dropping these in — no new migrations.

## 1. `apps/reports/services.py` was missing/mismatched, same class of bug as Phase 24's Bug 1

`views.py` called six functions that didn't exist in `services.py` at
all — `cash_flow`, `purchase_report`, `expense_report`, `tax_report`,
`stock_valuation` — plus three more it called under a different name or
expecting a different shape:

- `sales_report(company, date_from, date_to)` existed but didn't accept
  `customer_id` (the view passes it) and had no `"by_status"` key (the
  view's CSV export reads `data["by_status"]`). Added both.
- `stock_report(company, warehouse)` took a `Warehouse` object; the view
  passes `warehouse_id` (a query-string value) straight through. Added
  `_resolve_warehouse()` to look it up. Also returned `"rows"`; the view
  reads `data["products"]`. Renamed.
- `customer_outstanding_report()` / `supplier_outstanding_report()`
  existed under those names with a `"rows"` key; the view calls
  `services.customer_outstanding()` / `services.supplier_outstanding()`
  and reads `data["customers"]` / `data["suppliers"]`. Renamed both
  functions and their return key.

Wrote the five missing functions from scratch, following the same
"never re-derive from a stored total, read the source of truth" principle
the rest of the app uses:

- `purchase_report` / `expense_report` mirror `sales_report`'s shape
  (totals + a breakdown list + a detail list), scoped and filtered the
  same way.
- `tax_report` sums `tax_amount` from non-void `SalesInvoice`s vs.
  `Purchase`s over the period — output tax vs. input tax, net payable.
- `stock_valuation` reuses `stock_report`'s new `_stock_rows()` helper,
  company-wide (no warehouse filter) — "how much is tied up in inventory
  overall," as a report in its own right rather than a duplicate of
  `stock_report`.
- `cash_flow` reads `JournalLine` activity on the Cash (1000) and Bank
  (1010) accounts only, grouped by the journal entry's `source_type` —
  never re-summed from `SalesInvoice.amount_paid` or similar, same
  ledger-is-truth principle as `accounting.services.profit_and_loss`.
  Confirmed by test that an invoice alone (posts to Accounts Receivable)
  has zero cash-flow footprint until a `CustomerPayment` is actually
  recorded against it — that distinction is the whole point of the
  report and is exactly the kind of thing that silently rots without a
  test.

Also fixed two tenant-scoping convention violations while in this file:
`customer_outstanding`'s and `supplier_outstanding`'s `SalesInvoice`/
`Purchase` queries filtered by `customer=`/`supplier=` alone, without the
`.for_company(company)` the rest of the codebase's convention requires
(Phase 0 Section 3). Not an active data leak — a Purchase's supplier FK
can't point outside its own company — but worth closing while touching
the file, same as any other convention-checklist item.

## 2. Bug found while writing tests — `?format=csv` 404'd on every report, always

Not something PHASE24's notes could have flagged (it's independent of
the services.py content), and only surfaced because
`TestCsvExport.test_csv_export_succeeds` actually hit the endpoints with
`?format=csv` for the first time. Traced with a monkey-patched exception
handler:

```
django.http.response.Http404
  rest_framework/views.py, initial() -> perform_content_negotiation()
  rest_framework/negotiation.py, select_renderer() -> filter_renderers()
    raise Http404
```

DRF's own content negotiation raises `Http404` — not `NotAcceptable`,
despite what the docs might suggest — when `?format=` names a format that
no renderer in the view's `renderer_classes` declares. `BaseReportView`
never set `renderer_classes`, so it used DRF's default (JSON +
Browsable API only); `csv` matched neither, and the request 404'd inside
`dispatch()`'s `initial()` step, before `get()` — and therefore
`_maybe_export()` — ever ran. Every report's CSV export has been dead on
arrival since it was written; nothing before this phase's tests ever
called a report endpoint with `?format=csv`.

Fixed by adding a `_CSVFormatRenderer` (a `BaseRenderer` subclass
declaring `format = "csv"`) to `BaseReportView.renderer_classes`,
alongside the two DRF defaults. Its own `.render()` is never actually
called — `_maybe_export()` still builds and returns the real CSV
`HttpResponse` itself — the renderer exists purely to get past content
negotiation.

## 3. `apps/reports/urls.py` only wired 7 of the 12 views that exist

`CashFlowView`, `PurchaseReportView`, `ExpenseReportView`,
`TaxReportView`, and `StockValuationView` were fully implemented in
`views.py` but had no `path()` entry — unreachable regardless of
anything in `services.py`. Added all five
(`cash-flow/`, `purchases/`, `expenses/`, `tax/`, `stock-valuation/`).

## 4. Correction to PHASE24_NOTES.md's "6-vertical invoice-linkage gap"

Checked this myself while scoping Phase 25 (it's the same file family):
it's **8** verticals with a `create_invoice()` TODO left unimplemented,
not 6. `beauty_parlour.services.purchase_package()` and
`mobile_shop.services.sell_unit()` have the identical gap (explicit TODO
comment/docstring, no actual call) but weren't named in Phase 24's list
alongside saloon/textile/vehicle_wash/cycle_shop/medical_shop/
protein_shop. `sports_shop` has no `services.py` at all — it's a thin
`Product` extension with no sale-recording model of its own, so it
doesn't have this gap; it isn't a 9th case. Still open, scoped for the
next phase.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 104 passed (80 from Phase 24 + 24 new reports tests)
```

## Still open — not fixed here (scope)

- The 8-vertical invoice-linkage gap (corrected count above) — next phase.
- CompanyCounter true concurrency test (Phase 22/23's open item, unchanged).
- `general_retail` not a separate vertical (Phase 22/23's open item, unchanged).
- Repo housekeeping: a batch of empty stray files at the project root
  (`WARNING`, `Watching`, `Django`, `python`, `pip`, `cd`, `dir`, `tar`,
  `copy`, `findstr`, `migrations`, `26.2.1`, `For`, `Performing`, `Quit`,
  `September`, `Starting`, `System`) that look like a Windows shell
  command's words each became their own empty file, a
  `templates/webapp/{sports_shop,cycle_shop,saloon,beauty_parlour,`
  `medical_shop,protein_shop,construction}` directory literally named
  with unexpanded shell braces (all seven real vertical template folders
  already exist separately alongside it), and `phase24-drop-in.zip`
  sitting in the project root after already being applied. None of this
  affects the app; worth a five-minute cleanup pass whenever convenient.

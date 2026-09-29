# PHASE 31 — Advanced Inventory: Batch, Expiry, Serial and Stock Counts

## 1. Model additions — `apps/inventory/models.py`

- `Product.tracking_type` — `none` / `basic` / `batch` / `serial`. Default
  `"basic"` for every existing product post-migration, which is exactly
  the pre-Phase-31 behaviour (aggregate quantity only) — nothing changes
  for a product that doesn't opt in.
- `Product.block_expired_batch_sale` (default `True`) — the configurable
  "policy" the acceptance criteria refers to.
- `ProductBatch` — a lot/batch, `unique_together (company, product, batch_number)`.
  No stored quantity — stock in a batch is always summed live from
  `StockMovement` rows carrying that batch, same append-only-ledger
  principle as `Product.current_stock()`.
- `ProductSerial` — one physical unit, `unique_together (company, product, serial_number)`,
  with a `status` (`in_stock`/`sold`/`returned`) that's the actual
  mechanism behind "serial number cannot be sold twice".
- `StockMovement.batch` / `StockMovement.serial` — both nullable FKs
  added to the **existing** model. Every pre-Phase-31 row has both NULL
  and keeps working exactly as before — `current_stock()` still just
  sums `quantity` regardless. New `"stock_count"` reason added to the
  choices list.
- `StockCount` / `StockCountLine` — a physical count session per
  warehouse, snapshotting `system_quantity` at start.
- `BatchAlertLog` — dedup marker (one row per `(batch, alert_type)` ever)
  so expiry notifications don't repeat daily — same fix pattern as
  Phase 30's overdue-invoice spam, applied here from the start instead
  of shipping the same bug twice.
- `sales.SalesInvoiceLine` / `SalesReturnLine` gained nullable
  `batch`/`serial` FKs so a return can restore stock to the same batch/
  serial the original sale used.

## 2. Services — `apps/inventory/services.py`

- `create_batch()`, `receive_batch_stock()`, `available_batch_quantity()`
  — the last one is the literal "batch stock reconciles by warehouse"
  figure, always derived live.
- `suggest_fefo_batches()` — orders a product's batches with stock in a
  warehouse by `expiry_date` ascending. **Read-only, changes nothing** —
  the FEFO "suggestion only" rule. A caller still has to pass an
  explicit `batch=` to actually sell from it.
- `validate_batch_availability()` / `sell_batch_stock()` — rejects
  selling more than available, and (when `block_expired_batch_sale` is
  True, the default) rejects selling an expired batch outright.
- `register_serial()`, `validate_serial_availability()`,
  `sell_serial_stock()` (flips status inside the same transaction as the
  stock movement — this is what makes "serial number cannot be sold
  twice" airtight even under a race), `restore_serial_stock()`.
- `create_stock_transfer()` — one call posts both `transfer_out` and
  `transfer_in` rows; company-wide total stock is provably unchanged
  (tested), only its warehouse location moves.
- `create_stock_adjustment()` — a direct manual correction, always
  writes an `AuditLog` entry.
- `start_stock_count()` / `submit_stock_count_line()` /
  `complete_stock_count()` — snapshot → count → reconcile. Completing
  posts one `StockMovement` per line with a non-zero variance and writes
  **one `AuditLog` entry summarizing every variance** (acceptance
  criteria: "stock-count adjustment leaves an audit trail"). Rejects
  completing an already-completed count.
- `check_batch_expiry_and_notify()` — dedup via `BatchAlertLog`; a batch
  with stock on hand notifies once when it enters the near-expiry
  window and once when it actually expires, never daily. Wired into the
  same Celery beat task and `webapp/views.py` call site as Phase 30's
  overdue check — no new call sites needed.

## 3. Sales integration — `apps/sales/services.py`

- `create_invoice()` lines may now include an optional `"batch"` or
  `"serial"` key. When present and the product's `tracking_type` matches,
  the line sells through `sell_batch_stock()` / `sell_serial_stock()`
  (full validation); when absent, it falls back to the exact pre-Phase-31
  `record_stock_movement()` call — **zero behavior change** for every
  existing caller across all 12 verticals that doesn't pass batch/serial.
- `process_return()` accepts the same optional keys per line, and when a
  line doesn't specify one, it looks up the matching `SalesInvoiceLine`
  for that product on the invoice and reuses whatever batch/serial it
  recorded — "restore the correct batch/serial where possible" per the
  spec's own hedge.

## 4. API — mounted under `/api/inventory/`

New: `GET/POST /batches/` (`?product=`), `GET /serials/` (`?product=&status=`,
read-only — serials are created via `register_serial()`, not a generic
POST), `GET/POST /stock-counts/` + `/stock-counts/{id}/lines/{line_id}/`
+ `/stock-counts/{id}/complete/`, `POST /stock-transfer/`,
`POST /stock-adjustment/`. All gated behind the **existing**
`inventory.manage_stock` / `inventory.view_products` permissions — no
new permission codes, no backfill migration needed for this phase.

## 5. Tests — `apps/inventory/tests/test_advanced_inventory.py` (23 tests, new file)

Covers all four acceptance criteria directly: batch stock reconciling
per-warehouse across two warehouses; insufficient and expired batches
both rejected (and the expired case allowed through when the product's
policy permits it); a serial rejected on a second sell attempt and on
duplicate registration; stock-count completion reconciling stock and
writing an audit-log entry, plus rejecting a second completion and
correctly skipping uncounted lines. Also: FEFO ordering without state
mutation, full sales-integration round trips (sell from a specific
batch → return without specifying one → restored to the right batch;
sell a serial → reselling it blocked), transfers leaving company-wide
total stock unchanged, expiry-notification dedup, and API-level
permission/tenant-isolation checks.

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 244 passed (221 existing + 23 new)
```

## Phase 31 status: complete

## Known limitations / next open items

- `StockCount` counts at the **product** level, not per-batch — a
  batch-tracked product's physical count doesn't currently let you
  reconcile individual batches separately, only the product's total in
  that warehouse. Per-batch counting is a natural follow-up if a
  protein/medical business needs it.
- No dedicated bin/shelf-location field yet (spec mentions
  "warehouse/bin location") — `Warehouse` is still the finest location
  granularity; a `bin_location` field on `StockMovement` or a new
  `Bin` model would be the next step.
- Serial-tracked products aren't included in `start_stock_count()`
  snapshots by product-quantity — a serial audit (confirming which
  specific units are physically present) is a different workflow than
  a quantity count and hasn't been built here.
- Phase 32 (Purchase Order → Goods Receipt → Supplier Bill Workflow) is
  next per the recommended order.

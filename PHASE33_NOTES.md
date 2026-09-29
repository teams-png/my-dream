# PHASE 33 — Sales Quotation → Sales Order → Delivery → Invoice Workflow

## 1. New models — `apps/sales/models.py`

The sales-side mirror of Phase 32's PO→GRN→Bill flow:

- `Quotation` extended: `created_by`, `created_at`. **Never posts a
  journal entry** — it's a proposal, not a financial event.
- `QuotationLine` — the quoted lines. `unit_price` here is copied
  verbatim onto a `SalesOrderLine` on conversion, preserving the
  customer's quoted price exactly (acceptance criteria: "preserve
  original quoted prices/discounts").
- `SalesOrder` extended: `reference`, `created_by`, `created_at`, and
  `status` gained `partially_delivered` alongside the existing choices
  (the old `fulfilled` was renamed to `delivered` for symmetry with
  Phase 32's `PurchaseOrder.received`). **Never posts a journal entry**
  either.
- `SalesOrderLine` — no stored delivered/invoiced counters; both are
  always computed live from `DeliveryLine` and `SalesInvoiceLine` rows
  (`delivered_quantity()` / `invoiced_quantity()` in services.py), same
  principle as everywhere else in this codebase.
- `DeliveryNote` / `DeliveryLine` — the actual stock-issue point for the
  order-based flow. Multiple delivery notes per order support partial
  delivery. **No accounting entry posted here either** — this system
  never posted COGS on sale (see `accounting.services` docstrings), so
  revenue/AR recognition stays entirely at invoice time, matching the
  existing direct `create_invoice()` flow's behaviour.
- `SalesInvoiceLine` gained an optional `so_line` FK — both to trace a
  bill back to its order line, and to tell `create_invoice()` this
  line's stock already left at delivery time.

## 2. The no-double-decrement fix — `apps/sales/services.py`

`create_invoice()`'s existing stock-movement loop got one new guard: a
line carrying a `so_line` skips the stock movement entirely (the
delivery already moved it). This is the **entire** mechanism behind
"no double stock decrement occurs" — nothing else about
`create_invoice()` changed, so the **direct invoice flow used by every
vertical remains completely unaffected** (verified directly by a test).

## 3. New services

- `create_quotation()`, `send_quotation()`, `accept_quotation()`,
  `reject_quotation()` — status lifecycle, no ledger/stock impact.
- `create_sales_order()` — either pass `lines` directly, or pass an
  `accepted` `quotation` and let it copy lines (and prices) verbatim.
  Rejects converting a quotation that isn't `accepted`.
- `confirm_sales_order()` / `cancel_sales_order()` — approval gate;
  nothing can be delivered against a `draft` order.
- `create_delivery()` — posts a stock movement per line (new
  `StockMovement` reason `delivery`, added to the existing choices
  without touching pre-Phase-33 rows). Rejects delivering more than
  `ordered − already_delivered` per line unless `allow_over_delivery=True`
  — gated behind the new `sales.override_delivery_limits` permission.
  Auto-advances order status (`confirmed` → `partially_delivered` →
  `delivered`).
- `create_invoice_from_order()` — delegates to `create_invoice()` for
  the actual accounting entry, after validating the billed quantity
  doesn't exceed `delivered − already_invoiced` per line (same override
  permission for `allow_over_invoicing`). This is what makes the
  "conversion chain traceable": `SalesInvoice.sales_order` +
  `SalesInvoiceLine.so_line` both get set.

## 4. RBAC

One new permission: `sales.override_delivery_limits` — **Owner only** by
default, mirroring Phase 32's `purchases.override_receiving_limits`.
Existing companies backfilled via
`apps/tenants/migrations/0008_backfill_so_override_permission.py`.
Everything else reuses `sales.create_invoice` / `sales.view_invoice`.

## 5. API — mounted under `/api/sales/`

- `GET/POST /quotations/` + `/send/` `/accept/` `/reject/` actions
- `GET/POST /orders/` (nested `lines` show live `delivered_quantity`/
  `invoiced_quantity`) + `/confirm/` `/cancel/` `/deliver/` `/invoice/`
  actions (`allow_over_delivery`/`allow_over_invoicing` need the
  override permission, rejected with 403 otherwise)
- `GET /deliveries/` (`?sales_order=`) — read-only, created only via the
  `deliver` action above

## 6. Tests — `apps/sales/tests/test_quotation_order_delivery_workflow.py` (20 tests, new file)

Covers all four acceptance criteria directly: the direct `create_invoice()`
path completely unaffected; a sales order supporting partial delivery
across two delivery notes and partial invoicing across two invoices,
reconciling exactly to the ordered/delivered quantities; invoicing a
delivered line provably not moving stock a second time (checked before
and after); and the full chain traceable from invoice back to order line.
Also: quotation/order posting zero journal entries, quoted-price
preservation on conversion, rejecting conversion of an unaccepted
quotation, the draft-order-blocks-delivery gate, over-delivery/
over-invoicing both rejected by default and both explicitly allowed with
the override flag, cross-order-line rejection, and API-level RBAC
(Owner can run the full flow, Staff blocked from the override).

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 282 passed (262 existing + 20 new)
```

## Phase 33 status: complete

## Known limitations / next open items

- Discounts aren't modeled on `QuotationLine`/`SalesOrderLine` yet
  (only price) — "preserve original quoted prices/discounts" is
  satisfied for price; a dedicated discount field would be a small
  follow-up if quote-level discounts need to survive conversion too.
- No partial-quantity audit-trail note beyond the permission gate for
  over-delivery/over-invoicing, same known limitation as Phase 32's GRN
  override.
- `DeliveryNote` is one warehouse per note, same limitation as Phase
  32's `GoodsReceiptNote`.
- Phase 34 (Full POS Module) is next per the recommended order.

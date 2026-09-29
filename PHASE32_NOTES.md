# PHASE 32 — Purchase Order → Goods Receipt → Supplier Bill Workflow

## 1. New models — `apps/purchases/models.py`

- `PurchaseOrder` extended: `reference`, `created_by`, `created_at`, and
  `status` gained `partially_received` alongside the existing choices.
  **Never posts a journal entry** (acceptance criteria: "PO does not
  change ledger") — creating one is a pure record-keeping action.
- `PurchaseOrderLine` — the ordered lines. No stored "received"/"billed"
  counters — both are always computed live from `GoodsReceiptNoteLine`
  and `PurchaseLine` rows respectively (`received_quantity()` /
  `billed_quantity()` in services.py), same append-only-ledger principle
  used everywhere else in this codebase.
- `GoodsReceiptNote` / `GoodsReceiptNoteLine` — one delivery event
  against a PO. Multiple GRNs per PO support partial receiving.
- `PurchaseLine` gained an optional `po_line` FK so a bill line can be
  traced back to exactly which PO line it settles.

## 2. New account — `apps/accounting/services.py`

`2050 Goods Received Not Invoiced (GRNI)` added to
`DEFAULT_CHART_OF_ACCOUNTS` — the "clearly documented accrued account"
the phase spec calls for, used instead of touching Accounts Payable or
inventing a fake expense before the real bill arrives. Existing
companies get it automatically the first time a GRN or PO-bill posts,
via the same defensive `seed_chart_of_accounts(company)` pattern Phase
28 used for the Retained Earnings account.

## 3. Services — `apps/purchases/services.py`

Added as a **separate flow alongside** the existing `create_purchase()`
— that direct "cash and carry" bill-with-no-PO path is untouched and
still works exactly as before for businesses that don't need PO
approval.

- `create_purchase_order()` — creates the PO + lines only. No stock
  movement, no journal entry.
- `confirm_purchase_order()` / `cancel_purchase_order()` — the approval
  gate; nothing can be received against a `draft` PO.
- `create_goods_receipt()` — the GRN. Debits Inventory (1200), credits
  GRNI (2050) for the receipt's value; posts a stock movement per line
  (new `StockMovement` reason `goods_receipt`, distinct from a direct
  `purchase` bill's movement, added to the existing choices list without
  touching any pre-Phase-32 rows). Rejects receiving more than
  `ordered − already_received` per line unless `allow_over_receipt=True`
  — a controlled override the API only grants to a role holding the new
  `purchases.override_receiving_limits` permission. Auto-advances the
  PO's status (`confirmed` → `partially_received` → `received`) based on
  live received-vs-ordered totals.
- `create_bill_from_grn()` — posts the final liability (acceptance
  criteria: "supplier bill posts the final accounting liability"): Dr
  GRNI, Cr Accounts Payable (+ Tax Payable, mirroring the exact tax
  convention `create_purchase()` already uses, for consistency rather
  than inventing a second tax model — full input-tax handling is Phase
  37's job). **Never moves stock again** — that already happened at GRN
  time. Rejects billing more than `received − already_billed` per line
  unless `allow_over_billing=True`, same override permission.

## 4. RBAC

One new permission: `purchases.override_receiving_limits` — **Owner
only** by default (the "controlled override" the spec calls for).
Existing companies backfilled via
`apps/tenants/migrations/0007_backfill_po_override_permission.py`.
Everything else reuses the existing `purchases.create_purchase` /
`purchases.view_purchase` codes.

## 5. API — mounted under `/api/purchases/`

- `GET/POST /purchase-orders/` (with nested `lines`, each showing live
  `received_quantity`/`billed_quantity`)
- `POST /purchase-orders/{id}/confirm/` `POST /purchase-orders/{id}/cancel/`
- `POST /purchase-orders/{id}/receive/` — creates a GRN
  (`allow_over_receipt` requires the override permission, checked and
  rejected with 403 otherwise)
- `POST /purchase-orders/{id}/bill/` — creates a bill from received
  quantities (`allow_over_billing` same permission gate)
- `GET /goods-receipts/` (`?purchase_order=`) — read-only, GRNs are only
  ever created via the `receive` action above

## 6. Tests — `apps/purchases/tests/test_po_grn_bill_workflow.py` (18 tests, new file)

Covers all four acceptance criteria directly: a PO posting zero journal
entries; partial receiving across two GRNs correctly advancing PO status
and reconciling `received_quantity()`; over-receipt and over-billing
both rejected by default and both explicitly allowed with the override
flag; and the full receipt→bill reconciliation — GRNI exactly cleared,
AP exactly raised, Inventory touched only once (at receipt, never again
at billing), stock physically increasing only at receipt. Also: the
draft-PO-blocks-receiving gate, confirm/cancel lifecycle, partial
billing split across two bills reconciling to the full received
quantity, cross-PO-line rejection (tenant/document isolation), and
API-level checks (Owner can run the full flow, Accountant blocked from
using the override).

## Verified

```
python manage.py check                    → 0 issues
python manage.py makemigrations --check   → no changes detected
pytest                                     → 262 passed (244 existing + 18 new)
```

## Phase 32 status: complete

## Known limitations / next open items

- Tax handling in `create_bill_from_grn()` mirrors `create_purchase()`'s
  existing simplification (tax folds into the GRNI debit rather than a
  fully decomposed input-tax model) rather than introducing a different
  convention just for this flow — real configurable tax handling is
  explicitly Phase 37's job.
- No partial-quantity "over-receipt requires a note/reason" audit trail
  yet beyond the permission gate itself — if that's needed later it's a
  small addition alongside the existing `AuditLog` pattern used in
  Phases 28/31.
- `GoodsReceiptNote` doesn't yet support receiving into a *different*
  warehouse per line within the same GRN — one warehouse per receipt
  note. Multi-warehouse-per-GRN would need per-line warehouse fields.
- Phase 33 (Sales Quotation → Sales Order → Delivery → Invoice Workflow)
  is next per the recommended order — the sales-side mirror of this
  phase.

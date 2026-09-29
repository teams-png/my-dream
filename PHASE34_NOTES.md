# Phase 34 — Full POS Module

Phase 34 adds a tenant-scoped POS service and API on top of the existing sales, inventory,
payment and accounting engines. A POS checkout creates exactly one normal `SalesInvoice`,
uses normal `CustomerPayment` rows for cash/card/bank or split payment, and records a
traceable POS receipt. It does not create a second revenue or stock ledger.

Implemented:

- Cashier shift open/close with opening, expected and counted cash plus variance.
- Cash-in and cash-out records with reason and user audit fields.
- Held carts that do not post stock or accounting, and safe resume/checkout.
- Walk-in or selected customer checkout.
- Split cash/card/bank payments that must reconcile exactly to the invoice total.
- Sequential tenant-safe POS receipt numbers.
- Stock validation before checkout; non-stock products remain supported.
- Card/bank payments post to Bank while cash payments post to Cash.
- POS API actions under `/api/sales/pos/` for shift, cart, checkout, cash movement,
  closing and receipt retrieval.

Verification:

```text
python manage.py check                    0 issues
python manage.py makemigrations --check   no changes detected
pytest                                    288 passed
```

Phase 34 status: complete. Phase 35 is the next roadmap phase.

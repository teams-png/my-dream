# Phase 36 — Multi-Currency and Exchange Differences

Implemented company-base and transaction-currency accounting without float arithmetic.

- Effective-dated exchange-rate table with source and manual-rate flag.
- Foreign-currency sales invoices and purchases preserve transaction and base amounts.
- Base-currency journal posting for invoices and purchases.
- Foreign-currency customer settlement with realized exchange gain/loss.
- New system accounts: Realized Exchange Gain (4050) and Loss (5150).
- Exchange-rate API under `/api/sales/exchange-rates/`.
- Base-currency transactions retain rate 1 and their previous behaviour.
- Missing or invalid exchange rates fail explicitly.
- Unrealized revaluation is intentionally deferred; no approximation is posted.

Verification: Django check passed, migrations clean, and 296 tests passed.

Phase 36 status: complete. Phase 37 (configurable tax engine) is next.

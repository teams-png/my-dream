# Phase 35 — Pricing, Discounts, Loyalty and Promotions

Phase 35 extends the shared sales and POS engines with controlled commercial pricing rules.

Implemented:

- General and customer-specific price lists with effective dates, priority and active status.
- Scheduled product or order-wide promotions with percentage/fixed discounts.
- Deterministic precedence: customer price list, general price list, product price, then the
  highest-priority active promotion; stable record ordering resolves equal priorities.
- Manual discount reasons and configurable approval threshold.
- `sales.approve_discount` permission, assigned to Owner by default and backfilled safely.
- Configurable loyalty earn rate, redemption value and enable/disable setting.
- Loyalty redemption creates no separate journal entry; its financial effect is recorded as
  the invoice discount through the existing accounting engine.
- POS ignores client-supplied prices and resolves current server-side commercial prices.
- Price-list, promotion and commercial-settings APIs under `/api/sales/`.

Verification:

```text
python manage.py check                    0 issues
python manage.py makemigrations --check   no changes detected
pytest                                    292 passed
```

Phase 35 status: complete. Phase 36 (multi-currency and exchange differences) is next.

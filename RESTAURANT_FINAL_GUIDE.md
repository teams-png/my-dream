# Restaurant edition

This archive contains the full BookPilot project: platform owner console, tenant management, POS, cashier, customer QR menu, kitchen display, reporting and the restaurant improvements.

## Sample menu

Sign in as the restaurant tenant owner. Open **Restaurant Dashboard → Restaurant Setup → Add sample dishes**. This adds 20 optional demo dishes in 11 categories, with illustrated images, descriptions and example prices in the company's currency. The button can be used again after an earlier six-item demo; only missing items are added. Existing products, menu details and edited prices are preserved. Review item details, prices and availability before serving customers.

## Restaurant flow

1. Create a restaurant/cafe client from the platform admin console.
2. Restaurant Dashboard → New Order: choose dine-in, takeaway or delivery.
3. Cashier POS: choose category or search, add dishes and modifiers, then send to kitchen.
4. Kitchen Display: queued → preparing → ready → served.
5. Customer Menu: open the secure QR link in Restaurant Setup. Enable QR ordering in menu settings if customers should place orders themselves.
6. A persistent restaurant shortcut bar and back button appear on restaurant screens. Printed pages and the public order status also provide back navigation.

## Local run

Follow README.md for PostgreSQL and Redis. A local SQLite sanity mode exists (`SANDBOX_CHECK=1`) for checking screens, but PostgreSQL and Redis are required for a full multi-user kitchen installation. The ZIP excludes your existing `.env`, database and uploaded media; preserve those when updating an installation.

## Cashier screen

The restaurant dashboard is the overview. Select **New Order**, choose the order channel and continue to POS. The POS shows food categories, illustrated items and the cart. A new restaurant with an empty menu offers **Add sample menu** on the POS itself. Add a dish first; then **Send to Kitchen** becomes available. Held orders can be resumed or items can be added before sending. In local `SANDBOX_CHECK=1` mode, kitchen WebSocket messages use an in-memory channel layer without Redis, intended for a single-process preview only.

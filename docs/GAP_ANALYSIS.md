# BookPilot — Gap Analysis & Roadmap

Review date: 2026-09-29. Scope: the whole platform, with a deeper pass on the
restaurant POS. "Exists" means there is working code and tests for it.

## What is already strong

- Multi-tenant core with server-side tenant isolation, RBAC roles/permissions, audit log.
- Accounting (journal, trial balance, P&L, balance sheet, bank reconciliation), sales
  invoices, returns, purchases/GRN, expenses, customers/suppliers, collections.
- Inventory with batches/expiry, serials, reorder alerts, barcodes, branches, stock transfers.
- HR: employees, attendance, leave, payroll/payslips, commissions.
- CRM, loyalty, coupons, quotations/sales orders, analytics dashboards, import/export.
- 13 dedicated verticals (restaurant, gym, spa, salon, textile, mobile shop…) and 108 business types.
- Platform admin: clients, plans, pending payments, Stripe/Razorpay settings, modules, support.
- PWA install, WebSocket kitchen display, QR menu and self-ordering.

## Priority 1: needed before selling widely

| # | Gap | Why it matters |
|---|-----|----------------|
| 1 | **Add items after KOT (order rounds)** | Restaurant lines lock once sent to the kitchen, so a table cannot order dessert later without a new order. Needs per-line "sent" tracking so the next KOT contains only new items. |
| 2 | **Arabic / multi-language + RTL** | No translation layer at all (`gettext` unused). Essential for Qatar/GCC staff and customer receipts. |
| 3 | **Public sign-up, pricing page, self-serve checkout** | Only the platform admin can create clients (`admin-console/new-client/`). A SaaS needs a landing page, free-trial sign-up and online plan purchase. |
| 4 | **Send invoice/receipt by email & WhatsApp** | Email only sends notifications; there is no "send invoice" action. WhatsApp/SMS providers are stubbed/disabled. |
| 5 | **Two-factor authentication (2FA)** | Financial data with password-only login. Add TOTP at least for owners and platform admins. |
| 6 | **Persistent file storage in production** | Render deploy currently runs with `USE_S3=False`; logos/menu photos disappear on redeploy until S3 (or Cloudflare R2) is configured. |
| 7 | **Automated database backups / tenant data export** | No backup tooling in the repo; free Render Postgres expires after 30 days. |

## Priority 2: competitive features

- **E-invoicing compliance:** KSA ZATCA (Fatoorah) QR/XML, India GST e-invoice (IRN) and GSTIN fields.
- **Post-dated cheques (PDC)** register and maturity alerts, which GCC businesses rely on.
- **Recurring invoices/subscriptions** for service businesses (gym is covered, general services are not).
- **Fixed assets & depreciation** module.
- **Customer portal:** customers view and pay invoices and see order status/history.
- **Dark mode** and a consistent design system across all modules (the restaurant module now has one; see `static/css/restaurant.css`).
- **Offline POS mode** that queues sales when internet drops (PWA currently never caches financial pages).
- **Public API docs** (OpenAPI/Swagger) for integrations.

## Restaurant POS: remaining gaps

| Gap | Notes |
|-----|-------|
| Add items after KOT / multiple rounds | See Priority 1 #1. |
| Table transfer & guest count (covers) | Move an order to another table; record covers for per-head reports. |
| Course firing (starters → mains → desserts) | Hold/fire per course on KDS. |
| Direct thermal printer (ESC/POS) & cash drawer | Browser printing exists; direct LAN/USB printing needs a small print agent. |
| Customer-facing display | Second screen showing items/total during checkout. |
| Restaurant tax/VAT on bills | Restaurant settlement always uses tax rate 0. Needs a per-company rate for GST/VAT markets. |
| Default service charge % and tip presets | Currently typed manually on each bill. |
| Delivery aggregator APIs (Talabat, Snoonu…) | Webhook import exists; outbound status sync needs provider contracts. |
| Waiter handheld mode | The new POS is mobile-ready; a waiter-only view (tables → order) would speed service further. |

## Done in this pass (restaurant redesign)

- New full-screen POS: category rail, photo menu grid, live ticket panel, fly-to-cart
  animation, animated totals, modifier sheet with live price, keyboard `/` search.
- New payment sheet: cash with quick-cash buttons and change calculation, card, bank,
  and split payments that must balance before charging.
- Mobile POS: bottom order sheet, 2-column menu; app-wide mobile navigation drawer.
- Restaurant dashboard: greeting, shift status, live stats, colour-coded floor plan
  (tap a free table to start an order, tap an occupied one to open it), open orders.
- New-order screen: visual order-type cards and table picker.
- Fixed: numbers shown as `26.00000` / `2.000`; tables stuck in "cleaning" after payment
  (new **Mark ready** action); payment impossible when a tenant had no active stock location.

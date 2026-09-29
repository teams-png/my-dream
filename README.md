# BookPilot — Multi-Tenant Accounting & Business Management

Production-oriented multi-tenant Django accounting and business-management SaaS. Development phases 1-48 are implemented, including accounting, inventory, sales/POS, purchasing, banking, HR/payroll, CRM, analytics, subscriptions, queued notifications, security hardening and operational documentation.

The registration catalogue currently provisions 108 business types into the
appropriate dedicated, retail/POS, service/work-order or project/operations
suite. See `ALL_BUSINESS_EDITION_NOTES.md` for the complete grouping and scope.

Commercial-readiness phases 49-53 add resumable tenant onboarding, validated platform-admin module assignment, branch provisioning, invoice-linked mobile handset returns, mobile repair billing and trade-in acquisition. See `PHASE49_53_COMMERCIAL_READINESS.md` for scope and release boundaries.

Platform administrators can add or rotate Stripe and Razorpay credentials later
from **Platform Setup -> Payment Gateways**. Credentials are encrypted at rest,
never displayed again, and environment variables remain supported as a fallback.

Restaurant, café and catering tenants receive the dedicated restaurant module
for tables, orders, KOT/kitchen workflow, recipes, modifiers, combos, delivery,
split billing and shift reconciliation in addition to the shared accounting,
inventory, purchase, expense and reporting engine.

The restaurant production pack also includes photo menus, dish-specific required
modifier groups, kitchen stations, a live timed KDS, 58/80mm browser printing for
receipts and KOTs, reservations/waiting-list handling, recipe food-cost and waste
tracking, restaurant channel/item/margin reports, and a secure-token public QR
menu. BookPilot installs as a PWA; authenticated financial pages are deliberately
never cached offline. Provider-specific Talabat/Snoonu outbound APIs, SMS and
WhatsApp delivery remain disabled until the merchant supplies the relevant API
contract and credentials.

QR self-ordering can send validated dine-in/takeaway orders directly to KOT.
Scheduled menus are enforced server-side, cancellations require a reason and
create an audit record, paid orders route through the accounting-safe returns
workflow, and KDS updates use authenticated tenant-scoped WebSockets with a
timed refresh fallback. Production web processes must run the ASGI application
(the included Render blueprint uses Daphne) and Redis must be available for the
multi-process channel layer.

## Local setup

```bash
cp .env.example .env          # fill in real values
docker compose up -d          # postgres + redis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py seed_platform     # BusinessTypes, Modules, a Starter plan
python manage.py createsuperuser
python manage.py runserver
```

## Key architectural rules (do not violate these — see docs/architecture.md)

1. **Tenant isolation is server-side only.** `request.company` comes from
   `ActiveCompanyMiddleware`, resolved from the logged-in user's session +
   `CompanyMembership`. Never trust a company/tenant id from the client.
2. **All tenant-scoped models inherit `TenantScopedModel`** (`apps/tenants/models.py`)
   and are queried via `Model.objects.for_company(request.company)`.
3. **Views/viewsets never contain business logic.** All of it lives in each
   app's `services.py`; views just call into it.
4. **Nothing posts revenue/expense directly.** Every financial event goes
   through `accounting.services.post_journal_entry(...)` once the
   `accounting` app is scaffolded in Phase 3 — see Phase 1 Section 5.
5. **No `if business_type == "gym":` branches.** Feature visibility is data
   (`Module` / `CompanyModule`), not code branches — see `apps/modules/services.py`.

## Core status

| App | Status |
|---|---|
| accounts | ✅ register / JWT login / me |
| tenants | ✅ Company, Role/Permission, CompanyMembership, middleware, `create_company_with_owner` |
| modules | ✅ Module registry, `activate_default_modules` |
| subscriptions | ✅ plans, trial start, expiry guard middleware, Celery beat task |
| accounting | ✅ Chart of accounts, `post_journal_entry` (the ledger's only write path), trial balance |
| customers / suppliers | ✅ CRUD, tenant-scoped |
| inventory | ✅ Products, Warehouses, append-only `StockMovement` ledger |
| sales | ✅ `create_invoice` (atomic: invoice + stock + journal entry), payments, IDOR guard on cross-tenant ids |
| purchases | ✅ mirror of sales — `create_purchase`, payments, IDOR guard |
| expenses | ✅ `record_expense` posts a journal entry per expense |
| employees | ✅ CRUD |
| audit | ✅ `AuditLog` model + `log_action` service (admin delete/change disabled — append-only) |
| verticals/gym | ✅ Membership plans, linked non-stock billing products, enrollment/renewal invoices, freeze/unfreeze and attendance |

**Verified end-to-end** (see `smoke_test.py` pattern, not shipped — run your own):
register → `create_company_with_owner` (seeds roles, modules, chart of accounts, trial subscription) →
create product/customer/warehouse → `sales.services.create_invoice` → stock decremented →
balanced journal entry posted → trial balance shows AR/Sales Revenue correctly.

## Deployment prerequisites and external dependencies

- PostgreSQL is the production database and is required for concurrency-specific verification.
- Redis and a Celery worker/beat process are required for background notifications and scheduled checks.
- Email is implemented through Django's configured backend. SMS and WhatsApp remain provider adapters and require vendor credentials/configuration before activation.
- Production media storage must be private, backed up and configured through the deployment environment.
- Run the PostgreSQL CI job and the restore drill in `docs/OPERATIONS_RUNBOOK.md` before declaring a production release.

## App status (Phase 4 complete)

RBAC permission enforcement (`apps.tenants.permissions.HasCompanyPermission`) is wired into every
operational viewset — accounting, sales, purchases, expenses, customers, suppliers, inventory,
employees, and the new `tenants.RoleViewSet` / `tenants.MembershipViewSet` (Owner can create custom
roles, edit their permissions, and invite members — enforcing the subscription's `max_users`).

**`apps/reports`** — cross-app reporting engine:
- `GET /api/reports/trial-balance/?as_of=YYYY-MM-DD`
- `GET /api/reports/profit-and-loss/?date_from=...&date_to=...`
- `GET /api/reports/balance-sheet/?as_of=YYYY-MM-DD`
- `GET /api/reports/sales/?date_from=...&date_to=...`
- `GET /api/reports/stock/?warehouse=<id>`
- `GET /api/reports/customer-outstanding/`
- `GET /api/reports/supplier-outstanding/`

All gated behind `accounting.view_reports`. P&L and Balance Sheet are computed straight from
`JournalLine` (never re-derived from `SalesInvoice.total`/`Expense.amount`), so they always
reconcile with the ledger per Phase 0 Section 9.

## App status (Phase 5 — notifications — complete)

**`apps/notifications`** — in-app and email notifications. SMS/WhatsApp delivery is disabled until
a provider adapter and credentials are configured. `Notification` rows are either company-wide
(`user=None`) or per-user.

- `subscriptions.services.run_daily_expiry_check` now calls `notifications.services.notify_subscription_expiring`
  / `notify_subscription_expired` at the correct thresholds instead of a no-op stub.
- `notifications.services.check_low_stock_and_notify` / `check_overdue_invoices_and_notify` — run daily
  via `notifications.tasks.check_low_stock_and_overdue_invoices` (registered in `config/celery.py`
  alongside the subscription check). Both guard against notifying the same
  thing twice in one day.
- `GET/PATCH /api/notifications/` — list (company-wide + own), `mark_read`, `mark_all_read`. No extra
  RBAC gate — seeing your own notifications isn't a privilege to withhold from Staff.

**Verified**: forcing a subscription to 7 days from expiry and running the daily check produces exactly
one "expires in 7 days" notification; dropping a product below its reorder level produces exactly one
low-stock notification, and running the check twice in the same day does not duplicate it.

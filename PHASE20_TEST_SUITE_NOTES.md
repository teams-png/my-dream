# Phase 20 — Automated Test Suite

Picks up after Phase 19 (production VPS deployment). This closes the one
gap flagged Section 38 of the master brief ("Testing") that had no code
anywhere in the previously delivered zips: **47 tests, all passing.**

## Files in this zip

Drop these into your existing project root (same paths) — this zip only
contains what's new or changed, not the whole codebase.

**New:**
```
pytest.ini
conftest.py
config/settings/test.py
apps/tenants/tests/{__init__.py, test_tenant_isolation.py, test_rbac.py}
apps/subscriptions/tests/{__init__.py, test_limits_and_expiry.py}
apps/accounting/tests/{__init__.py, test_ledger_integrity.py}
apps/sales/tests/{__init__.py, test_invoice_flow.py}
apps/accounts/tests/{__init__.py, test_registration.py}
```

**Modified (see "Bugs found" below for why):**
```
apps/tenants/middleware.py
apps/notifications/services.py
```

## How to run

```bash
pip install -r requirements/dev.txt   # pytest, pytest-django, factory-boy already listed
pytest
```

Defaults to SQLite in-memory (`config/settings/test.py`) for speed — the
codebase uses no Postgres-only features, so this is safe. For CI, point
`DATABASE_URL` at a real Postgres service container instead before
running `pytest`, so migrations get exercised for real:

```bash
DATABASE_URL=postgres://postgres:postgres@localhost:5432/test_db pytest
```

## What's covered

| File | Covers |
|---|---|
| `test_tenant_isolation.py` | Master brief Section 38's exact requirement — ORM-level `.for_company()` isolation, API list-leak checks, **IDOR** (guessing another tenant's numeric ID), cross-tenant invoice creation blocked, reports endpoint isolation |
| `test_rbac.py` | Owner/Accountant/Staff boundaries (Section 7) — Staff blocked from reports/roles/members, Accountant blocked from role management, Owner can customize custom-role permissions, system roles (Owner/Accountant/Staff) can't be edited or deleted |
| `test_limits_and_expiry.py` | Plan `max_users` enforcement (service-layer `ValueError` + API `402`), trial subscription on signup, daily expiry check (status flip + notification), `SubscriptionGuardMiddleware` blocking non-Owner routes once expired, renewal |
| `test_ledger_integrity.py` | Double-entry invariants (Section 41) — unbalanced/zero-amount entries rejected, rejected entries leave no partial rows, trial balance always nets to zero, P&L reads from the ledger (not a separate calculation), voided entries excluded |
| `test_invoice_flow.py` | Invoice numbering (sequential, per-tenant), stock decrement on sale, balanced journal entry posted alongside the invoice, **atomicity** (a simulated failure mid-`create_invoice` rolls back the invoice *and* the stock movement), partial/full payment status transitions |
| `test_registration.py` | Register → login → JWT → (service-layer) company creation → Owner membership → authenticated dashboard-style call |

## Bugs found while writing these tests

**1. `apps/tenants/middleware.py` — JWT requests never got a resolved `request.company`.**
`ActiveCompanyMiddleware` is a plain Django middleware, which runs
*before* DRF's authentication classes ever see the request (DRF
authenticates lazily inside `APIView.dispatch`, after all middleware has
already run). Since the API's `DEFAULT_AUTHENTICATION_CLASSES` is JWT,
any request carrying only an `Authorization: Bearer <token>` header (no
session cookie) reached this middleware with `request.user` still
`AnonymousUser`, so `request.company` was silently left `None` for
**every JWT-authenticated API call** — every `HasCompanyPermission` check
would have failed. Fixed by having the middleware fall back to an
explicit `JWTAuthentication().authenticate(request)` call when session
auth didn't already populate a user.

**2. `apps/notifications/services.py` — missing `notify_product_expiry`.**
`apps/verticals/protein_shop/services.py` imports this function; it
didn't exist in the notifications app. Added it as a generic
expiry-alert hook (any vertical with dated/perishable batches — protein
shop, medical shop — can reuse it, rather than each vertical growing its
own bespoke notification type).

## Gaps flagged, not yet fixed (left for you to prioritize)

- **No API endpoint for "create company."** `tenants.services.
  create_company_with_owner()` is fully built and tested (directly, and
  indirectly through the `tenant_a`/`tenant_b` fixtures used everywhere),
  but nothing in `apps/tenants/urls.py` calls it — Section 4's
  registration flow is only wired up through user registration + login
  at the HTTP layer. `test_registration.py` calls the service function
  directly to stand in for this missing step. Needs a
  `POST /api/tenants/companies/` view.
- The three TODOs already flagged in the Phase 3 scaffold's own README
  (invoice-numbering race condition under concurrency, gym-enrollment →
  invoice linkage, AuditLog write-only DB grant) are unchanged — none of
  today's tests happened to touch that code path.
- 10 of the 13 vertical modules (textile, spa, construction, mobile
  shop, vehicle wash, sports shop, cycle shop, saloon, beauty parlour,
  medical shop) and `apps.platform_admin` weren't in this batch's zips,
  so they have zero test coverage here — worth a follow-up pass once
  those zips are back in the tree.

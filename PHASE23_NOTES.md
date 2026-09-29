# Phase 23 — Spa invoice-linkage fix (closes the item Phase 22 flagged as next)

Picks up after Phase 22. Mirrors that phase's fix to `apps.verticals.gym`
exactly: a spa appointment or package purchase is money changing hands, so
both now go through `sales.services.create_invoice()` before the row that
represents "this has been paid for" is created — matching every other
vertical's rule (Section 41 / Phase 0 Section 18: never shortcut the
accounting engine).

## Drop-in files (same paths as your existing project root)

```
apps/verticals/spa/models.py                                          (modified — product FK on SpaService + ServicePackage)
apps/verticals/spa/services.py                                        (modified — create_spa_service, create_service_package, book_appointment, purchase_package now invoice)
apps/verticals/spa/views.py                                           (modified — creation routed through services, IDOR guards)
apps/verticals/spa/serializers.py                                     (modified — Create*/Book*/Purchase* input serializers)
apps/verticals/spa/migrations/0002_spaservice_product_servicepackage_product.py  (new)
apps/verticals/spa/tests/test_appointment_invoicing.py                (new)
```

Run `python manage.py migrate` after dropping these in.

## What changed

**`SpaService` and `ServicePackage` each gained a `product` FK** to
`inventory.Product` (nullable — existing rows created before this
migration just can't be booked/purchased against until re-created via the
new service functions, same non-breaking approach Phase 22 used for
`MembershipPlan.product`).

**`create_spa_service()` / `create_service_package()`** — new functions,
create the catalog row and its linked service `Product` atomically. Use
these instead of creating `SpaService`/`ServicePackage` directly from now
on.

**`book_appointment()`** — now branches on `customer_package`:
- **Walk-in** (no package): invoices 1 × the service's price against
  `service.product` *before* the `Appointment` row is created. Raises
  `ValueError` if the service has no linked product (created before this
  migration / bypassed the new service function) — same guard shape as
  gym's `enroll_member`.
- **Package-covered**: unchanged behavior — only the
  `sessions_remaining >= 1` check runs, no invoice, because the money was
  already collected when the package was purchased.

**`purchase_package()`** — now invoices the package's price against
`package.product` before creating the `CustomerPackage` row. Same
`ValueError`-if-no-linked-product guard.

**`complete_appointment()`** — unchanged. It was never the place that
should invoice (payment already happened at booking or package-purchase
time), so there was nothing to fix here — worth stating explicitly since
it's easy to assume "completing" a paid service is also where you'd
naively bolt on invoicing.

**Both new atomicity guarantees are the same pattern as gym**: wrapped in
`@transaction.atomic`, so a failed `create_invoice()` call rolls back the
whole `book_appointment()`/`purchase_package()` call — no Appointment or
CustomerPackage is ever left behind without a real invoice, verified by
`test_failed_invoice_leaves_no_appointment` /
`test_failed_invoice_leaves_no_customer_package`.

## Known accepted quirk — unchanged, not fixed here

Same StockMovement drift gym's fix accepted (Phase 22): invoicing a
service through the same `create_invoice()` path used for physical
products writes a `StockMovement` for the service "product," which has no
physical meaning and makes `current_stock()` drift negative over time.
Now that **two** verticals (gym, spa) hit this, a proper "non-stock
product" distinction in `apps.inventory` (and `apps.reports.stock_report`,
which reads stock movements) is worth its own reviewed phase — deliberately
not bundled into this one to keep this phase's diff reviewable against a
single concern.

## Verified

```
python manage.py check                    # expected: 0 issues
python manage.py makemigrations --check   # expected: clean
pytest                                     # expected: 63 + new spa tests (11) = 74 passed
```
(Run these yourself after reassembling — this phase was written and
compile-checked in isolation, not against your full reassembled tree, so
the exact pass count depends on what else has changed since Phase 22.)

## Still open

- The "non-stock product" fix flagged above — now justified by two
  verticals needing it, good Phase 24 candidate.
- `CompanyCounter` true concurrency test (needs Postgres + real threads —
  unchanged from Phase 22's notes).
- `general_retail` — still intentionally not a separate vertical app.

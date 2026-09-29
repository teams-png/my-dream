# Phase 22 — Closing the three items flagged "Still open" since Phase 21

Before starting this phase, all 21 previously delivered zips (`all-20.zip`
+ the phase21 diff) were reassembled into one tree and verified —
`manage.py check`, `manage.py makemigrations --check`, `pytest` — same
process Phase 21 itself used. **That surfaced one real reassembly bug**,
described below, on top of the three items Phase 21's own notes left open.

## Drop-in files (same paths as your existing project root)

```
apps/tenants/models.py                    (modified — new CompanyCounter model)
apps/tenants/services.py                  (modified — new next_counter_value())
apps/tenants/admin.py                     (modified — register CompanyCounter)
apps/tenants/migrations/0002_companycounter.py                       (new)
apps/tenants/tests/test_company_counter.py                           (new)

apps/sales/services.py                    (modified — _next_invoice_number uses the counter)

apps/verticals/gym/models.py              (modified — MembershipPlan.product FK)
apps/verticals/gym/services.py            (modified — create_membership_plan, real enroll_member)
apps/verticals/gym/views.py               (modified — creation routed through services, not bare writes)
apps/verticals/gym/serializers.py         (modified — input serializers for the above)
apps/verticals/gym/migrations/0002_membershipplan_product.py         (new)
apps/verticals/gym/tests/test_enrollment.py                          (new)

apps/audit/migrations/0002_insert_only_db_grant.py                   (new)
apps/audit/tests/test_insert_only_grant.py                           (new)

apps/accounts/migrations/0003_rename_..._idx.py                      (new — unrelated, see "Bug 0" below)
```

Run `python manage.py migrate` after dropping these in. On Postgres, also
set `DB_APP_ROLE` to your actual app DB role (e.g. `saas_app` from the
Phase 19 deployment guide) for the new audit migration to take effect —
see its section below.

---

## Bug 0 — found while reassembling, not part of the "still open" list

`apps/reports/models.py`, `services.py`, and `admin.py` were getting
silently reverted to empty stubs during reassembly, deleting the
`ReportExport` model. Cause: the generic "-scaffold" zips (`phase4-scaffold`,
`phase5-scaffold`, ...) are **full-tree snapshots** from an earlier point,
not incremental patches — applying them in filename order after the
focused `phase4-reports`/`phase5-superadmin` patches let the older
snapshot clobber the newer, more complete files. Fixed by reassembling in
two explicit layers: all "-scaffold" snapshots first, then every specific
feature patch on top, then the phase21 diff last. No file content changed
by this — it's purely a reassembly-order note for whoever reassembles the
zips again from scratch. `pytest` was still green either way (the existing
suite doesn't happen to exercise `ReportExport`), so this wouldn't have
been caught by CI — worth keeping in mind.

---

## 1. Race-safe invoice numbering

`apps.sales.services._next_invoice_number` used to read the last invoice
row and add 1 with no locking — two concurrent requests could read the
same "last" value and produce the same invoice number.

**Fix:** a new `CompanyCounter(company, key, last_value)` model
(`apps/tenants/models.py`) plus `tenants.services.next_counter_value(company, key)`,
which does:
```python
counter, _ = CompanyCounter.objects.select_for_update().get_or_create(
    company=company, key=key, defaults={"last_value": 0}
)
counter.last_value += 1
counter.save(update_fields=["last_value"])
return counter.last_value
```
`select_for_update()` requires an open transaction — it's called from
inside `create_invoice()`'s own `@transaction.atomic`, so the row lock
covers the whole invoice-creation flow. On Postgres, a second concurrent
`create_invoice()` call for the same company blocks until the first
commits, then gets the correctly-incremented value — never a duplicate.

**Scoped to SQLite in tests:** `select_for_update()` is a documented
no-op on SQLite (per Django's own docs), which is what `config/settings/test.py`
uses. The new tests (`apps/tenants/tests/test_company_counter.py`) verify
sequence correctness and per-company/per-key isolation, not true
concurrency — that guarantee is architectural (Postgres row locking), not
something a SQLite-backed unit test can exercise. If you want to prove
the concurrency guarantee itself, that needs a Postgres-backed test with
real threads/processes — flagging as a possible Phase 23 item rather than
guessing at one here.

`purchases.bill_number` was checked too — it's supplier-provided, not
auto-generated, so it was never exposed to this race condition and needed
no change.

---

## 2. Gym enrollment → invoice linkage

`gym.services.enroll_member()` created a `GymMember` row directly with no
money changing hands — the exact "shortcut the accounting engine" mistake
Section 41 and Phase 0 Section 18 warn against, left as an explicit TODO
since the vertical was first built.

**Fix:**
- `MembershipPlan` gained a `product` FK to `inventory.Product` (nullable,
  so any plan created before this migration doesn't break — it just can't
  enroll members until re-created properly).
- New `gym.services.create_membership_plan(company, name, duration_days, price, ...)`
  creates the plan and its linked service `Product` atomically. Use this
  instead of creating `MembershipPlan` directly from now on.
- `enroll_member()` now calls `sales.services.create_invoice()` against
  the plan's product for 1 × the plan price, and only creates the
  `GymMember` row after that succeeds — same atomicity guarantee
  `sales.create_invoice` itself relies on (a failed invoice step rolls
  back the whole enrollment, verified in
  `test_failed_invoice_leaves_no_gym_member`).
- Calling `enroll_member()` with a plan that has no linked `product`
  (e.g. one created before this migration, or directly via the ORM)
  raises `ValueError` rather than silently skipping invoicing.
- **Bug found while wiring this up:** `join_date` arrives as whatever the
  caller passes — often an ISO string, same as every date param elsewhere
  in this codebase (`create_invoice(date="2026-01-05", ...)` works because
  Django's ORM parses the string when it hits a `DateField`). But
  `enroll_member` does raw Python `join_date + timedelta(...)` arithmetic
  *before* that ever happens, which fails on a plain string. Fixed by
  coercing `join_date` to a real `date` at the top of the function if it
  arrives as a string.

**Known accepted quirk, left as-is:** invoicing a membership through the
same path used for physical products also writes a `StockMovement` for
the membership "product," which has no physical meaning and makes its
`current_stock()` drift negative over time. Introducing a "non-stock
product" distinction in `apps.inventory` is a bigger, cross-cutting change
(it'd also touch `apps.reports.stock_report`) and isn't justified by gym
alone — worth revisiting if a second service-based vertical (Spa is the
obvious next one) needs the same thing.

---

## 3. AuditLog write-only DB grant

Phase 0 Section 14 always specified this ("no DELETE/UPDATE permission
granted to the application DB user on that table") but it had only ever
existed as a manual `psql` step in the Phase 19 deployment doc — easy to
forget, not enforced by anything.

**Fix:** `apps/audit/migrations/0002_insert_only_db_grant.py` — a real
migration using `RunPython` to execute:
```sql
REVOKE UPDATE, DELETE ON audit_auditlog FROM <role>;
GRANT INSERT, SELECT ON audit_auditlog TO <role>;
```
Deliberately a no-op in two safe cases, so it never breaks a setup that
doesn't need it:
- **Not Postgres** (checks `schema_editor.connection.vendor`) — SQLite
  (dev/test) has no `GRANT`/`REVOKE` equivalent.
- **`DB_APP_ROLE` env var not set** — so a local Postgres setup using one
  shared superuser isn't suddenly locked out of its own audit table.

The role name is validated against a strict identifier pattern
(`^[A-Za-z_][A-Za-z0-9_]*$`) before being interpolated into SQL — tested
directly in `apps/audit/tests/test_insert_only_grant.py`, including a
literal SQL-injection-shaped value, since a wrong check here would be an
actual injection surface, not just a correctness bug.

**Action needed on your production VPS** (per Phase 19): set `DB_APP_ROLE=saas_app`
(or whatever your actual Postgres role is) in the environment before
running `python manage.py migrate` there. Without it, this migration runs
as a documented no-op and the manual `psql` step from the Phase 19 guide
is still your only enforcement — same as before this phase.

---

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 63 passed (48 from Phase 21 + 15 new)
```

## Still open

- True concurrency test for `CompanyCounter` (needs Postgres + real
  threads/processes — see Section 1 above).
- Spa (or another service-based vertical) will hit the same "no-stock
  service product" quirk gym has — worth a real fix once a second
  vertical needs it, not before.
- Everything else Phase 20/21 already flagged as out of scope for this
  project (multi-branch, multi-currency, payment gateway integration,
  mobile app, SMS/WhatsApp) is unchanged — this phase touched only the
  three items above plus the Bug 0 reassembly note.

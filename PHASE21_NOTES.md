# Phase 21 — Company Registration API + Phase 20 bug fixes

Picks up after Phase 20 (test suite). All 20 previously delivered zips
were reassembled into one tree and verified (`manage.py check`,
`makemigrations --check`, `pytest`) before this phase started — that
surfaced 4 real, pre-existing bugs, all fixed here, on top of the one
gap Phase 20's own notes flagged.

## Drop-in files (same paths as your existing project root)

```
apps/tenants/serializers.py          (modified — RegisterCompanySerializer)
apps/tenants/views.py                (modified — CompanyRegisterView)
apps/tenants/urls.py                 (modified — new route)
apps/notifications/models.py         (modified — field/choice fix, see Bug 3)
apps/notifications/services.py       (modified — field/choice fix, see Bug 3)
apps/notifications/migrations/0002_alter_notification_notif_type_and_more.py  (new)
apps/reports/views.py                (modified — RBAC + response shape, see Bugs 1–2)
apps/subscriptions/services.py       (modified — missing notify call, see Bug 4)
apps/subscriptions/tests/test_limits_and_expiry.py  (modified — field name fix)
apps/accounts/tests/test_registration.py            (modified — real endpoint test)
```

Run `python manage.py migrate` after dropping these in.

## 1. New: POST /api/tenants/companies/

Closes the exact gap Phase 20 flagged: `create_company_with_owner()` was
fully built and tested but had no HTTP entry point. Section 4's
registration flow ("register → pick business type → create company →
become Owner") is now complete end-to-end over the API, not just from
Python/the admin.

**Request** (authenticated — call after register + login):
```json
POST /api/tenants/companies/
{
  "name": "New Biz Textiles",
  "slug": "new-biz-textiles",
  "business_type": "textile",   // BusinessType.code — see seed_platform
  "phone": "+974...",           // optional
  "email": "...",               // optional
  "address": "...",             // optional
  "registration_number": "...", // optional
  "default_currency": "QAR"     // optional, defaults to QAR
}
```
Returns `201` + the created `Company` and makes the caller its Owner
(roles/permissions/default modules/trial subscription/chart of accounts
all seeded atomically by the existing service function — unchanged).
Duplicate `slug` → `400`. Unknown `business_type` code → `400`.

Deliberately **not** gated by `HasCompanyPermission` — the caller has no
company yet at this point.

## 2–5. Bugs found while reassembling phases 1–20

**Bug 1 — Reports endpoints had no RBAC.**
Every view in `apps/reports/views.py` used `permission_classes =
[IsAuthenticated]` only. A Staff member could hit
`/api/reports/trial-balance/`, `/profit-and-loss/`, etc. directly —
Section 7 says Staff must not see financial reports. Fixed by adding a
shared `BaseReportView` gated with `HasCompanyPermission` +
`accounting.view_reports` (the same permission code Owner/Accountant
already have from `tenants.services.ROLE_PERMISSION_MAP`); all 12
report views now inherit from it.

**Bug 2 — `TrialBalanceView` returned a bare list.**
Every other report view returns an object; this one returned
`Response([...])` directly, which is both inconsistent and harder for a
frontend to extend (can't add pagination/meta later). Changed to
`Response({"rows": [...]})`.

**Bug 3 — `apps/notifications/services.py` didn't match its own model.**
`Notification` uses `recipient` / `notif_type`; `services.py` (as
modified in the Phase 20 zip, to add `notify_product_expiry`) called
`Notification.objects.create(user=..., type=...)` — wrong keyword
names entirely, so **every** subscription-expiry, low-stock, and
invoice-overdue notification raised `TypeError` at creation time. Also:
the model's own docstring says "`recipient = null` means a company-wide
broadcast" but the field wasn't actually nullable, and
`NotificationType` had no `subscription_expired` choice (only
`subscription_expiry`), so it couldn't distinguish the two events the
subscription flow fires. Fixed: renamed the choice to
`SUBSCRIPTION_EXPIRING` and added `SUBSCRIPTION_EXPIRED`, made
`recipient` nullable (migration included), and corrected every
`notify()`/`filter()` call site to use `recipient=`/`notif_type=`.

**Bug 4 — Subscriptions never actually sent the "expired" notification.**
`run_daily_expiry_check()` flipped `status` to `"expired"` once
`end_date` had passed, but the branch never called
`notify_subscription_expired()` — only the day-threshold branch above
it called `notify_subscription_expiring()`. An Owner's subscription
could lapse silently. Added the missing call.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean (after applying the notifications migration)
pytest                                     # 48 passed (47 from Phase 20 + 1 new)
```

## Still open (unchanged from Phase 20's own notes — not touched here)

- Invoice-numbering race condition under concurrency (`apps/sales`).
- Gym-enrollment → invoice linkage (`apps/verticals/gym`).
- `AuditLog` write-only DB grant.
- `general_retail` is intentionally **not** a separate vertical app — it
  uses core Sales/Purchases/Inventory only, matching Section 12's spec
  (no vertical-specific fields listed for it). The `BusinessType` row
  already exists in `seed_platform.py`; nothing further needed there.

# Master Version Manifest

## Platform owner panel update

The `/platform/` owner panel includes business-facing administration that
previously required Django admin: module catalogue, business types and default
module bundles, users and access visibility, support ticket handling, a
read-only cross-company audit log, and integration configuration status.
Sensitive framework internals remain restricted to `/admin/`.

## Authoritative release

`BookPilot-Accounting-SaaS-Commercial-Phase53`

## Archives reviewed

- Original accounting SaaS project
- Phase 36
- Phase 37
- Phase 38
- Phase 39 (duplicate copies verified as identical)
- Phase 48
- Commercial Phase 53

## Consolidation result

- Phase 53 contained all meaningful source, template, static, migration and test files present in the earlier phase archives.
- The original large archive contained a nested duplicate project, a virtual environment, local database/media/cache data and Git metadata. These were intentionally excluded.
- The historical `phase24-drop-in.zip` was not embedded because its incorporated source already exists in later phases.
- `.gitignore`, expanded environment documentation, optional payment dependencies and this setup/manifest documentation were added.
- Real `.env` credentials, local databases, uploaded media, caches and compiled files are not included.

## Verification

- Django system check: passed
- Migration drift check: passed
- Automated tests: 330 passed
- PostgreSQL CI workflow: included; external run required before production declaration

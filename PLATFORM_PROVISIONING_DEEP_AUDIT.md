# Platform Owner Provisioning — Deep Audit Fix

The previous commercial build had a real integration gap: the post-creation Client 360 pages supported the full module catalogue and multiple business suites, but `Add new client` still rendered the old fixed eight `WEB_FEATURES` checkboxes.

This build fixes that gap end-to-end:

- Add New Client is now a 4-step provisioning wizard.
- Every business type in the canonical `BUSINESS_TYPE_CHOICES` catalogue is shown, grouped by workflow family.
- One primary business plus any number of additional business suites can be selected before creation.
- All selected suites are persisted as `CompanyBusinessType` rows and share the same company/accounting tenant.
- Every registered `Module` is selectable during creation; core modules remain mandatory.
- `WEB_FEATURES` (POS, returns/refunds, loyalty, expenses, purchases, branches, staff roles, analytics) are registered into the same canonical Module table instead of being a separate fixed UI island.
- “Apply recommended” combines default modules from every selected business suite; selections remain manually editable.
- Manual/custom modules can be entered during client creation (`Name | code`) and are created + enabled atomically.
- Provisioning is transaction-wrapped so a failed setup does not leave a half-created owner/client.
- Successful creation redirects directly to Client 360, where Business Suites, Modules & Permissions, Commercial/White-label, plan and payments remain editable.
- Older databases are protected from hiding catalogue businesses: the wizard ensures canonical business type rows exist. Run `seed_platform` to populate the richer default-module mappings.

## Recommended first run after replacing the project

    python manage.py migrate
    python manage.py seed_platform
    python manage.py runserver

`seed_platform` is idempotent and is important for recommended module presets across the full business catalogue.

## Validation performed in this environment

- Python source tree passes `compileall` syntax validation.
- Searched all platform navigation entry points and confirmed they route to the upgraded `register_client` view/template.
- `manage.py check` could not run in the build container because Django is not installed in that container; run it in the project's normal virtual environment before deployment.

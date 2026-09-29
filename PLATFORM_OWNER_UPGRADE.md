# Platform Owner Commercial Upgrade

Added to the owner-facing platform interface:
- Commercial Control Centre for selling configurable SaaS packages.
- Multi-business suite overview and consolidated-accounting provisioning flow.
- Expanded package/pricing builder fields: modules, users, warehouses, invoice quota, storage, grace period.
- Client 360 commercial controls for branch count, POS terminal count, API quota and negotiated monthly price.
- White-label/reseller metadata: reseller, brand name and custom domain.
- Full platform permission catalogue grouped by module.
- Existing per-client module/feature centre remains the switchboard for POS and shared/common capabilities.
- Existing Business Suites screen remains the multi-industry selector for one accounting tenant.
- UsageSnapshot data model added as the foundation for monthly invoice/API/storage metering and future threshold alerts.

After extracting over an existing database run: `python manage.py migrate`.

# Phases 40-48 Completion Notes

## Phase 40 - CRM

Added tenant-scoped leads, pipeline stages, opportunities and activities; duplicate-customer detection; atomic lead conversion; optional quotation creation; customer timeline; role-ready assignment fields; indexes; API routes and isolation tests.

## Phase 41 - Vertical invoice linkage

Audited all chargeable vertical services. Gym, saloon, spa, beauty parlour, textile, vehicle wash, cycle shop, mobile shop, medical shop and protein shop use the shared sales invoice service with atomic rollback tests. Service products remain non-stock and physical products use stock tracking.

## Phase 42 - Owner analytics

Added tenant-scoped dashboard aggregation for sales, purchases, expenses, receivables, payables, overdue invoices, low stock, near expiry, top products/customers and trends. Warehouse IDs are resolved inside the active tenant. Gross profit is clearly labelled as an estimate; ledger P&L remains the audited measure.

## Phase 43 - SaaS entitlements

Expanded plans with users, warehouses, monthly invoice, storage and grace-period limits. Added server-side module/limit helpers, trial/grace state, safe plan-change handling, confirmed-payment revenue metrics and no-delete downgrade behavior.

## Phase 44 - External notifications

Added templates, preferences, channel-neutral deliveries, statuses, retry count, failure reason and idempotency keys. Email delivery uses Celery after transaction commit. SMS and WhatsApp remain disabled adapter points until provider configuration is supplied.

## Phase 45 - Security hardening

Added production secret failure, secure headers/cookies, request IDs, privacy-safe structured logging, security documentation and additional tenant-isolation coverage. Existing login throttling, cross-tenant 404 behavior and PostgreSQL audit grant are retained.

## Phase 46 - Performance

Added composite indexes for high-volume invoice, bill, journal and audit queries; used grouped aggregations/select-related access in new services; added filters and tenant-bounded dashboard queries. Query profiling remains environment-specific and should be repeated with production-sized PostgreSQL data.

## Phase 47 - Operations

Added health/readiness endpoints, request correlation, structured production logs, backup/restore/deployment/rollback runbook and independent notification retries.

## Phase 48 - Documentation and regression

Updated README, added API/security/operations guides, added SQLite and PostgreSQL CI jobs and expanded tests for CRM, dashboard, entitlements and notification delivery. Local verification: 320 tests passed. PostgreSQL CI is configured but was not executed in the local environment because no PostgreSQL server was available.

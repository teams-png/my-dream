# Phase 37 — Configurable Tax Engine

Implemented a generic, effective-dated tax engine without hard-coded country law.

- Tenant tax schemes with registration details.
- Effective-dated tax codes with taxable, zero-rated and exempt classifications.
- Exact Decimal inclusive/exclusive calculations.
- Sales, purchase and POS-compatible line tax codes.
- Per-document and per-line tax breakdowns.
- Sales returns reverse the original line tax through the tax-control account.
- Period tax report includes sales/purchase totals grouped by tax code.
- Tax scheme and tax code management APIs.
- Legacy tax-rate calls remain compatible.

Configuration is a business setting, not legal advice. Verification: Django check passed,
migrations are clean, and 300 tests passed.

Phase 37 status: complete. Phase 38 (HR core) is next.

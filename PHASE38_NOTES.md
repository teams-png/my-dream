# Phase 38 — HR Core

Implemented a tenant-scoped HR foundation integrated with the existing employee module.

- Departments, designations, employment status, joining/leaving dates and work shifts.
- Unique employee/date attendance with safe update behaviour.
- Leave types, annual balances, requests, approvals/rejections and holiday-aware working-day calculations.
- Employee self-service permission separated from manager/HR management permission.
- Configurable employee document metadata for QID, passport, visa, contract or other types.
- Document-expiry alerts with threshold-level duplicate prevention.
- Identity-document files are not stored until hardened private file storage is available.
- HR APIs for each core resource.

Verification: Django check passed, migrations are clean, and 304 tests passed.

Phase 38 status: complete. Phase 39 (payroll and payslips) is next.

# API Guide

All operational endpoints require authentication. Tenant identity is resolved server-side from the authenticated membership; clients never select a company by sending `company_id`.

## Main endpoint groups

| Prefix | Purpose |
|---|---|
| `/api/accounts/` | Registration, token login, current user |
| `/api/tenants/` | Company membership, roles and permissions |
| `/api/accounting/` | Accounts, journals and fiscal years |
| `/api/sales/` | Quotes, orders, deliveries, invoices, payments, returns and POS |
| `/api/purchases/` | Purchase orders, receipts, bills, payments and returns |
| `/api/inventory/` | Products, warehouses, batches, serials and stock operations |
| `/api/reports/` | Ledger-backed financial and operational reports |
| `/api/banking/` | Bank/cash accounts, statement import and reconciliation |
| `/api/collections/` | AR/AP ageing and follow-up |
| `/api/employees/` | HR, attendance, leave and payroll |
| `/api/crm/` | Leads, opportunities, activities, conversion and customer timeline |
| `/api/analytics/dashboard/` | Owner dashboard; supports `start_date`, `end_date`, and tenant-scoped `warehouse` filters |
| `/api/subscriptions/` | Current plan and subscription state |
| `/api/notifications/` | In-app notifications and read state |

## CRM conversion

`POST /api/crm/leads/{id}/convert/` accepts optional `customer_id`, `resolve_duplicate`, and `create_quotation`. Matching name, email, or phone candidates are returned as a validation warning unless the caller explicitly resolves the duplicate. Conversion is atomic.

## Error conventions

- `400`: invalid business rule or request data
- `401`: unauthenticated
- `403`: authenticated but missing permission/entitlement
- `404`: absent or outside the active tenant (prevents IDOR disclosure)
- `402`: expired subscription for a non-owner operational request
- `429`: throttled

Every response includes `X-Request-ID` for operational correlation.

## Commercial SaaS administration

- `GET/POST /api/tenants/onboarding/` reads or updates the active company's resumable setup checklist.
- `GET/POST /api/platform-admin/tenants/{id}/modules/` lets a platform administrator inspect or assign modules. Assignments are validated against the subscription plan and never delete tenant data.
- `/api/mobile-shop/repairs/` manages repair jobs; completion invoices through the shared sales engine.
- `/api/mobile-shop/trade-ins/` manages quoted trade-ins; acceptance creates inventory and accounting through the shared purchase engine.

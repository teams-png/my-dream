# Phase 39 — Payroll and Payslips

## Delivered

- Tenant-scoped salary structures with basic pay, allowances, deductions, and overtime rate.
- Employee overtime submission with normal/weekend/holiday types and approval/rejection workflow.
- Payroll periods and one payroll run per period.
- Payroll calculation using approved overtime only, with gross, deduction, and net totals.
- Employee payslip data and paid/unpaid tracking.
- Posting to the general ledger using Salary Expense, Payroll Payable, and Payroll Deductions Payable.
- Controlled reversal for unpaid posted payroll; paid payroll cannot be reversed accidentally.
- Payroll RBAC for Owner and Accountant, while employees retain self-service access to their own overtime/payslip.
- Database migrations for payroll models and permission backfill.

## Verification

- `python manage.py check`: passed.
- Payroll tests: 6 passed.
- Full regression suite: 310 passed.

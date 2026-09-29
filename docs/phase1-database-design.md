# Multi-Tenant SaaS Accounting & Business Management Platform
## Phase 1 — Field-Level Database Design

This document defines exact models, fields, types, constraints, and relationships for all core apps, plus one fully-specified vertical module (**Gym**) as the proof-of-concept for the module pattern. Other verticals follow the same extension-table shape once Gym is validated end-to-end.

Conventions used throughout:
- `id` — every model has an implicit `BigAutoField` primary key (Django default), not repeated per model below.
- `created_at` / `updated_at` — every model includes these (`DateTimeField(auto_now_add=True)` / `auto_now=True)`) unless noted; omitted from tables below for brevity.
- `company` FK — present on every tenant-scoped model via `TenantScopedModel`, `on_delete=PROTECT` (never CASCADE for tenant — a company is archived, not hard-deleted, per Section 15/42 of Phase 0).
- Money fields — `DecimalField(max_digits=14, decimal_places=2)`, never `FloatField`.
- All FKs default to `on_delete=models.PROTECT` unless stated otherwise (prevents silent data loss; explicit CASCADE only where truly a child record with no independent meaning, e.g. `JournalLine → JournalEntry`).

---

## 1. `apps/accounts` — Platform User

```python
class User(AbstractUser):
    # username kept as Django default login identifier OR switch to email-only login — decide in Phase 2
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)  # super admin flag, NOT tenant role
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
```

No `company` FK here — deliberately platform-wide, per Phase 0 Section 6.

---

## 2. `apps/tenants` — Company, Membership, RBAC

```python
class Company(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)               # reserved for future subdomain use, not routed on yet
    business_type = models.ForeignKey("modules.BusinessType", on_delete=models.PROTECT)
    registration_number = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    default_currency = models.CharField(max_length=3, default="QAR")  # single-currency v1, field kept flexible
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)       # False = archived, not deleted
    archived_at = models.DateTimeField(null=True, blank=True)

class Role(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=50)               # "Owner", "Accountant", "Staff", or custom
    is_system_role = models.BooleanField(default=False)   # True for the 3 seeded roles — cannot be deleted
    class Meta:
        unique_together = ("company", "name")

class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)  # e.g. "accounting.view_reports", "sales.create_invoice"
    label = models.CharField(max_length=255)
    module = models.CharField(max_length=50)               # groups permissions in the UI, e.g. "accounting"

class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    class Meta:
        unique_together = ("role", "permission")

class CompanyMembership(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("user", "company")
```

**Session state:** after login, `request.session['active_company_id']` (or a JWT claim for API) resolves to `request.company` in middleware — set once, read everywhere. Switching company re-resolves `request.role` and permission set.

---

## 3. `apps/modules` — Module Registry

```python
class BusinessType(models.Model):
    code = models.SlugField(unique=True)     # "gym", "textile", "general_retail"...
    name = models.CharField(max_length=100)

class Module(models.Model):
    code = models.SlugField(unique=True)     # "accounting", "gym"
    name = models.CharField(max_length=100)
    is_core = models.BooleanField(default=False)   # core modules always active, not toggleable

class BusinessTypeDefaultModule(models.Model):
    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    class Meta:
        unique_together = ("business_type", "module")

class CompanyModule(models.Model):
    company = models.ForeignKey("tenants.Company", on_delete=models.CASCADE, related_name="company_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ("company", "module")
```

`company.active_modules()` — helper method returning `Module` queryset where `is_core=True OR CompanyModule.is_active=True`.

---

## 4. `apps/subscriptions`

```python
class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_period = models.CharField(max_length=20, choices=[("monthly","Monthly"),("yearly","Yearly")], default="yearly")
    max_users = models.PositiveIntegerField(default=5)
    modules = models.ManyToManyField("modules.Module", related_name="plans")
    is_active = models.BooleanField(default=True)   # retire old plans without deleting

class Subscription(models.Model):
    STATUS = [("trial","Trial"),("active","Active"),("expired","Expired"),("cancelled","Cancelled")]
    company = models.OneToOneField("tenants.Company", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="trial")
    auto_renew = models.BooleanField(default=False)

class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=30, default="manual")  # abstraction point for future gateway
    reference = models.CharField(max_length=100, blank=True)

class SubscriptionRenewal(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="renewals")
    previous_end_date = models.DateField()
    new_end_date = models.DateField()
    renewed_at = models.DateTimeField(auto_now_add=True)
```

Celery beat daily task: for each `Subscription` with `status in [trial, active]`, compute `days_remaining = end_date - today`; fire notification at 30/15/7/3/1; if `days_remaining < 0`, set `status='expired'`.

---

## 5. `apps/accounting` — The Ledger (core of the system)

```python
class Account(TenantScopedModel):
    TYPE = [("asset","Asset"),("liability","Liability"),("equity","Equity"),("income","Income"),("expense","Expense")]
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=TYPE)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_system_account = models.BooleanField(default=False)  # seeded ones (Cash, AR, AP...) — cannot be deleted
    is_active = models.BooleanField(default=True)
    class Meta:
        unique_together = ("company", "code")

class JournalEntry(TenantScopedModel):
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)   # e.g. "SalesInvoice#123"
    memo = models.TextField(blank=True)
    source_type = models.CharField(max_length=50, blank=True)  # "sales_invoice", "purchase", "expense", "manual"
    source_id = models.PositiveIntegerField(null=True, blank=True)  # generic reference, no hard FK across apps
    posted_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    is_void = models.BooleanField(default=False)   # reversing entries, never hard-delete a posted entry

class JournalLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True)

class FiscalYear(TenantScopedModel):
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
```

`accounting.services.post_journal_entry(company, date, lines, reference, source_type, source_id, user)` — validates `sum(debit) == sum(credit)`, wraps in `transaction.atomic()`, is the **only** sanctioned write path into `JournalLine`.

---

## 6. `apps/customers` / `apps/suppliers`

```python
class Customer(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

class Supplier(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
```

---

## 7. `apps/inventory`

```python
class ProductCategory(TenantScopedModel):
    name = models.CharField(max_length=100)

class Brand(TenantScopedModel):
    name = models.CharField(max_length=100)

class Unit(TenantScopedModel):
    name = models.CharField(max_length=30)   # "pcs", "kg", "meter"

class Warehouse(TenantScopedModel):
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

class Product(TenantScopedModel):
    sku = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    class Meta:
        unique_together = ("company", "sku")

class StockMovement(TenantScopedModel):
    REASON = [("purchase","Purchase"),("sale","Sale"),("adjustment","Adjustment"),
              ("transfer_in","Transfer In"),("transfer_out","Transfer Out"),("return","Return")]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)  # signed: + in, - out
    reason = models.CharField(max_length=20, choices=REASON)
    reference = models.CharField(max_length=100, blank=True)  # e.g. "SalesInvoice#123"
    moved_at = models.DateTimeField(auto_now_add=True)
```

`Product.current_stock(warehouse=None)` — service function summing `StockMovement.quantity`, never a stored counter field (Phase 0 Section 18 risk).

---

## 8. `apps/sales`

```python
class Quotation(TenantScopedModel):
    STATUS = [("draft","Draft"),("sent","Sent"),("accepted","Accepted"),("rejected","Rejected"),("expired","Expired")]
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    notes = models.TextField(blank=True)

class SalesOrder(TenantScopedModel):
    STATUS = [("draft","Draft"),("confirmed","Confirmed"),("fulfilled","Fulfilled"),("cancelled","Cancelled")]
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="draft")

class SalesInvoice(TenantScopedModel):
    STATUS = [("unpaid","Unpaid"),("partial","Partially Paid"),("paid","Paid"),("void","Void")]
    sales_order = models.ForeignKey(SalesOrder, null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=30)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="unpaid")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, on_delete=models.SET_NULL)
    class Meta:
        unique_together = ("company", "invoice_number")

class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

class CustomerPayment(TenantScopedModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    invoice = models.ForeignKey(SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=30, default="cash")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, on_delete=models.SET_NULL)

class SalesReturn(TenantScopedModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    reason = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
```

`sales.services.create_invoice(...)` — in one `transaction.atomic()`: creates `SalesInvoice` + `SalesInvoiceLine`s → writes `StockMovement` (reason="sale", negative qty) per line → calls `accounting.services.post_journal_entry(...)` (Dr Accounts Receivable / Cr Sales Revenue + Cr Tax Payable if applicable) → links `journal_entry`. Any failure rolls back all three.

---

## 9. `apps/purchases` (mirror of sales)

```python
class PurchaseOrder(TenantScopedModel):
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=[("draft","Draft"),("confirmed","Confirmed"),("received","Received"),("cancelled","Cancelled")], default="draft")

class Purchase(TenantScopedModel):
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    bill_number = models.CharField(max_length=30, blank=True)
    date = models.DateField()
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=[("unpaid","Unpaid"),("partial","Partial"),("paid","Paid")], default="unpaid")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, on_delete=models.SET_NULL)

class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

class SupplierPayment(TenantScopedModel):
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    purchase = models.ForeignKey(Purchase, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=30, default="cash")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, on_delete=models.SET_NULL)

class PurchaseReturn(TenantScopedModel):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    reason = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
```

---

## 10. `apps/expenses`, `apps/employees`

```python
class ExpenseCategory(TenantScopedModel):
    name = models.CharField(max_length=100)

class Expense(TenantScopedModel):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=30, default="cash")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, on_delete=models.SET_NULL)

class Employee(TenantScopedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    role_title = models.CharField(max_length=100, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    joined_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
```

---

## 11. `apps/audit`

```python
class AuditLog(TenantScopedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)          # "create", "update", "delete", "login", ...
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    changes = models.JSONField(blank=True, default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
```

DB user for the app role gets `INSERT` only on this table (Phase 0 Section 14) — enforced via a Postgres `GRANT`, not Django.

---

## 12. Vertical Module Proof-of-Concept: `apps/verticals/gym`

Following the extension-table pattern — no forking of `Product`/`Customer`, only 1:1 or FK extensions.

```python
class MembershipPlan(TenantScopedModel):
    name = models.CharField(max_length=100)          # "Monthly", "Quarterly", "Annual"
    duration_days = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

class GymMember(TenantScopedModel):
    customer = models.OneToOneField("customers.Customer", on_delete=models.CASCADE, related_name="gym_member")
    membership_plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    join_date = models.DateField()
    membership_start = models.DateField()
    membership_end = models.DateField()
    status = models.CharField(max_length=20, choices=[("active","Active"),("expired","Expired"),("frozen","Frozen")], default="active")

class Attendance(TenantScopedModel):
    member = models.ForeignKey(GymMember, on_delete=models.CASCADE, related_name="attendance")
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
```

**Money flow:** a new `GymMember` membership purchase reuses `sales.services.create_invoice()` against a `Product` row representing the plan (or a dedicated `gym.services.enroll_member()` that itself calls `create_invoice` internally) — **never** a direct write to a revenue account. This is the exact rule from Phase 0 Section 18 ("business modules shortcutting the accounting engine") being enforced in the first vertical, so the pattern is correct before Textile/Spa/etc. copy it.

---

## 13. Cross-Cutting Notes for Phase 2

- **Migrations order:** `accounts → tenants → modules → subscriptions → accounting → customers/suppliers → inventory → sales → purchases → expenses → employees → audit → verticals.gym`. This matches the FK dependency graph above.
- **`TenantScopedModel` custom manager** (Phase 0 Section 3) will be implemented as a base in `apps/tenants/models.py` and imported by every app above — this is the single piece of shared infrastructure everything else depends on, so it's built first in Phase 2.
- **Seed data on company creation** (signal or service call at registration): default Chart of Accounts (Section 5), 3 system Roles + their RolePermissions, default Warehouse, `CompanyModule` rows from `BusinessTypeDefaultModule`.
- **Numbering schemes** (`invoice_number`, `bill_number`) — per-company sequential counters; exact implementation (DB sequence vs. a `CompanyCounter` model) to be decided in Phase 2 to avoid race conditions under concurrent invoice creation.

---

### Next step

Confirm this field-level design (or flag any model you want changed) and I'll move to **Phase 2: project scaffolding** — repo structure, `TenantScopedModel` + middleware implementation, initial migrations for the Foundation apps (`accounts`, `tenants`, `modules`, `subscriptions`), and the seed-data service.

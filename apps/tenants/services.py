"""
Service-layer functions for tenants. Views/viewsets call into these —
they never contain business logic themselves (Phase 0 Section 1).
"""
from django.db import transaction

from .models import Company, Role, Permission, RolePermission, CompanyMembership, CompanyCounter, CompanyOnboarding

SYSTEM_ROLES = ["Owner", "Accountant", "Staff"]

# Minimal seed permission set — expand as each app is scaffolded (Phase 1 Section 13).
DEFAULT_PERMISSIONS = [
    ("accounting.view_reports", "View financial reports", "accounting"),
    ("accounting.post_journal_entry", "Post journal entries", "accounting"),
    ("sales.create_invoice", "Create sales invoices", "sales"),
    ("sales.view_invoice", "View sales invoices", "sales"),
    ("purchases.create_purchase", "Create purchases", "purchases"),
    ("purchases.view_purchase", "View purchases", "purchases"),
    ("inventory.manage_stock", "Adjust stock", "inventory"),
    ("inventory.manage_products", "Manage products/categories/warehouses", "inventory"),
    ("inventory.view_products", "View products/stock", "inventory"),
    ("customers.manage", "Create/edit customers", "customers"),
    ("suppliers.manage", "Create/edit suppliers", "suppliers"),
    ("expenses.manage", "Record expenses", "expenses"),
    ("expenses.view", "View expenses", "expenses"),
    ("employees.manage", "Manage employee records", "employees"),
    ("employees.self_service", "Use employee self-service HR features", "employees"),
    ("employees.manage_payroll", "Manage payroll, overtime approvals and payslips", "employees"),
    ("tenants.manage_roles", "Manage roles and permissions", "tenants"),
    ("tenants.manage_members", "Invite/remove company members", "tenants"),
    ("accounting.manage_fiscal_years", "Create and close fiscal years", "accounting"),
    ("accounting.override_period_lock", "Post into a locked/closed period and reopen a closed fiscal year", "accounting"),
    ("banking.manage", "Manage bank/cash accounts, deposits, withdrawals, transfers, statement imports and matching", "banking"),
    ("banking.view", "View bank/cash accounts and reconciliation reports", "banking"),
    ("collections.view", "View AR/AP ageing reports and credit status", "collections"),
    ("collections.manage", "Add collection notes/follow-ups", "collections"),
    ("purchases.override_receiving_limits", "Receive or bill quantities beyond the ordered/received amount on a purchase order", "purchases"),
    ("sales.override_delivery_limits", "Deliver or invoice quantities beyond the ordered/delivered amount on a sales order", "sales"),
    ("sales.approve_discount", "Approve sales discounts above the configured threshold", "sales"),
    ("restaurant.manage", "Manage restaurant tables, orders, kitchen and shifts", "restaurant"),
]

# Owner gets everything; Accountant gets the accounting/sales/purchases set;
# Staff gets read/operational access only. Adjust per Phase 0 Section 6 ("Owner
# should be able to customize permissions" — this is just the seeded default).
ROLE_PERMISSION_MAP = {
    "Owner": [code for code, _, _ in DEFAULT_PERMISSIONS],
    "Accountant": [
        "accounting.view_reports", "accounting.post_journal_entry",
        "accounting.manage_fiscal_years",
        "banking.manage", "banking.view",
        "collections.view", "collections.manage",
        "sales.create_invoice", "sales.view_invoice",
        "purchases.create_purchase", "purchases.view_purchase",
        "expenses.manage", "expenses.view",
        "inventory.view_products", "customers.manage", "suppliers.manage",
        "employees.self_service",
        "employees.manage_payroll",
        "restaurant.manage",
    ],
    "Staff": [
        "sales.create_invoice", "sales.view_invoice",
        "inventory.manage_stock", "inventory.view_products",
        "customers.manage", "collections.view",
        "employees.self_service",
        "restaurant.manage",
    ],
}


def ensure_default_permissions():
    """Idempotent — safe to call on every deploy/migration."""
    for code, label, module in DEFAULT_PERMISSIONS:
        Permission.objects.get_or_create(code=code, defaults={"label": label, "module": module})


@transaction.atomic
def create_company_with_owner(*, user, name, slug, business_type, plan=None, **extra_fields):
    """
    Registration entry point: creates the Company, seeds system roles +
    role-permissions, seeds default modules for the business type
    (apps.modules.services), and makes `user` the Owner.

    Everything happens in one transaction — a partially-created company
    (e.g. Company row with no Owner membership) must never be possible.
    """
    ensure_default_permissions()

    company = Company.objects.create(
        name=name, slug=slug, business_type=business_type, **extra_fields
    )

    roles_by_name = {}
    for role_name in SYSTEM_ROLES:
        role = Role.objects.create(company=company, name=role_name, is_system_role=True)
        roles_by_name[role_name] = role
        perms = Permission.objects.filter(code__in=ROLE_PERMISSION_MAP[role_name])
        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=p) for p in perms]
        )

    CompanyMembership.objects.create(
        user=user, company=company, role=roles_by_name["Owner"]
    )

    # Deferred imports avoid a circular import between tenants <-> modules/subscriptions/accounting at app-load time.
    from apps.modules.services import activate_default_modules
    from apps.subscriptions.services import start_trial_subscription
    from apps.accounting.services import seed_chart_of_accounts
    from apps.expenses.services import seed_default_categories
    from apps.collections.services import seed_default_ageing_buckets

    activate_default_modules(company)
    start_trial_subscription(company, plan=plan)
    seed_chart_of_accounts(company)
    seed_default_categories(company)
    seed_default_ageing_buckets(company)
    CompanyOnboarding.objects.create(
        company=company, company_profile_complete=bool(company.name and company.country),
        accounting_setup_complete=True,
    )
    from apps.verticals.restaurant.starter_kit import install_for_new_company
    install_for_new_company(company, user)

    return company


@transaction.atomic
def complete_onboarding_step(*, company, step, value=True):
    from django.utils import timezone
    allowed = {
        "company_profile", "accounting_setup", "branch_setup", "products_setup",
        "team_setup", "tax_setup", "opening_balances",
    }
    if step not in allowed:
        raise ValueError("Unknown onboarding step.")
    state, _ = CompanyOnboarding.objects.select_for_update().get_or_create(company=company)
    setattr(state, f"{step}_complete", bool(value))
    state.save(update_fields=[f"{step}_complete", "updated_at"])
    if state.is_complete and state.completed_at is None:
        state.completed_at = timezone.now()
        state.save(update_fields=["completed_at"])
    elif not state.is_complete and state.completed_at is not None:
        state.completed_at = None
        state.save(update_fields=["completed_at"])
    return state


@transaction.atomic
def provision_company_basics(*, company):
    """Idempotently creates the minimum usable branch/unit for a new tenant."""
    from apps.inventory.models import Warehouse, Unit
    warehouse, _ = Warehouse.objects.get_or_create(
        company=company, name="Main Branch", defaults={"is_default": True, "is_active": True},
    )
    Unit.objects.get_or_create(company=company, name="pcs")
    state, _ = CompanyOnboarding.objects.get_or_create(company=company)
    state.branch_setup_complete = True
    state.save(update_fields=["branch_setup_complete", "updated_at"])
    return warehouse


@transaction.atomic
def invite_member(*, company, user, role):
    """
    Adds `user` to `company` under `role`. Enforces the plan's max_users at
    the point of creation with a clear error, not a silent failure
    (Phase 0 Section 7).
    """
    current_count = CompanyMembership.objects.filter(company=company, is_active=True).count()
    subscription = getattr(company, "subscription", None)
    if subscription and current_count >= subscription.plan.max_users and not subscription.plan.extra_user_price:
        raise ValueError(
            f"This company's plan allows a maximum of {subscription.plan.max_users} users."
        )
    membership, created = CompanyMembership.objects.get_or_create(
        user=user, company=company, defaults={"role": role, "is_active": True}
    )
    if not created:
        membership.role = role
        membership.is_active = True
        membership.save(update_fields=["role", "is_active"])
    return membership


def set_role_permissions(*, role, permission_codes):
    """
    Lets an Owner customize a (non-system) role's permission set
    (Phase 0 Section 6). System roles (Owner/Accountant/Staff) are not
    editable here — create a custom Role instead.
    """
    if role.is_system_role:
        raise ValueError("System roles cannot be edited directly — create a custom role instead.")
    perms = Permission.objects.filter(code__in=permission_codes)
    role.permissions.all().delete()
    RolePermission.objects.bulk_create([RolePermission(role=role, permission=p) for p in perms])
    return role


def next_counter_value(company, key):
    """
    Race-safe sequential counter (see CompanyCounter's docstring for why
    this exists). MUST be called from inside the caller's own
    `transaction.atomic()` block — e.g. sales.services.create_invoice,
    which already opens one around the whole invoice-creation flow — so
    that `select_for_update()`'s row lock is held for the entire
    document-creation transaction, not released early. Calling this
    outside a transaction raises under most backends (Postgres included)
    or silently doesn't lock (SQLite), so don't call it standalone.

    Two concurrent calls with the same (company, key) are serialized by
    Postgres at the row level: the second caller blocks until the first
    commits or rolls back, then sees the incremented value — never a
    duplicate.
    """
    counter, _ = CompanyCounter.objects.select_for_update().get_or_create(
        company=company, key=key, defaults={"last_value": 0}
    )
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    return counter.last_value

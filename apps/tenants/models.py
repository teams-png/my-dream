from django.db import models

from apps.common.validators import validate_upload_file
from django.conf import settings
from .managers import TenantManager


class TenantScopedModel(models.Model):
    """
    Abstract base for every tenant-scoped model in the system.

    Every model that inherits from this MUST be filtered through
    `objects` (TenantManager), which requires an explicit `company=`
    filter and refuses to return an unscoped queryset. This is the
    single most important enforcement point in the whole system
    (Phase 0 Section 3 / Section 14 — tenant isolation).

    Never trust a company/tenant id supplied by the client. The only
    sanctioned source of the active company is `request.company`,
    resolved server-side in ActiveCompanyMiddleware from the logged-in
    user's session-selected membership.
    """
    company = models.ForeignKey(
        "tenants.Company", on_delete=models.PROTECT, related_name="+"
    )

    objects = TenantManager()

    class Meta:
        abstract = True


class Company(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)  # reserved for future subdomain routing, not used yet
    business_type = models.ForeignKey(
        "modules.BusinessType", on_delete=models.PROTECT, related_name="companies"
    )
    registration_number = models.CharField(max_length=100, blank=True)
    vat_number = models.CharField(
        max_length=30, blank=True,
        help_text="Tax registration number printed on invoices (VAT TRN, KSA VAT no., India GSTIN).",
    )
    country = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True, validators=[validate_upload_file])
    onboarding_completed_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when the owner finishes or skips the first-run setup wizard.",
    )
    default_currency = models.CharField(max_length=3, default="QAR")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)  # False = archived, never hard-deleted
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def active_modules(self):
        """Core modules are always active; others depend on CompanyModule.is_active."""
        from apps.modules.models import Module
        return Module.objects.filter(
            models.Q(is_core=True) | models.Q(
                code__in=self.company_modules.filter(is_active=True).values_list("module__code", flat=True)
            )
        ).distinct()


class Role(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=50)
    is_system_role = models.BooleanField(default=False)  # Owner / Accountant / Staff — cannot be deleted
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self):
        return f"{self.company.name} / {self.name}"


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)  # e.g. "accounting.view_reports"
    label = models.CharField(max_length=255)
    module = models.CharField(max_length=50)

    def __str__(self):
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("role", "permission")


class CompanyMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    # Branches this person works at. Empty = every branch. Owners always see every branch.
    warehouses = models.ManyToManyField("inventory.Warehouse", blank=True, related_name="+")

    class Meta:
        unique_together = ("user", "company")

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role.name})"


class CompanyOnboarding(models.Model):
    """Persistent setup checklist for a newly provisioned tenant."""
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="onboarding")
    company_profile_complete = models.BooleanField(default=False)
    accounting_setup_complete = models.BooleanField(default=False)
    branch_setup_complete = models.BooleanField(default=False)
    products_setup_complete = models.BooleanField(default=False)
    team_setup_complete = models.BooleanField(default=False)
    tax_setup_complete = models.BooleanField(default=False)
    opening_balances_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_complete(self):
        return all((
            self.company_profile_complete, self.accounting_setup_complete,
            self.branch_setup_complete, self.products_setup_complete,
            self.team_setup_complete, self.tax_setup_complete,
            self.opening_balances_complete,
        ))


class CompanyCounter(models.Model):
    """
    Race-safe per-company sequential counter, used anywhere a document
    number (invoice, bill, receipt...) must never collide or skip under
    concurrent requests. `key` namespaces independent sequences within
    the same company (e.g. "sales_invoice" vs a future "purchase_bill").

    Closes the gap flagged since Phase 1 Section 13: the original
    `_next_invoice_number()` in apps.sales.services read the last row and
    added 1 with no locking — two concurrent requests could read the same
    "last" value and generate the same invoice number. See
    tenants.services.next_counter_value() for the locking implementation.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="counters")
    key = models.CharField(max_length=50)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("company", "key")

    def __str__(self):
        return f"{self.company.name} / {self.key} = {self.last_value}"

class CompanyBusinessType(models.Model):
    """Additional business suites enabled inside one legal company/accounting tenant."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="business_suites")
    business_type = models.ForeignKey("modules.BusinessType", on_delete=models.PROTECT, related_name="company_suites")
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "business_type")

    def __str__(self):
        return f"{self.company.name} / {self.business_type.name}"

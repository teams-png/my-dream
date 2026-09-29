"""
Phase 28 (Fiscal Years / Period Locking): new permission codes
"accounting.manage_fiscal_years" and "accounting.override_period_lock"
only get attached to a company's Owner/Accountant roles inside
create_company_with_owner() -- i.e. at signup time. Existing companies
created before this phase would otherwise never get them. This backfills
every already-existing company so the feature works immediately for
current customers, per the "migration-safe defaults for existing
companies and data" requirement.

Idempotent (get_or_create throughout) -- safe to run more than once,
e.g. if migrated twice in different environments.
"""
from django.db import migrations


NEW_PERMISSIONS = [
    ("accounting.manage_fiscal_years", "Create and close fiscal years", "accounting"),
    ("accounting.override_period_lock", "Post into a locked/closed period and reopen a closed fiscal year", "accounting"),
]

# Mirrors apps.tenants.services.ROLE_PERMISSION_MAP's Phase 28 additions --
# Owner gets both, Accountant gets manage_fiscal_years only, Staff gets neither.
ROLE_GRANTS = {
    "Owner": ["accounting.manage_fiscal_years", "accounting.override_period_lock"],
    "Accountant": ["accounting.manage_fiscal_years"],
}


def backfill_permissions(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Role = apps.get_model("tenants", "Role")
    RolePermission = apps.get_model("tenants", "RolePermission")

    permission_objs = {}
    for code, label, module in NEW_PERMISSIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"label": label, "module": module}
        )
        permission_objs[code] = perm

    for role_name, codes in ROLE_GRANTS.items():
        for role in Role.objects.filter(name=role_name, is_system_role=True):
            for code in codes:
                RolePermission.objects.get_or_create(
                    role=role, permission=permission_objs[code]
                )


def noop_reverse(apps, schema_editor):
    """Not reversed -- removing a permission grant on migrate-back could
    silently take away access a company owner has already been using."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_company_country'),
    ]

    operations = [
        migrations.RunPython(backfill_permissions, noop_reverse),
    ]

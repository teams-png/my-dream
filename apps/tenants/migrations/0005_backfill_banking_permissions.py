"""
Phase 29 (Bank and Cash Management + Reconciliation): new permission
codes "banking.manage" and "banking.view" only get attached to a
company's Owner/Accountant roles inside create_company_with_owner() --
i.e. at signup time. Existing companies created before this phase would
otherwise never get them. Backfills every already-existing company, same
pattern as 0004_backfill_fiscal_year_permissions.

Idempotent (get_or_create throughout).
"""
from django.db import migrations


NEW_PERMISSIONS = [
    ("banking.manage", "Manage bank/cash accounts, deposits, withdrawals, transfers, statement imports and matching", "banking"),
    ("banking.view", "View bank/cash accounts and reconciliation reports", "banking"),
]

ROLE_GRANTS = {
    "Owner": ["banking.manage", "banking.view"],
    "Accountant": ["banking.manage", "banking.view"],
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
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_backfill_fiscal_year_permissions'),
    ]

    operations = [
        migrations.RunPython(backfill_permissions, noop_reverse),
    ]

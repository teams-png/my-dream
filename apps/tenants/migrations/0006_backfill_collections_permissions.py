"""
Phase 30 (AR/AP Ageing and Collections): new permission codes
"collections.view" and "collections.manage" only get attached at
signup time. Backfills every already-existing company's Owner/
Accountant/Staff roles, same pattern as the two prior phases' backfills.
"""
from django.db import migrations


NEW_PERMISSIONS = [
    ("collections.view", "View AR/AP ageing reports and credit status", "collections"),
    ("collections.manage", "Add collection notes/follow-ups", "collections"),
]

ROLE_GRANTS = {
    "Owner": ["collections.view", "collections.manage"],
    "Accountant": ["collections.view", "collections.manage"],
    "Staff": ["collections.view"],
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
        ('tenants', '0005_backfill_banking_permissions'),
    ]

    operations = [
        migrations.RunPython(backfill_permissions, noop_reverse),
    ]

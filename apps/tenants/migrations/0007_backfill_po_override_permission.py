"""
Phase 32 (Purchase Order -> Goods Receipt -> Supplier Bill Workflow):
new permission "purchases.override_receiving_limits" only gets attached
to a company's Owner role inside create_company_with_owner() -- i.e. at
signup time. Backfills every already-existing company's Owner role,
same pattern as the three prior phases' backfills.
"""
from django.db import migrations


NEW_PERMISSIONS = [
    ("purchases.override_receiving_limits", "Receive or bill quantities beyond the ordered/received amount on a purchase order", "purchases"),
]

ROLE_GRANTS = {
    "Owner": ["purchases.override_receiving_limits"],
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
        ('tenants', '0006_backfill_collections_permissions'),
    ]

    operations = [
        migrations.RunPython(backfill_permissions, noop_reverse),
    ]

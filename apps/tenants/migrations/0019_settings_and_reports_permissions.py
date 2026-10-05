"""Two new permissions: business settings and reports.

Owners get both; Accountants get reports. A custom role keeps what it could open before:
reports if it could see financial reports, settings if it could manage roles."""
from django.db import migrations

NEW = [
    ("business.manage_settings", "Business settings, branches, website, online orders/booking setup, backups and data export", "tenants"),
    ("reports.view", "See sales reports, analytics, profit figures and exports", "reports"),
]


def grant(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Role = apps.get_model("tenants", "Role")
    RolePermission = apps.get_model("tenants", "RolePermission")
    perms = {code: Permission.objects.get_or_create(code=code, defaults={"label": label, "module": module})[0]
             for code, label, module in NEW}

    def give(roles, code):
        RolePermission.objects.bulk_create([RolePermission(role_id=r, permission=perms[code]) for r in roles],
                                           ignore_conflicts=True)

    owners = list(Role.objects.filter(name="Owner", is_system_role=True).values_list("id", flat=True))
    give(owners, "business.manage_settings")
    give(owners, "reports.view")
    give(list(Role.objects.filter(name="Accountant", is_system_role=True).values_list("id", flat=True)), "reports.view")
    custom = Role.objects.filter(is_system_role=False)
    give(list(custom.filter(permissions__permission__code="accounting.view_reports").values_list("id", flat=True)),
         "reports.view")
    give(list(custom.filter(permissions__permission__code="tenants.manage_roles").values_list("id", flat=True)),
         "business.manage_settings")


class Migration(migrations.Migration):
    dependencies = [("tenants", "0018_backups")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]

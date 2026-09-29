from django.db import migrations


def forwards(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Role = apps.get_model("tenants", "Role")
    RolePermission = apps.get_model("tenants", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code="sales.approve_discount",
        defaults={"label": "Approve sales discounts above the configured threshold", "module": "sales"},
    )
    for role in Role.objects.filter(name="Owner"):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def backwards(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Permission.objects.filter(code="sales.approve_discount").delete()


class Migration(migrations.Migration):
    dependencies = [("tenants", "0008_backfill_so_override_permission")]
    operations = [migrations.RunPython(forwards, backwards)]

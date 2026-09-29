from django.db import migrations

def forwards(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Role = apps.get_model("tenants", "Role")
    RolePermission = apps.get_model("tenants", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code="employees.self_service",
        defaults={"label": "Use employee self-service HR features", "module": "employees"},
    )
    for role in Role.objects.filter(name__in=["Owner", "Accountant", "Staff"]):
        RolePermission.objects.get_or_create(role=role, permission=permission)

def backwards(apps, schema_editor):
    apps.get_model("tenants", "Permission").objects.filter(code="employees.self_service").delete()

class Migration(migrations.Migration):
    dependencies = [("tenants", "0009_backfill_discount_approval_permission")]
    operations = [migrations.RunPython(forwards, backwards)]

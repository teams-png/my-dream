from django.db import migrations


def forwards(apps, schema_editor):
    Permission = apps.get_model("tenants", "Permission")
    Role = apps.get_model("tenants", "Role")
    RolePermission = apps.get_model("tenants", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code="employees.manage_payroll",
        defaults={"label": "Manage payroll, overtime approvals and payslips", "module": "employees"},
    )
    for role in Role.objects.filter(name__in=["Owner", "Accountant"]):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def backwards(apps, schema_editor):
    apps.get_model("tenants", "Permission").objects.filter(code="employees.manage_payroll").delete()


class Migration(migrations.Migration):
    dependencies = [("tenants", "0010_backfill_employee_self_service_permission")]
    operations = [migrations.RunPython(forwards, backwards)]

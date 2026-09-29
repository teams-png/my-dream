from django.db import migrations, models
import django.db.models.deletion


def seed_primary(apps, schema_editor):
    Company = apps.get_model("tenants", "Company")
    CompanyBusinessType = apps.get_model("tenants", "CompanyBusinessType")
    for company in Company.objects.all().iterator():
        CompanyBusinessType.objects.get_or_create(company_id=company.id, business_type_id=company.business_type_id, defaults={"is_primary": True, "is_active": True})

class Migration(migrations.Migration):
    dependencies = [("tenants", "0012_companyonboarding"), ("modules", "0002_initial")]
    operations = [
        migrations.CreateModel(
            name="CompanyBusinessType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("is_primary", models.BooleanField(default=False)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                ("business_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="company_suites", to="modules.businesstype")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="business_suites", to="tenants.company")),
            ],
            options={"unique_together": {("company", "business_type")}},
        ),
        migrations.RunPython(seed_primary, migrations.RunPython.noop),
    ]

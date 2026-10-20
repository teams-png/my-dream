from django.db import migrations


def add(apps, schema_editor):
    Module = apps.get_model("modules", "Module")
    Module.objects.get_or_create(code="ai_assistant",
                                 defaults={"name": "Ask BookPilot (AI) · advanced add-on", "is_core": False})


class Migration(migrations.Migration):
    dependencies = [("modules", "0002_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]

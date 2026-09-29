from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0007_alter_stockmovement_reason")]

    operations = [
        migrations.AddField(model_name="product", name="size", field=models.CharField(blank=True, db_index=True, max_length=50)),
        migrations.AddField(model_name="product", name="colour", field=models.CharField(blank=True, db_index=True, max_length=50)),
        migrations.AddField(model_name="product", name="material", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="product", name="design", field=models.CharField(blank=True, max_length=100)),
    ]

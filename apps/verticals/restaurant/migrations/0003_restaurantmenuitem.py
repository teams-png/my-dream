import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0008_product_boutique_attributes"),
        ("restaurant", "0002_deliveryintegration_deliveryorderimport"),
        ("tenants", "0012_companyonboarding"),
    ]

    operations = [
        migrations.CreateModel(
            name="RestaurantMenuItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.TextField(blank=True)),
                ("image", models.ImageField(blank=True, upload_to="restaurant/menu/%Y/%m/")),
                ("preparation_minutes", models.PositiveSmallIntegerField(default=10)),
                ("spice_level", models.CharField(choices=[("none", "Not spicy"), ("mild", "Mild"), ("medium", "Medium"), ("hot", "Hot")], default="none", max_length=10)),
                ("is_vegetarian", models.BooleanField(default=False)),
                ("is_featured", models.BooleanField(default=False)),
                ("is_available", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
                ("product", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="restaurant_menu_item", to="inventory.product")),
            ],
            options={"ordering": ["sort_order", "product__name"]},
        ),
    ]

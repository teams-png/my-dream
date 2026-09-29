import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0008_product_boutique_attributes"),
        ("restaurant", "0003_restaurantmenuitem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RestaurantProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_menu_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("tagline", models.CharField(blank=True, max_length=180)),
                ("opening_hours", models.CharField(blank=True, max_length=180)),
                ("delivery_minimum", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("delivery_charge", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("qr_ordering_enabled", models.BooleanField(default=False)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("company",), name="one_restaurant_profile_per_company")]},
        ),
        migrations.CreateModel(
            name="KitchenStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("colour", models.CharField(default="#f97316", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("categories", models.ManyToManyField(blank=True, related_name="kitchen_stations", to="inventory.productcategory")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
            ],
        ),
        migrations.CreateModel(
            name="MenuModifierGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("min_selections", models.PositiveSmallIntegerField(default=0)),
                ("max_selections", models.PositiveSmallIntegerField(default=1)),
                ("is_required", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
            ],
        ),
        migrations.CreateModel(
            name="FoodWaste",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("reason", models.CharField(choices=[("expired", "Expired"), ("spoiled", "Spoiled"), ("preparation", "Preparation waste"), ("customer_return", "Customer return"), ("other", "Other")], max_length=20)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
                ("ingredient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="restaurant_waste", to="inventory.product")),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="restaurant_waste_recorded", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.warehouse")),
            ],
        ),
        migrations.CreateModel(
            name="TableReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("customer_name", models.CharField(max_length=150)),
                ("phone", models.CharField(max_length=30)),
                ("reservation_at", models.DateTimeField()),
                ("guest_count", models.PositiveSmallIntegerField(default=2)),
                ("status", models.CharField(choices=[("booked", "Booked"), ("seated", "Seated"), ("completed", "Completed"), ("cancelled", "Cancelled"), ("no_show", "No-show")], default="booked", max_length=12)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
                ("table", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reservations", to="restaurant.diningtable")),
            ],
            options={"ordering": ["reservation_at"]},
        ),
        migrations.CreateModel(
            name="MenuModifierOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenants.company")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="restaurant.menumodifiergroup")),
                ("modifier", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="group_options", to="restaurant.menumodifier")),
            ],
            options={"ordering": ["sort_order", "modifier__name"], "unique_together": {("group", "modifier")}},
        ),
        migrations.AddField(model_name="restaurantmenuitem", name="available_from", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="restaurantmenuitem", name="available_until", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="restaurantmenuitem", name="modifier_groups", field=models.ManyToManyField(blank=True, related_name="menu_items", to="restaurant.menumodifiergroup")),
        migrations.AddField(model_name="restaurantorder", name="reservation", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="restaurant.tablereservation")),
        migrations.AddField(model_name="kitchenticket", name="priority", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="kitchenticket", name="station", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="restaurant.kitchenstation")),
    ]

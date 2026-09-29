import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurant", "0004_restaurant_operations_pack"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="restaurantorder", name="public_order_token", field=models.UUIDField(blank=True, editable=False, null=True, unique=True)),
        migrations.AddField(model_name="restaurantorder", name="cancelled_reason", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="restaurantorder", name="cancelled_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="restaurantorder", name="cancelled_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="restaurant_orders_cancelled", to=settings.AUTH_USER_MODEL)),
    ]

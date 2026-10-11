"""A product whose stock lives on its size / colour variants is not itself stock-tracked, so it never shows as
"out of stock" on the overview, low-stock lists or reorder reports. Only parents with no stock of their own."""
from django.db import migrations
from django.db.models import Sum


def forwards(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    StockMovement = apps.get_model("inventory", "StockMovement")
    parents = Product.objects.filter(is_stock_tracked=True, variants__isnull=False).distinct()
    for parent in parents:
        held = StockMovement.objects.filter(product=parent).aggregate(t=Sum("quantity"))["t"] or 0
        if not held:
            Product.objects.filter(pk=parent.pk).update(is_stock_tracked=False)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0009_product_image")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]

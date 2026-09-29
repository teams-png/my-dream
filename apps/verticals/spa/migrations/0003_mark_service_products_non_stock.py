# Generated manually — Phase 24, mirrors gym's 0003 migration exactly.

from django.db import migrations


def mark_non_stock(apps, schema_editor):
    SpaService = apps.get_model('spa', 'SpaService')
    ServicePackage = apps.get_model('spa', 'ServicePackage')
    Product = apps.get_model('inventory', 'Product')
    product_ids = set(SpaService.objects.exclude(product__isnull=True).values_list('product_id', flat=True))
    product_ids |= set(ServicePackage.objects.exclude(product__isnull=True).values_list('product_id', flat=True))
    Product.objects.filter(id__in=list(product_ids)).update(is_stock_tracked=False)


def reverse(apps, schema_editor):
    SpaService = apps.get_model('spa', 'SpaService')
    ServicePackage = apps.get_model('spa', 'ServicePackage')
    Product = apps.get_model('inventory', 'Product')
    product_ids = set(SpaService.objects.exclude(product__isnull=True).values_list('product_id', flat=True))
    product_ids |= set(ServicePackage.objects.exclude(product__isnull=True).values_list('product_id', flat=True))
    Product.objects.filter(id__in=list(product_ids)).update(is_stock_tracked=True)


class Migration(migrations.Migration):

    dependencies = [
        ('spa', '0002_spaservice_product_servicepackage_product'),
        ('inventory', '0004_product_is_stock_tracked'),
    ]

    operations = [
        migrations.RunPython(mark_non_stock, reverse),
    ]

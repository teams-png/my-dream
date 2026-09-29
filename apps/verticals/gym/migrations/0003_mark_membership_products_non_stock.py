# Generated manually — Phase 24. Existing MembershipPlan.product rows created before
# Product.is_stock_tracked existed default to True; this backfills them to False so they
# stop showing up in stock_report / low-stock notifications and drifting negative.

from django.db import migrations


def mark_non_stock(apps, schema_editor):
    MembershipPlan = apps.get_model('gym', 'MembershipPlan')
    Product = apps.get_model('inventory', 'Product')
    product_ids = MembershipPlan.objects.exclude(product__isnull=True).values_list('product_id', flat=True)
    Product.objects.filter(id__in=list(product_ids)).update(is_stock_tracked=False)


def reverse(apps, schema_editor):
    MembershipPlan = apps.get_model('gym', 'MembershipPlan')
    Product = apps.get_model('inventory', 'Product')
    product_ids = MembershipPlan.objects.exclude(product__isnull=True).values_list('product_id', flat=True)
    Product.objects.filter(id__in=list(product_ids)).update(is_stock_tracked=True)


class Migration(migrations.Migration):

    dependencies = [
        ('gym', '0002_membershipplan_product'),
        ('inventory', '0004_product_is_stock_tracked'),
    ]

    operations = [
        migrations.RunPython(mark_non_stock, reverse),
    ]

# Generated manually — Phase 24 (non-stock / service product distinction).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_warehouse_address_warehouse_is_active_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_stock_tracked',
            field=models.BooleanField(
                default=True,
                help_text=(
                    "False for service-type products (gym memberships, spa sessions, ...) that get "
                    "invoiced through sales.services.create_invoice() but have no physical stock to "
                    "move. When False: create_invoice()/process_return() skip writing a StockMovement "
                    "for this product, and it's excluded from reports.stock_report and the low-stock "
                    "notification sweep. See docs/phase1-database-design.md — introduced to fix the "
                    "'service product drifts negative in stock reports' quirk flagged in the gym and "
                    "spa vertical notes."
                ),
            ),
        ),
    ]

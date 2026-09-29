from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('subscriptions','0004_subscription_downgrade_effective_on_and_more'),('tenants','0013_companybusinesstype')]
    operations=[
      migrations.CreateModel(name='ClientCommercialProfile',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('max_branches',models.PositiveIntegerField(default=1)),('max_pos_terminals',models.PositiveIntegerField(default=1)),('api_calls_per_month',models.PositiveIntegerField(default=0,help_text='0 means unlimited')),('custom_monthly_price',models.DecimalField(blank=True,decimal_places=2,max_digits=10,null=True)),('reseller_name',models.CharField(blank=True,max_length=120)),('white_label_name',models.CharField(blank=True,max_length=120)),('custom_domain',models.CharField(blank=True,max_length=255)),('admin_notes',models.TextField(blank=True)),('updated_at',models.DateTimeField(auto_now=True)),('company',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name='commercial_profile',to='tenants.company'))]),
      migrations.CreateModel(name='UsageSnapshot',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('period',models.CharField(help_text='YYYY-MM',max_length=7)),('invoices',models.PositiveIntegerField(default=0)),('api_calls',models.PositiveIntegerField(default=0)),('storage_mb',models.PositiveIntegerField(default=0)),('captured_at',models.DateTimeField(auto_now=True)),('company',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='usage_snapshots',to='tenants.company'))],options={'unique_together':{('company','period')}}),
    ]

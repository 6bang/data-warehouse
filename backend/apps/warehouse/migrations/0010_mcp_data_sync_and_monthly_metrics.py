from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0009_accessrole_accountprofile_allowed_shops_and_more")]

    operations = [
        migrations.AddField(
            model_name="mcpserverconfig",
            name="data_sync_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="organization_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="monthlyproductfact",
            name="sales_volume",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="monthlyproductfact",
            name="visitors",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="monthlyproductfact",
            name="conversion_rate",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="monthlyproductfact",
            name="stock",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0010_mcp_data_sync_and_monthly_metrics")]

    operations = [
        migrations.AddField(
            model_name="mcpserverconfig",
            name="schedule_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="schedule_interval_minutes",
            field=models.PositiveSmallIntegerField(default=120),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="last_sync_attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="consecutive_sync_failures",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="sync_in_progress",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="mcpserverconfig",
            name="sync_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

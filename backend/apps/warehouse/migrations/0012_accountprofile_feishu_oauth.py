from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0011_mcp_automatic_sync_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="feishu_open_id",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="feishu_union_id",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="feishu_user_id",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="feishu_tenant_key",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="feishu_last_login_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0012_accountprofile_feishu_oauth"),
    ]

    operations = [
        migrations.AddField(
            model_name="feishuintegration",
            name="allowed_tenant_keys",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]

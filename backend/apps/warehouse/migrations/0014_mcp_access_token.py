from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0013_feishuintegration_allowed_tenant_keys"),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPAccessToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                ("token_prefix", models.CharField(max_length=20)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("allowed_tools", models.JSONField(blank=True, default=list)),
                ("allowed_shops", models.JSONField(blank=True, default=list)),
                ("enabled", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_mcp_access_tokens", to=settings.AUTH_USER_MODEL)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mcp_access_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "mcp_access_token", "ordering": ["-created_at", "id"]},
        ),
    ]

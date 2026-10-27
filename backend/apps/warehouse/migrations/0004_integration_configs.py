from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0003_accountprofile_approval"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeishuIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(default="飞书经营数据", max_length=100)),
                ("app_id", models.CharField(blank=True, max_length=100)),
                ("app_secret_encrypted", models.TextField(blank=True)),
                ("default_base_url", models.URLField(blank=True, max_length=1000)),
                ("enabled", models.BooleanField(default=False)),
                ("connection_status", models.CharField(choices=[("untested", "未测试"), ("connected", "已连接"), ("error", "连接失败")], default="untested", max_length=16)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_feishu_integrations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "feishu_integration"},
        ),
        migrations.CreateModel(
            name="AIProviderConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("provider", models.CharField(choices=[("deepseek", "DeepSeek"), ("openai", "OpenAI"), ("custom", "OpenAI 兼容服务")], default="deepseek", max_length=20)),
                ("api_base_url", models.URLField(max_length=500)),
                ("model", models.CharField(max_length=100)),
                ("api_key_encrypted", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("connection_status", models.CharField(choices=[("untested", "未测试"), ("connected", "已连接"), ("error", "连接失败")], default="untested", max_length=16)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_ai_providers", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "ai_provider_config", "ordering": ["-is_default", "name"]},
        ),
        migrations.CreateModel(
            name="MCPServerConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("endpoint_url", models.URLField(max_length=1000)),
                ("auth_type", models.CharField(choices=[("none", "无认证"), ("bearer", "Bearer Token")], default="none", max_length=16)),
                ("auth_token_encrypted", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=False)),
                ("agent_query_enabled", models.BooleanField(default=False)),
                ("allow_private_network", models.BooleanField(default=False)),
                ("allowed_tools", models.JSONField(blank=True, default=list)),
                ("discovered_tools", models.JSONField(blank=True, default=list)),
                ("protocol_version", models.CharField(default="2025-06-18", max_length=20)),
                ("connection_status", models.CharField(choices=[("untested", "未测试"), ("connected", "已连接"), ("error", "连接失败")], default="untested", max_length=16)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_mcp_servers", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "mcp_server_config", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="IntegrationEventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("integration_type", models.CharField(max_length=20)),
                ("integration_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("action", models.CharField(max_length=50)),
                ("success", models.BooleanField(default=True)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="integration_events", to=settings.AUTH_USER_MODEL)),
                ("ai_analysis_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="integration_events", to="warehouse.aianalysisrun")),
            ],
            options={"db_table": "integration_event_log", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="integrationeventlog",
            index=models.Index(fields=["integration_type", "created_at"], name="integration_integra_fb411b_idx"),
        ),
    ]

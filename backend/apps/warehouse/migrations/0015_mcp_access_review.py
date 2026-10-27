from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_permission_codes(apps, schema_editor):
    MCPAccessToken = apps.get_model("warehouse", "MCPAccessToken")
    tool_permissions = {
        "query_realtime_metrics": "realtime.view",
        "query_monthly_metrics": "monthly.view",
        "list_business_dimensions": "dimensions.view",
    }
    for token in MCPAccessToken.objects.all().iterator():
        codes = sorted({tool_permissions[name] for name in (token.allowed_tools or []) if name in tool_permissions})
        if codes:
            MCPAccessToken.objects.filter(pk=token.pk).update(permission_codes=codes)


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0014_mcp_access_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="agent_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="agent_platform",
            field=models.CharField(default="feishu", max_length=30),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="agent_id",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="permission_codes",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="approval_status",
            field=models.CharField(choices=[("pending", "待审核"), ("approved", "已通过"), ("rejected", "已驳回")], default="approved", max_length=16),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="review_note",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mcpaccesstoken",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_mcp_access_tokens", to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_permission_codes, migrations.RunPython.noop),
    ]

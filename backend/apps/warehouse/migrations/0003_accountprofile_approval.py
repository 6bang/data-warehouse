from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0002_aianalysisrun_month"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="accountprofile",
            name="approval_status",
            field=models.CharField(
                choices=[("pending", "待审批"), ("approved", "已批准"), ("rejected", "已拒绝")],
                default="approved",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="review_note",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountprofile",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

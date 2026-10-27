from django.db import migrations


class Migration(migrations.Migration):
    """Remove the third-party account/password connector; MCP and file import remain."""

    dependencies = [
        ("warehouse", "0017_structured_operation_strategies"),
    ]

    operations = [
        migrations.DeleteModel(name="ChachazhanIntegration"),
    ]

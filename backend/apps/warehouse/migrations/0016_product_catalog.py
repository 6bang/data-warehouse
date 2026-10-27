from django.db import migrations, models


def backfill_product_catalog(apps, schema_editor):
    MonthlyProductFact = apps.get_model("warehouse", "MonthlyProductFact")
    ProductCatalog = apps.get_model("warehouse", "ProductCatalog")
    for fact in MonthlyProductFact.objects.all().iterator():
        if not fact.product_id or not fact.shop:
            continue
        identity = {
            "organization": fact.organization,
            "platform": fact.platform or "未识别平台",
            "shop": fact.shop or "未识别店铺",
            "product_id": fact.product_id,
        }
        defaults = {
            "shop_id": fact.shop_id or "",
            "product_name": fact.product_name or "",
            "product_code": fact.product_code or "",
            "product_created_at": fact.product_created_at,
            "product_image_url": fact.product_image_url or "",
            "last_seen_month": fact.month or "",
            "source": fact.source or "monthly_product_fact",
            "raw_payload": fact.raw_payload or {},
        }
        catalog, created = ProductCatalog.objects.get_or_create(defaults=defaults, **identity)
        if not created:
            changed = []
            for field, value in defaults.items():
                current = getattr(catalog, field)
                if value not in (None, "", {}) and current != value:
                    setattr(catalog, field, value)
                    changed.append(field)
            if changed:
                catalog.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0015_mcp_access_review"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCatalog",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("organization", models.CharField(db_index=True, max_length=150)),
                ("platform", models.CharField(blank=True, default="未识别平台", max_length=50)),
                ("shop_id", models.CharField(blank=True, max_length=100)),
                ("shop", models.CharField(blank=True, default="未识别店铺", max_length=150)),
                ("product_id", models.CharField(max_length=150)),
                ("product_name", models.CharField(blank=True, max_length=500)),
                ("product_code", models.CharField(blank=True, max_length=150)),
                ("product_created_at", models.DateTimeField(blank=True, null=True)),
                ("product_image_url", models.URLField(blank=True, max_length=1000)),
                ("last_seen_month", models.CharField(blank=True, max_length=7)),
                ("source", models.CharField(default="monthly_product_fact", max_length=50)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "product_catalog",
                "ordering": ["-product_created_at", "product_name", "product_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="productcatalog",
            constraint=models.UniqueConstraint(
                fields=("organization", "platform", "shop", "product_id"),
                name="uniq_product_catalog_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="productcatalog",
            index=models.Index(fields=["organization", "product_name"], name="product_catalog_org_name_idx"),
        ),
        migrations.AddIndex(
            model_name="productcatalog",
            index=models.Index(fields=["product_created_at"], name="product_catalog_created_idx"),
        ),
        migrations.AddIndex(
            model_name="productcatalog",
            index=models.Index(fields=["shop", "product_id"], name="prod_catalog_shop_prod_idx"),
        ),
        migrations.RunPython(backfill_product_catalog, migrations.RunPython.noop),
    ]

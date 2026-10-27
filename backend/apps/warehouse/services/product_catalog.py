from django.db import transaction

from apps.warehouse.models import MonthlyProductFact, ProductCatalog
from apps.warehouse.services.product_images import enrich_product_images, normalize_product_image_url


def sync_catalog_from_facts(facts, *, source="monthly_product_fact"):
    """将月度事实中的商品身份字段合并到独立商品主档案。"""
    count = 0
    with transaction.atomic():
        # Materialise once so the bounded image resolver can fill gaps from
        # catalog/other months without N+1 queries. This never changes metrics.
        iterable = list(facts.iterator()) if hasattr(facts, "iterator") else list(facts)
        original_images = {getattr(item, "pk", None): getattr(item, "product_image_url", "") for item in iterable}
        enrich_product_images(iterable)
        fact_images = [item for item in iterable if isinstance(item, MonthlyProductFact)
                       and item.pk and item.product_image_url != original_images.get(item.pk, "")]
        if fact_images:
            MonthlyProductFact.objects.bulk_update(fact_images, ["product_image_url"], batch_size=400)
        for fact in iterable:
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
                "product_image_url": normalize_product_image_url(fact.product_image_url) or "",
                "last_seen_month": fact.month or "",
                "source": source or fact.source or "monthly_product_fact",
                "raw_payload": fact.raw_payload or {},
            }
            catalog, created = ProductCatalog.objects.get_or_create(defaults=defaults, **identity)
            if not created:
                # 上游某个月份缺字段时，不覆盖主档案中已有的非空值。
                changed = []
                for field, value in defaults.items():
                    current = getattr(catalog, field)
                    if value not in (None, "", {}) and current != value:
                        setattr(catalog, field, value)
                        changed.append(field)
                if changed:
                    catalog.save(update_fields=[*changed, "updated_at"])
            count += 1
    return count


def backfill_catalog_from_facts():
    return sync_catalog_from_facts(MonthlyProductFact.objects.all())

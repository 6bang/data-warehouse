from django.db import migrations


def seed_templates(apps, schema_editor):
    OperationStrategy = apps.get_model("warehouse", "OperationStrategy")
    StrategyRule = apps.get_model("warehouse", "StrategyRule")
    templates = [
        {
            "name": "新品上架 30 天预警",
            "strategy_type": "new_product",
            "description": "新品上架 30 天内自动检查成交、广告产出，及时进入破零和素材优化计划。",
            "new_product_days": 30,
            "rules": [
                {"name": "新品尚未破零", "metric": "sales", "operator": "lte", "threshold": 0, "level": "critical", "suggestion": "检查商品链接、主图、标题和首轮引流，24 小时内制定破零动作。"},
                {"name": "新品广告 ROI 偏低", "metric": "roi", "operator": "lt", "threshold": 1, "level": "warning", "suggestion": "复核关键词与人群包，暂停持续消耗且无成交的单元。"},
            ],
        },
        {
            "name": "老品利润与退款预警",
            "strategy_type": "mature_product",
            "description": "老品按月检查毛利率和退款率，避免规模增长掩盖利润与售后风险。",
            "new_product_days": 30,
            "rules": [
                {"name": "老品毛利率偏低", "metric": "gross_margin", "operator": "lt", "threshold": 0.3, "level": "warning", "suggestion": "核对成本、折扣和投放结构，优先优化低毛利高销量商品。"},
                {"name": "老品退款率过高", "metric": "refund_rate", "operator": "gt", "threshold": 0.2, "level": "critical", "suggestion": "检查退款原因、描述一致性和质量问题，建立售后整改计划。"},
            ],
        },
    ]
    for item in templates:
        rules = item.pop("rules")
        strategy, created = OperationStrategy.objects.get_or_create(name=item["name"], defaults=item)
        if created:
            StrategyRule.objects.bulk_create([StrategyRule(strategy=strategy, enabled=True, **rule) for rule in rules])


def remove_templates(apps, schema_editor):
    OperationStrategy = apps.get_model("warehouse", "OperationStrategy")
    OperationStrategy.objects.filter(name__in=["新品上架 30 天预警", "老品利润与退款预警"]).delete()


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0007_operationstrategy_strategyrule_strategyalert_and_more")]
    operations = [migrations.RunPython(seed_templates, remove_templates)]

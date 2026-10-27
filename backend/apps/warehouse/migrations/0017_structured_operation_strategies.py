from django.db import migrations, models
import django.db.models.deletion


def seed_structured_templates(apps, schema_editor):
    OperationStrategy = apps.get_model("warehouse", "OperationStrategy")
    StrategyRule = apps.get_model("warehouse", "StrategyRule")

    new_description = (
        "新品定义：创建日为第1天，第36天起为老品。第35天按累计销量分级："
        "A≥500、B=100-499、C=1-99、D=0。第1周只做内功；第2-5周按日销量和完整周累计销量评估。"
        "内功：评价、买家秀、问大家、短视频、标题/主图/详情页优化；付费：测图、拉升。"
    )
    old_description = (
        "老品定义：创建日大于35天（第36天起）。按最近30天累计销量分级："
        "A≥1000、B=500-999、C=100-499、D=1-99、E=0。"
        "转化率≥3%为上等马（拉升计划），2%-3%为中等马、<2%为下等马（优化计划）。"
        "内功覆盖标题、点击主图、转化主图、详情页、评价、问大家、SKU；付费覆盖拉新-蓄水-收割-测图。"
    )
    new, _ = OperationStrategy.objects.update_or_create(
        name="新品35天分级运营策略",
        defaults={"strategy_type": "new_product", "strategy_code": "new_product_35d", "description": new_description, "new_product_days": 35, "enabled": True, "schedule_enabled": True},
    )
    old, _ = OperationStrategy.objects.update_or_create(
        name="老品近30天分级运营策略",
        defaults={"strategy_type": "mature_product", "strategy_code": "mature_product_30d", "description": old_description, "new_product_days": 35, "enabled": True, "schedule_enabled": True},
    )
    StrategyRule.objects.filter(strategy__in=[new, old]).delete()
    week_thresholds = {
        "week2": {"A": (4, 28), "B": (3, 21), "C": (1, 7), "D": (0, 0)},
        "week3": {"A": (5, 35), "B": (4, 28), "C": (1, 7), "D": (0, 0)},
        "week4": {"A": (8, 56), "B": (5, 35), "C": (1, 7), "D": (0, 0)},
        "week5": {"A": (10, 70), "B": (8, 40), "C": (1, 7), "D": (0, 0)},
    }
    new_rules = []
    for stage, grades in week_thresholds.items():
        for grade, (daily, weekly) in grades.items():
            new_rules.append(StrategyRule(
                strategy=new, name=f"新品{stage}{grade}类销量评估", metric="daily_sales_volume",
                operator="lt", threshold=daily, weekly_threshold=weekly, stage=stage,
                product_grade=grade, level="warning" if grade != "D" else "critical", enabled=True,
                message_template="{product} 新品阶段销量未达标", suggestion=(
                    "A/B类重点关注，执行评价、买家秀、问大家，付费测图与拉升。" if grade in ("A", "B") else
                    "C类优化标题、主图点击率、详情页、评价、买家秀、问大家和详情短视频，付费测图。" if grade == "C" else
                    "D类滞销，检查链接和素材，暂停无效投放并制定破零计划。"
                ),
            ))
    for grade, lower, upper in (("A", 500, None), ("B", 100, 499), ("C", 1, 99), ("D", 0, 0)):
        new_rules.append(StrategyRule(
            strategy=new, name=f"新品35天最终{grade}类", metric="cumulative_35d_sales",
            operator="eq", threshold=lower, threshold_max=upper, stage="final35", product_grade=grade,
            level="info", enabled=True, message_template="{product} 新品35天评级完成",
            suggestion="根据新品35天累计销量确认等级，并将A/B类纳入拉升、C类纳入优化、D类纳入滞销处理。",
        ))
    StrategyRule.objects.bulk_create(new_rules)

    action = "内功：标题、点击主图、转化主图、详情页、评价、问大家、SKU优化；付费：拉新-蓄水-收割-测图，平补/递增，单/多计划和单/多工具。"
    old_rules = []
    grades = (("A", "超级爆款"), ("B", "潜力爆款"), ("C", "潜力小爆款"), ("D", "动销款"), ("E", "滞销款"))
    bands = (("high", "上等马", 0.03, "拉升计划"), ("middle", "中等马", 0.02, "优化计划"), ("low", "下等马", 0, "优化计划"))
    for grade, label in grades:
        for band, horse, threshold, direction in bands:
            old_rules.append(StrategyRule(
                strategy=old, name=f"老品{grade}类{horse}策略", metric="conversion_rate",
                operator="gte" if band != "low" else "lt", threshold=threshold, stage="old30",
                product_grade=grade, conversion_band=band, level="warning" if band != "low" else "critical", enabled=True,
                message_template=f"{{product}} 老品{grade}类{horse}", suggestion=f"{direction}：{action}",
            ))
    StrategyRule.objects.bulk_create(old_rules)


def remove_structured_templates(apps, schema_editor):
    OperationStrategy = apps.get_model("warehouse", "OperationStrategy")
    OperationStrategy.objects.filter(name__in=["新品35天分级运营策略", "老品近30天分级运营策略"]).delete()


class Migration(migrations.Migration):
    dependencies = [("warehouse", "0016_product_catalog")]
    operations = [
        migrations.AddField(
            model_name="operationstrategy", name="strategy_code",
            field=models.CharField(choices=[("standard", "通用规则"), ("new_product_35d", "新品 35 天分级策略"), ("mature_product_30d", "老品近 30 天分级策略")], default="standard", max_length=32),
        ),
        migrations.AlterField(
            model_name="strategyrule", name="metric",
            field=models.CharField(choices=[("sales", "成交金额"), ("orders", "订单数"), ("refund_amount", "退款金额"), ("refund_rate", "退款率"), ("ad_cost", "广告花费"), ("roi", "广告 ROI"), ("gross_profit", "毛利润"), ("gross_margin", "毛利率"), ("net_profit", "净利润"), ("net_margin", "净利率"), ("product_age_days", "商品上架天数"), ("conversion_rate", "转化率"), ("cumulative_35d_sales", "新品 35 天累计销量"), ("daily_sales_volume", "日销量"), ("weekly_sales_volume", "周销量"), ("recent_30d_sales", "近 30 天销量")], max_length=32),
        ),
        migrations.AddField(model_name="strategyrule", name="weekly_threshold", field=models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
        migrations.AddField(model_name="strategyrule", name="stage", field=models.CharField(blank=True, default="", max_length=16)),
        migrations.AddField(model_name="strategyrule", name="product_grade", field=models.CharField(blank=True, default="", max_length=2)),
        migrations.AddField(model_name="strategyrule", name="conversion_band", field=models.CharField(blank=True, default="", max_length=16)),
        migrations.AlterField(model_name="strategyalert", name="product_fact", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="strategy_alerts", to="warehouse.monthlyproductfact")),
        migrations.AddField(model_name="strategyalert", name="product_catalog", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="strategy_alerts", to="warehouse.productcatalog")),
        migrations.AddField(model_name="strategyalert", name="evaluation_date", field=models.DateField(blank=True, db_index=True, null=True)),
        migrations.AddConstraint(model_name="strategyalert", constraint=models.UniqueConstraint(fields=("strategy", "rule", "product_catalog", "evaluation_date"), name="uniq_strategy_alert_catalog_day")),
        migrations.RunPython(seed_structured_templates, remove_structured_templates),
    ]

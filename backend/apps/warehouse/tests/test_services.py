from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from apps.warehouse.models import AIAnalysisRun, AbnormalRecord, ProductData
from apps.warehouse.services.ai import run_analysis
from apps.warehouse.services.anomalies import detect_anomalies
from apps.warehouse.services.dashboard import dashboard_summary, monthly_dashboard, monthly_product_ranking
from apps.warehouse.services.health import calculate_health


@pytest.mark.django_db
def test_health_score_rewards_growth_and_margin():
    previous = ProductData.objects.create(
        date="2026-08-01", shop="旗舰店", product_id="A", sales=1000, visitors=1000,
        conversion_rate=Decimal("0.02"), profit=200,
    )
    current = ProductData.objects.create(
        date="2026-08-02", shop="旗舰店", product_id="A", sales=1300, visitors=1200,
        conversion_rate=Decimal("0.021"), profit=390,
    )
    result = calculate_health(current, previous)
    assert result["score"] >= 80
    assert result["components"]["profit_health"] == 100


@pytest.mark.django_db
def test_detects_sales_drop():
    ProductData.objects.create(date="2026-08-01", shop="旗舰店", product_id="A", product_name="商品A", sales=1000, visitors=1000, conversion_rate=Decimal("0.02"))
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="A", product_name="商品A", sales=600, visitors=1000, conversion_rate=Decimal("0.02"))
    detected = detect_anomalies(date(2026, 8, 2), "旗舰店")
    assert len(detected) == 1
    record = AbnormalRecord.objects.get()
    assert record.type == AbnormalRecord.Type.SALES
    assert record.level == AbnormalRecord.Level.CRITICAL


@pytest.mark.django_db
def test_dashboard_aggregates_product_metrics():
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="A", sales=1000, sales_volume=3, orders=2, visitors=100, ad_cost=100, ad_revenue=300)
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="B", sales=500, sales_volume=2, orders=1, visitors=50, ad_cost=50, ad_revenue=100)
    result = dashboard_summary(date(2026, 8, 2), "旗舰店")
    assert result["metrics"]["sales"]["value"] == Decimal("1500")
    assert result["metrics"]["visitors"]["value"] == 150
    assert result["metrics"]["roi"]["value"] == Decimal("400") / Decimal("150")


@pytest.mark.django_db
def test_ai_analysis_context_is_json_serializable():
    user = User.objects.create_user("analyst")
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="A", sales=1000, visitors=100)
    run = run_analysis(user, day=date(2026, 8, 2), shop="旗舰店", question="分析问题")
    assert AIAnalysisRun.objects.count() == 1
    assert run.input_context["scope"]["date"] == "2026-08-02"
    assert "problems" in run.output


@pytest.mark.django_db
def test_monthly_dashboard_and_product_ranking():
    ProductData.objects.create(date="2026-07-01", shop="旗舰店", product_id="A", product_name="商品A", sales=300, visitors=30, orders=1)
    ProductData.objects.create(date="2026-07-02", shop="旗舰店", product_id="A", product_name="商品A", sales=200, visitors=20, orders=1)
    ProductData.objects.create(date="2026-08-01", shop="旗舰店", product_id="A", product_name="商品A", sales=600, visitors=60, orders=3)
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="A", product_name="商品A", sales=400, visitors=40, orders=2)
    result = monthly_dashboard("2026-08", "旗舰店")
    assert result["metrics"]["sales"]["value"] == Decimal("1000")
    assert result["metrics"]["sales"]["change_rate"] == Decimal("1")
    assert result["is_partial"] is True
    assert result["comparison_label"] == "2026-07 同期"
    assert result["available_months"] == ["2026-08", "2026-07"]
    ranking = monthly_product_ranking("2026-08", "旗舰店")
    assert len(ranking) == 1
    assert ranking[0]["sales"] == Decimal("1000")
    assert ranking[0]["month"] == "2026-08"


@pytest.mark.django_db
def test_monthly_dashboard_uses_product_fallback_when_shop_summary_has_gaps():
    ProductData.objects.create(
        date="2026-08-01", shop="旗舰店", product_id="__SHOP_TOTAL__", product_name="店铺汇总",
        record_type=ProductData.RecordType.SHOP_SUMMARY, sales=1000, visitors=100, orders=5,
    )
    ProductData.objects.create(date="2026-08-01", shop="旗舰店", product_id="A", sales=600, visitors=60, orders=3)
    ProductData.objects.create(date="2026-08-01", shop="旗舰店", product_id="B", sales=400, visitors=40, orders=2)
    ProductData.objects.create(date="2026-08-02", shop="旗舰店", product_id="A", sales=700, visitors=70, orders=4)
    result = monthly_dashboard("2026-08", "旗舰店")
    assert result["metrics"]["sales"]["value"] == Decimal("1700")
    assert result["metrics"]["visitors"]["value"] == 170

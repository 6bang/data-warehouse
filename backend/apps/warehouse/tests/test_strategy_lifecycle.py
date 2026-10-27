"""Independent acceptance tests for 35-day / rolling-30-day strategy rules."""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.warehouse.models import OperationStrategy, ProductCatalog, ProductData, StrategyAlert, StrategyRule
from apps.warehouse.services import strategies as service


@pytest.mark.parametrize("sales,expected", [(0, "D"), (1, "C"), (99, "C"), (100, "B"), (499, "B"), (500, "A")])
def test_new_product_final_grade_boundaries(sales, expected):
    assert service._grade_new(sales) == expected


@pytest.mark.parametrize("sales,expected", [(0, "E"), (1, "D"), (99, "D"), (100, "C"), (499, "C"), (500, "B"), (999, "B"), (1000, "A")])
def test_mature_product_rolling_grade_boundaries(sales, expected):
    assert service._grade_mature(sales) == expected


@pytest.mark.parametrize("rate,expected", [("0", "low"), ("0.019999", "low"), ("0.02", "middle"), ("0.029999", "middle"), ("0.03", "high")])
def test_conversion_band_boundaries(rate, expected):
    assert service._conversion_band(Decimal(rate)) == expected


def catalog(product_id, created):
    return ProductCatalog.objects.create(
        organization="验收组织", platform="淘宝", shop="验收店", product_id=product_id,
        product_name=f"验收商品{product_id}",
        product_created_at=datetime.combine(created, datetime.min.time(), dt_timezone.utc),
    )


def daily_rows(product, start, days, *, volume=0, orders=0, visitors=100):
    return ProductData.objects.bulk_create([
        ProductData(date=start + timedelta(days=index), shop=product.shop, product_id=product.product_id,
                    sales_volume=volume, orders=orders, visitors=visitors)
        for index in range(days)
    ])


def strategy(code):
    return OperationStrategy.objects.create(
        name="独立验收策略", strategy_code=code, new_product_days=35,
        strategy_type="new_product" if code == "new_product_35d" else "mature_product",
        organization="验收组织", shop="验收店",
    )


@pytest.mark.django_db
def test_creation_day_is_day_one_and_day_36_is_mature():
    as_of = date(2026, 8, 31)
    first = catalog("day1", as_of)
    last = catalog("day35", as_of - timedelta(days=34))
    old = catalog("day36", as_of - timedelta(days=35))
    new_scope = service._structured_catalogs(strategy("new_product_35d"), as_of)
    old_scope = service._structured_catalogs(strategy("mature_product_30d"), as_of)
    assert {item.pk for item in new_scope} == {first.pk, last.pk}
    assert {item.pk for item in old_scope} == {old.pk}


def test_week5_b_threshold_preserves_business_table():
    assert service.NEW_WEEK_THRESHOLDS["week5"]["B"] == (8, 40)


def test_conversion_is_weighted_and_no_visits_is_unknown():
    rows = [ProductData(orders=1, visitors=10), ProductData(orders=1, visitors=90)]
    assert service._conversion_rate(rows) == Decimal("0.02")
    assert service._conversion_rate([ProductData(orders=0, visitors=0)]) is None


@pytest.mark.django_db
def test_missing_daily_records_are_not_zero_sales():
    item = catalog("missing", date(2026, 7, 1))
    # One real zero observation does not prove 30 days of zero sales.
    daily_rows(item, date(2026, 8, 31), 1)
    policy = strategy("mature_product_30d")
    StrategyRule.objects.create(strategy=policy, name="零销量", metric="recent_30d_sales",
                                operator="eq", threshold=0, stage="old30", product_grade="E")
    result = service.run_strategy(policy, "2026-08")
    assert result["alerts"] == 0
    assert StrategyAlert.objects.filter(strategy=policy).count() == 0
    # The important invariant is that an incomplete window produces no zero-sales
    # alert. Implementations may expose skip counts in the summary, but do not
    # need to use a particular summary key to preserve the data-semantics rule.


@pytest.mark.django_db
def test_complete_mature_window_is_idempotent():
    item = catalog("complete", date(2026, 7, 1))
    daily_rows(item, date(2026, 8, 2), 30, volume=1, orders=3)
    policy = strategy("mature_product_30d")
    StrategyRule.objects.create(strategy=policy, name="D类上等马", metric="recent_30d_sales",
                                operator="gte", threshold=1, stage="old30", product_grade="D",
                                conversion_band="high", suggestion="拉升计划")
    first = service.run_strategy(policy, "2026-08")
    second = service.run_strategy(policy, "2026-08")
    assert first["alerts"] == second["alerts"] == 1
    assert StrategyAlert.objects.filter(strategy=policy).count() == 1
    alert = StrategyAlert.objects.get(strategy=policy)
    assert alert.threshold_snapshot["recent_30d_sales"] == 30
    assert Decimal(alert.threshold_snapshot["conversion_rate"]) == Decimal("0.03")


@pytest.mark.django_db
def test_lifecycle_rule_fields_round_trip_through_api():
    user = User.objects.create_user("strategy-lifecycle-reviewer", password="test-only-password")
    client = APIClient()
    client.force_authenticate(user)
    payload = {
        "name": "35天验收", "strategy_type": "new_product", "strategy_code": "new_product_35d",
        "new_product_days": 35, "report_mode": "system", "enabled": True,
        "rules": [{"name": "第5周B类", "metric": "daily_sales_volume", "operator": "lt", "threshold": "8",
                   "weekly_threshold": "40", "stage": "week5", "product_grade": "B", "conversion_band": "",
                   "level": "warning", "suggestion": "测图、拉升", "enabled": True}],
    }
    created = client.post("/api/v1/operation-strategies/", payload, format="json")
    assert created.status_code == 201, created.data
    detail = client.get(f"/api/v1/operation-strategies/{created.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["strategy_code"] == "new_product_35d"
    rule = detail.data["rules"][0]
    assert (rule["stage"], rule["product_grade"], rule["conversion_band"]) == ("week5", "B", "")
    assert Decimal(rule["threshold"]) == 8
    assert Decimal(rule["weekly_threshold"]) == 40

from datetime import datetime, timezone as dt_timezone

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.warehouse.models import MonthlyProductFact, OperationPlan, OperationStrategy, StrategyAlert, StrategyRule
from apps.warehouse.services.strategies import run_strategy


@pytest.fixture
def monthly_product():
    return MonthlyProductFact.objects.create(
        organization="测试组织", month="2026-08", platform="淘宝", shop="测试店",
        category_path="家居收纳->收纳盒", product_id="10001", product_name="新品收纳盒",
        product_created_at=datetime(2026, 8, 5, tzinfo=dt_timezone.utc), sales=100, orders=1,
        refund_amount=0, ad_cost=20, ad_revenue=10, gross_profit=30, net_profit=10, net_sales=100,
    )


@pytest.mark.django_db
def test_strategy_rule_run_is_idempotent(monthly_product):
    strategy = OperationStrategy.objects.create(name="新品破零预警", strategy_type="new_product", organization="测试组织")
    StrategyRule.objects.create(
        strategy=strategy, name="新品销售不足", metric="sales", operator="lt", threshold=500,
        level="critical", suggestion="检查主图和首轮投放",
    )
    first = run_strategy(strategy, "2026-08")
    second = run_strategy(strategy, "2026-08")
    assert first["alerts"] == second["alerts"] == 1
    assert StrategyAlert.objects.count() == 1
    alert = StrategyAlert.objects.get()
    assert alert.product_url == "https://item.taobao.com/item.htm?id=10001"
    assert "系统规则播报" in alert.reporter_name


@pytest.mark.django_db
def test_strategy_api_creates_rule_and_converts_alert_to_plan(monthly_product):
    user = User.objects.create_user("strategy-owner", password="secret-pass")
    client = APIClient()
    client.force_authenticate(user)
    response = client.post("/api/v1/operation-strategies/", {
        "name": "新品成交预警", "strategy_type": "new_product", "organization": "测试组织",
        "new_product_days": 30, "report_mode": "system", "enabled": True,
        "schedule_enabled": True, "schedule_hour": 7,
        "rules": [{
            "name": "成交不足", "metric": "sales", "operator": "lt", "threshold": "500",
            "level": "warning", "suggestion": "优化首图与关键词", "enabled": True,
        }],
    }, format="json")
    assert response.status_code == 201
    strategy_id = response.data["id"]

    response = client.post(f"/api/v1/operation-strategies/{strategy_id}/run/", {"month": "2026-08"}, format="json")
    assert response.status_code == 200
    assert response.data["alerts"] == 1

    alert = StrategyAlert.objects.get()
    response = client.post(f"/api/v1/strategy-alerts/{alert.id}/convert_plan/", {"owner_id": user.id}, format="json")
    assert response.status_code == 201
    assert OperationPlan.objects.filter(alert=alert, owner=user).exists()
    alert.refresh_from_db()
    assert alert.status == StrategyAlert.Status.CONVERTED

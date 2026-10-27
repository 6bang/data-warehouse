from unittest.mock import patch
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.warehouse.models import MCPServerConfig
from apps.warehouse.services.secrets import encrypt_secret
from apps.warehouse.services.realtime import _hourly_trend


@pytest.fixture
def realtime_config():
    cache.clear()
    return MCPServerConfig.objects.create(
        name="测试数据洞察",
        endpoint_url="https://source.example.invalid/open/v1/data-insight/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        organization_name="测试组织",
    )


def test_hourly_trend_reports_unavailable_without_any_outbound_call():
    # conftest forbids unmocked sockets/urlopen, so any hidden login or fetch would fail here.
    trend = _hourly_trend(date(2026, 8, 12), [{"store_id": "S1", "store_name": "测试店"}])
    assert trend["available"] is False
    assert trend["hours"] == list(range(24))
    assert trend["current"] == [] and trend["previous"] == []
    assert "不可用" in trend["warning"]


@pytest.mark.django_db
def test_realtime_dashboard_combines_compare_trend_and_rankings(realtime_config):
    user = User.objects.create_user("realtime-viewer", password="secret-pass")
    client = APIClient()
    client.force_authenticate(user)
    compare = {
        "metrics": {
            "paid_amount": {"current": 3458.8, "compare": 9089.8, "change_rate": -0.6195},
            "net_profit": {"current": 837.59, "compare": 2990.16, "change_rate": -0.7199},
        }
    }
    ranking = {"items": [{
        "store_id": "S1", "store_name": "测试店", "platform_type": "taobao",
        "paid_amount": 3458.8, "trade_count": 10, "ad_cost": 46.21, "net_profit": 837.59,
    }]}
    report = {
        "shop_summary": {"items": [{"store_id": "S1", "store_name": "测试店", "paid_amount": 3458.8}]},
        "top_items": {"items": [{"rank": 1, "item_id": "P1", "title": "商品A", "paid_amount": 814}]},
        "top_taobao_campaigns": {"items": [{"rank": 1, "campaign_id": "C1", "campaign_name": "计划A", "cost": 46.21}]},
    }

    def fake_call(_client, tool_name, _arguments=None):
        return {"data_insight_compare": compare, "data_insight_query": ranking, "data_insight_daily_report": report}[tool_name]

    with patch("apps.warehouse.services.realtime.list_stores", return_value=[{
        "store_id": "S1", "store_name": "测试店", "platform_type": "taobao", "platform_name": "淘宝",
    }]), patch("apps.warehouse.services.realtime.MCPHttpClient.call_tool_json", new=fake_call), patch(
        "apps.warehouse.services.realtime._hourly_trend",
        return_value={"available": True, "hours": list(range(24)), "previous": [0] * 24, "current": [], "warning": ""},
    ):
        response = client.get("/api/v1/dashboard/realtime/?refresh=1")

    assert response.status_code == 200
    assert response.data["metrics"]["paid_amount"]["current"] == 3458.8
    assert response.data["metrics"]["paid_amount"]["label"] == "成交金额"
    assert response.data["hourly_trend"]["available"] is True
    assert response.data["rankings"]["item"][0]["item_id"] == "P1"
    assert response.data["rankings"]["shop"][0]["ad_cost"] == 46.21
    assert response.data["available_shops"][0]["store_name"] == "测试店"
    assert "测试数据洞察" not in str(response.data)


@pytest.mark.django_db
def test_realtime_dashboard_does_not_leak_when_user_has_no_assigned_shops(realtime_config):
    from apps.warehouse.models import AccessRole, AccountProfile

    role = AccessRole.objects.create(
        name="空范围查看者",
        code="empty-scope",
        data_scope=AccessRole.DataScope.ASSIGNED,
        permissions=["dashboard.view"],
    )
    user = User.objects.create_user("empty-scope-user", password="secret-pass")
    AccountProfile.objects.create(user=user, access_role=role, allowed_shops=[])
    client = APIClient()
    client.force_authenticate(user)

    with patch("apps.warehouse.services.realtime.list_stores", return_value=[{
        "store_id": "S1", "store_name": "未授权店", "platform_type": "taobao", "platform_name": "淘宝",
    }]), patch("apps.warehouse.services.realtime.MCPHttpClient.call_tool_json") as remote_call:
        response = client.get("/api/v1/dashboard/realtime/")

    assert response.status_code == 200
    assert response.data["metrics"]["paid_amount"]["current"] is None
    assert response.data["available_shops"] == []
    remote_call.assert_not_called()

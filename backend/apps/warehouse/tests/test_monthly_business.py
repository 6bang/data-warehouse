from io import StringIO
from pathlib import Path
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

import pandas as pd
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.warehouse.models import DataSyncJob, MCPServerConfig, MonthlyProductFact, ProductCatalog
from apps.warehouse.services.monthly_export import import_monthly_product_export
from apps.warehouse.services.mcp_sync import SyncAlreadyRunning, next_scheduled_at, sync_month as sync_mcp_month
from apps.warehouse.services.secrets import encrypt_secret


@pytest.fixture
def monthly_export(tmp_path):
    path = Path(tmp_path) / "商品数据.xlsx"
    pd.DataFrame([
        {
            "商品ID": "10001", "平台类型": "淘宝", "店铺ID": "测试店", "商品标题": "示例收纳盒",
            "全类目名称": "家居收纳->收纳盒", "运营ID": "--", "成交金额": 1000, "成交笔数": 10,
            "毛销售额": 1000, "净销售额": 800, "总退款金额": 200, "广告花费": 100,
            "广告交易额": 400, "毛利润": 500, "净利润": 300,
        },
        {
            "商品ID": "10002", "平台类型": "淘宝", "店铺ID": "测试店", "商品标题": "示例整理袋",
            "全类目名称": "家居收纳->整理袋", "运营ID": "张三", "成交金额": 500, "成交笔数": 5,
            "毛销售额": 500, "净销售额": 450, "总退款金额": 50, "广告花费": 0,
            "广告交易额": 0, "毛利润": 250, "净利润": 180,
        },
    ]).to_excel(path, index=False)
    return path


@pytest.mark.django_db
def test_import_monthly_export_is_idempotent(monthly_export):
    first = import_monthly_product_export(monthly_export, "测试组织", "2026-08")
    second = import_monthly_product_export(monthly_export, "测试组织", "2026-08")
    assert first.status == DataSyncJob.Status.SUCCEEDED
    assert second.status == DataSyncJob.Status.SUCCEEDED
    assert MonthlyProductFact.objects.count() == 2
    assert second.summary["sales"] == 1500
    assert MonthlyProductFact.objects.get(product_id="10001").operator_name == "未分配运营"


@pytest.mark.django_db
def test_import_command_records_neutral_source_names(monthly_export):
    output = StringIO()
    call_command("import_monthly_export", file=str(monthly_export), organization="测试组织", month="2026-08", stdout=output)
    assert "rows=2/2" in output.getvalue()
    assert list(DataSyncJob.objects.values_list("source_system", flat=True)) == ["excel"]
    assert set(MonthlyProductFact.objects.values_list("source", flat=True)) == {"excel_export"}
    assert set(ProductCatalog.objects.values_list("source", flat=True)) == {"excel_export"}
    assert MonthlyProductFact._meta.get_field("source").default == "excel_export"


@pytest.mark.django_db
def test_monthly_business_dimensions_and_mcp(monthly_export):
    import_monthly_product_export(monthly_export, "测试组织", "2026-08")
    user = User.objects.create_user("business-viewer", password="secret-pass")
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/v1/business/dimensions/?organization=测试组织&month=2026-08")
    assert response.status_code == 200
    assert response.data["platforms"] == ["淘宝"]
    assert set(response.data["operators"]) == {"未分配运营", "张三"}

    response = client.get("/api/v1/business/monthly/?organization=测试组织&month=2026-08&group_by=operator")
    assert response.status_code == 200
    assert response.data["summary"]["sales"] == 1500
    assert response.data["summary"]["roi"] == 4
    assert len(response.data["results"]) == 2

    response = client.post("/api/v1/mcp/business/", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, format="json")
    assert response.status_code == 200
    assert {tool["name"] for tool in response.data["result"]["tools"]} == {
        "list_business_dimensions", "query_monthly_metrics", "query_realtime_metrics",
    }


@pytest.mark.django_db
def test_mcp_sync_is_idempotent_and_keeps_extended_metrics():
    config = MCPServerConfig.objects.create(
        name="测试数据洞察",
        endpoint_url="https://source.example.invalid/open/v1/data-insight/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        organization_name="测试组织",
    )
    payload = {
        "items": [{
            "platform_type": "taobao", "store_id": "S1", "store_name": "测试店", "item_id": "1001",
            "title": "商品A", "outer_id": "A01", "cat_full_name": "收纳->收纳盒", "op_manager_name": "张三",
            "stock": 88, "gross_goods_cost": 400, "gross_sales": 1000, "paid_amount": 1000,
            "paid_units": 12, "net_sales": 800, "trade_count": 10, "total_success_refund_amt": 200,
            "ad_cost": 100, "ad_trade_amt": 400, "gross_profit": 600, "net_profit": 300,
            "item_uv": 250, "item_pay_cvr": 0.04,
        }],
        "page": 1,
        "has_next": False,
    }
    with patch("apps.warehouse.services.mcp_sync.MCPHttpClient.call_tool_json", return_value=payload):
        first = sync_mcp_month(config, "2026-08")
        second = sync_mcp_month(config, "2026-08")

    assert first.status == DataSyncJob.Status.SUCCEEDED
    assert second.summary["products"] == 1
    assert MonthlyProductFact.objects.filter(organization="测试组织", month="2026-08").count() == 1
    fact = MonthlyProductFact.objects.get(product_id="1001")
    assert fact.source == "mcp_sync"
    assert fact.sales_volume == 12
    assert fact.visitors == 250
    assert fact.stock == 88
    assert fact.conversion_rate == Decimal("0.04")


@pytest.mark.django_db
def test_mcp_data_sync_api_lists_sources_and_syncs_through_neutral_path():
    config = MCPServerConfig.objects.create(
        name="测试数据接口",
        endpoint_url="https://source.example.invalid/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        organization_name="测试组织",
    )
    admin = User.objects.create_superuser("sync-admin", password="secret-pass")
    client = APIClient()
    client.force_authenticate(admin)

    listing = client.get("/api/v1/data-sync/mcp/")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.data["sources"]] == [config.id]

    payload = {
        "items": [{
            "platform_type": "taobao", "store_id": "S1", "store_name": "测试店", "item_id": "2001",
            "title": "示例收纳盒", "paid_amount": 300, "paid_units": 3, "trade_count": 3,
        }],
        "page": 1,
        "has_next": False,
    }
    with patch("apps.warehouse.services.mcp_sync.MCPHttpClient.call_tool_json", return_value=payload):
        response = client.post("/api/v1/data-sync/mcp/", {"source_id": config.id, "month": "2026-08"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["summary"]["products"] == 1
    assert list(DataSyncJob.objects.values_list("source_system", flat=True)) == ["mcp_sync"]
    assert set(MonthlyProductFact.objects.values_list("source", flat=True)) == {"mcp_sync"}

    dimensions = client.get("/api/v1/business/dimensions/?organization=测试组织&month=2026-08")
    assert dimensions.status_code == 200
    assert "visitors" in dimensions.data["coverage"]["available"]


@pytest.mark.django_db
def test_mcp_sync_lock_prevents_overlapping_runs():
    config = MCPServerConfig.objects.create(
        name="测试同步锁",
        endpoint_url="https://source.example.invalid/open/v1/data-insight/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        organization_name="测试组织",
        sync_in_progress=True,
        sync_started_at=timezone.now(),
    )
    with pytest.raises(SyncAlreadyRunning):
        sync_mcp_month(config, "2026-08")
    assert DataSyncJob.objects.filter(source_system="mcp_sync").count() == 0


@pytest.mark.django_db
def test_mcp_failure_uses_short_retry_then_returns_to_interval():
    now = timezone.now()
    config = MCPServerConfig.objects.create(
        name="测试调度连接",
        endpoint_url="https://source.example.invalid/open/v1/data-insight/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        schedule_enabled=True,
        schedule_interval_minutes=120,
        organization_name="测试组织",
        last_synced_at=now,
    )
    assert next_scheduled_at(config) == now + timedelta(minutes=120)
    config.last_sync_attempted_at = now
    config.consecutive_sync_failures = 2
    assert next_scheduled_at(config) == now + timedelta(minutes=10)


@pytest.mark.django_db
def test_mcp_schedule_command_runs_due_source():
    config = MCPServerConfig.objects.create(
        name="测试自动同步",
        endpoint_url="https://source.example.invalid/open/v1/data-insight/mcp",
        auth_type=MCPServerConfig.AuthType.BEARER,
        auth_token_encrypted=encrypt_secret("test-token"),
        enabled=True,
        data_sync_enabled=True,
        schedule_enabled=True,
        schedule_interval_minutes=120,
        organization_name="测试组织",
    )
    fake_job = type("Job", (), {"success_rows": 70})()
    with patch("apps.warehouse.management.commands.sync_mcp_data.sync_month", return_value=fake_job) as runner:
        call_command("sync_mcp_data")
    runner.assert_called_once_with(config, timezone.localtime().strftime("%Y-%m"))

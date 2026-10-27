import calendar
import hashlib
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.warehouse.models import ConnectionStatus, DataSyncJob, MCPServerConfig, MonthlyProductFact
from apps.warehouse.services.integrations import record_integration_event
from apps.warehouse.services.mcp import MCPHttpClient
from apps.warehouse.services.product_catalog import sync_catalog_from_facts
from apps.warehouse.services.product_images import enrich_product_images


# Compatibility adapter: endpoints are always supplied by the administrator.
STORE_TOOL = "data_insight_list_stores"
QUERY_TOOL = "data_insight_query"
PLATFORM_NAMES = {
    "taobao": "淘宝", "tmall": "天猫", "jd": "京东", "pdd": "拼多多",
    "douyin": "抖音", "kuaishou": "快手", "1688": "1688",
}
SYNC_FIELDS = [
    "platform_type", "store_id", "store_name", "item_id", "title", "outer_id", "pic_url",
    "cat_full_name", "created", "op_manager_name", "stock", "gross_goods_cost", "gross_sales",
    "paid_amount", "paid_units", "net_sales", "trade_count", "total_success_refund_amt", "ad_cost",
    "ad_trade_amt", "gross_profit", "net_profit", "item_uv", "item_pay_cvr",
]
# The server-side poller runs every five minutes.  Five minutes is also a
# supported source sync interval so a configured source can be fetched on
# every poll (without relying on an open browser session).
ALLOWED_SYNC_INTERVALS = {5, 30, 60, 120, 360, 1440}
SYNC_LOCK_TIMEOUT_MINUTES = 45


class SyncAlreadyRunning(ValueError):
    pass


def next_scheduled_at(config):
    if not config.schedule_enabled or not config.data_sync_enabled or not config.enabled:
        return None
    interval = config.schedule_interval_minutes if config.schedule_interval_minutes in ALLOWED_SYNC_INTERVALS else 120
    if config.consecutive_sync_failures and config.last_sync_attempted_at:
        retry_minutes = min(5 * (2 ** max(config.consecutive_sync_failures - 1, 0)), 60)
        return config.last_sync_attempted_at + timedelta(minutes=retry_minutes)
    baseline = config.last_synced_at or config.last_sync_attempted_at
    return baseline + timedelta(minutes=interval) if baseline else timezone.now()


def is_sync_due(config, now=None):
    if not config.last_synced_at and not config.last_sync_attempted_at:
        return bool(config.schedule_enabled and config.data_sync_enabled and config.enabled)
    due_at = next_scheduled_at(config)
    return bool(due_at and due_at <= (now or timezone.now()))


def _acquire_sync_lock(config):
    now = timezone.now()
    stale_before = now - timedelta(minutes=SYNC_LOCK_TIMEOUT_MINUTES)
    with transaction.atomic():
        locked = MCPServerConfig.objects.select_for_update().get(pk=config.pk)
        if locked.sync_in_progress and locked.sync_started_at and locked.sync_started_at > stale_before:
            raise SyncAlreadyRunning("该数据源正在同步，请稍后再试")
        locked.sync_in_progress = True
        locked.sync_started_at = now
        locked.last_sync_attempted_at = now
        locked.save(update_fields=["sync_in_progress", "sync_started_at", "last_sync_attempted_at", "updated_at"])


def _release_sync_lock(config):
    MCPServerConfig.objects.filter(pk=config.pk).update(sync_in_progress=False, sync_started_at=None)


def _text(value, fallback=""):
    result = "" if value is None else str(value).strip()
    return result or fallback


def _decimal(value):
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _integer(value):
    number = _decimal(value)
    return max(int(number or 0), 0)


def _datetime(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return timezone.make_aware(result, timezone.get_current_timezone()) if timezone.is_naive(result) else result


def _validate_config(config):
    if not config.enabled or not config.data_sync_enabled:
        raise ValueError("该 MCP 数据源尚未启用一键同步")
    if not config.endpoint_url:
        raise ValueError("请先配置兼容经营数据工具协议的 MCP 地址")
    if config.auth_type != MCPServerConfig.AuthType.BEARER or not config.auth_token_encrypted:
        raise ValueError("经营数据接口必须配置 Bearer Token")


def list_stores(config):
    _validate_config(config)
    payload = MCPHttpClient(config).call_tool_json(STORE_TOOL)
    stores = payload.get("stores", [])
    return [
        {
            "store_id": _text(item.get("store_id")),
            "store_name": _text(item.get("store_name"), "未命名店铺"),
            "platform_type": _text(item.get("platform_type"), "unknown"),
            "platform_name": PLATFORM_NAMES.get(_text(item.get("platform_type")), _text(item.get("platform_type"), "未知平台")),
        }
        for item in stores
        if item.get("store_id")
    ]


def _month_dates(month):
    try:
        year, month_number = (int(part) for part in month.split("-"))
        last_day = calendar.monthrange(year, month_number)[1]
    except (TypeError, ValueError):
        raise ValueError("month 必须使用 YYYY-MM 格式")
    return f"{year:04d}-{month_number:02d}-01", f"{year:04d}-{month_number:02d}-{last_day:02d}"


def _query_rows(config, month, store_ids):
    date_from, date_to = _month_dates(month)
    client = MCPHttpClient(config)
    rows, page = [], 1
    while True:
        arguments = {
            "dataset": "item",
            "granularity": "summary",
            "date_from": date_from,
            "date_to": date_to,
            "event_type": "PAID",
            "fields": SYNC_FIELDS,
            "page": page,
            "page_size": 1000,
            "user_query": f"一键同步 {month} 商品经营数据",
        }
        if store_ids:
            arguments["filters"] = {"store_id": store_ids}
        payload = client.call_tool_json(QUERY_TOOL, arguments)
        page_rows = payload.get("items", [])
        if not isinstance(page_rows, list):
            raise ValueError("外部数据源返回的商品数据格式不正确")
        rows.extend(item for item in page_rows if isinstance(item, dict))
        if not payload.get("has_next"):
            break
        page += 1
        if page > 100:
            raise ValueError("外部数据源返回数据超过 10 万行，已停止同步")
    return rows


def sync_month(config, month, *, organization="", store_ids=None, actor=None):
    _validate_config(config)
    _acquire_sync_lock(config)
    organization = _text(organization, config.organization_name or "经营数据")
    selected_store_ids = [str(item) for item in (store_ids or []) if str(item).strip()]
    started_at = time.monotonic()
    job = None
    try:
        job = DataSyncJob.objects.create(
            organization=organization,
            source_system="mcp_sync",
            period=month,
            source_name=f"经营数据接口 / {month}",
        )
        rows = _query_rows(config, month, selected_store_ids)
        if not rows:
            raise ValueError("外部数据源没有返回商品数据，已停止覆盖现有月度数据")
        checksum = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        facts = []
        for row in rows:
            product_id = _text(row.get("item_id"))
            store_id = _text(row.get("store_id"))
            if not product_id or not store_id:
                continue
            platform_code = _text(row.get("platform_type"), "unknown")
            operator_name = _text(row.get("op_manager_name"), "未分配运营")
            facts.append(MonthlyProductFact(
                organization=organization,
                month=month,
                platform=PLATFORM_NAMES.get(platform_code, platform_code),
                shop_id=store_id,
                shop=_text(row.get("store_name"), store_id),
                category_path=_text(row.get("cat_full_name"), "未分类"),
                product_id=product_id,
                product_name=_text(row.get("title")),
                product_code=_text(row.get("outer_id")),
                product_image_url=_text(row.get("pic_url")),
                product_created_at=_datetime(row.get("created")),
                operator_name=operator_name,
                product_cost=_decimal(row.get("gross_goods_cost")),
                gross_sales=_decimal(row.get("gross_sales")),
                sales=_decimal(row.get("paid_amount")) or Decimal("0"),
                sales_volume=_integer(row.get("paid_units")),
                net_sales=_decimal(row.get("net_sales")),
                orders=_integer(row.get("trade_count")),
                visitors=_integer(row.get("item_uv")),
                conversion_rate=_decimal(row.get("item_pay_cvr")),
                stock=_integer(row.get("stock")) if row.get("stock") not in {None, ""} else None,
                refund_amount=_decimal(row.get("total_success_refund_amt")),
                ad_cost=_decimal(row.get("ad_cost")),
                ad_revenue=_decimal(row.get("ad_trade_amt")),
                gross_profit=_decimal(row.get("gross_profit")),
                net_profit=_decimal(row.get("net_profit")),
                source="mcp_sync",
                source_name=f"经营数据接口 / {month}",
                source_checksum=checksum,
                raw_payload=row,
            ))
        if not facts:
            raise ValueError("外部数据源返回数据缺少商品 ID 或店铺 ID，已停止同步")
        # Fill blank source images from exact-scope catalog/history before insert.
        enrich_product_images(facts, organization=organization)

        with transaction.atomic():
            scope = MonthlyProductFact.objects.filter(organization=organization, month=month)
            if selected_store_ids:
                scope = scope.filter(shop_id__in=selected_store_ids)
            scope.delete()
            MonthlyProductFact.objects.bulk_create(facts, batch_size=500)

        queryset = MonthlyProductFact.objects.filter(organization=organization, month=month)
        if selected_store_ids:
            queryset = queryset.filter(shop_id__in=selected_store_ids)
        sync_catalog_from_facts(queryset, source="mcp_sync")
        totals = queryset.aggregate(
            sales=Sum("sales"), sales_volume=Sum("sales_volume"), orders=Sum("orders"), visitors=Sum("visitors"),
            refunds=Sum("refund_amount"), ad_cost=Sum("ad_cost"), ad_revenue=Sum("ad_revenue"),
            gross_profit=Sum("gross_profit"), net_profit=Sum("net_profit"),
        )
        summary = {
            "products": queryset.count(),
            "platforms": queryset.values("platform").distinct().count(),
            "shops": queryset.values("shop").distinct().count(),
            "categories": queryset.values("category_path").distinct().count(),
            **{key: float(value or 0) for key, value in totals.items()},
        }
        job.status = DataSyncJob.Status.SUCCEEDED
        job.total_rows = len(rows)
        job.success_rows = len(facts)
        job.source_checksum = checksum
        job.summary = summary
        job.finished_at = timezone.now()
        job.save(update_fields=[
            "status", "total_rows", "success_rows", "source_checksum", "summary", "finished_at", "updated_at",
        ])
        config.organization_name = organization
        config.connection_status = ConnectionStatus.CONNECTED
        config.last_synced_at = timezone.now()
        config.consecutive_sync_failures = 0
        config.last_error = ""
        config.save(update_fields=[
            "organization_name", "connection_status", "last_synced_at", "consecutive_sync_failures", "last_error", "updated_at",
        ])
        record_integration_event(
            "mcp", config, "data_sync", actor=actor, success=True, started_at=started_at,
            detail={"organization": organization, "month": month, "store_ids": selected_store_ids, **summary},
        )
        return job
    except Exception as exc:
        if job:
            job.status = DataSyncJob.Status.FAILED
            job.error = str(exc)[:1000]
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error", "finished_at", "updated_at"])
        config.connection_status = ConnectionStatus.ERROR
        config.last_error = str(exc)[:500]
        config.consecutive_sync_failures = min(config.consecutive_sync_failures + 1, 15)
        config.save(update_fields=["connection_status", "last_error", "consecutive_sync_failures", "updated_at"])
        record_integration_event(
            "mcp", config, "data_sync", actor=actor, success=False, started_at=started_at,
            detail={"organization": organization, "month": month, "store_ids": selected_store_ids},
            error_message=str(exc),
        )
        raise
    finally:
        _release_sync_lock(config)

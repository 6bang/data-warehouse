import hashlib
import json
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.warehouse.models import MCPServerConfig
from apps.warehouse.services.mcp import MCPHttpClient
from apps.warehouse.services.mcp_sync import list_stores


COMPARE_TOOL = "data_insight_compare"
QUERY_TOOL = "data_insight_query"
DAILY_REPORT_TOOL = "data_insight_daily_report"
CACHE_SECONDS = 300
STORE_CACHE_SECONDS = 600

METRIC_DEFINITIONS = [
    ("paid_amount", "成交金额", "money"),
    ("ad_cost", "广告花费", "money"),
    ("gross_profit", "毛利润", "money"),
    ("net_profit", "净利润", "money"),
    ("net_profit_margin", "净利率", "percent"),
    ("total_custom_cost", "成本项总费用", "money"),
    ("paid_units", "成交件数", "int"),
    ("gross_sales", "毛销售额", "money"),
    ("net_sales", "净销售额", "money"),
    ("gross_profit_margin", "毛利率", "percent"),
    ("total_success_refund_amt", "总退款金额", "money"),
    ("buyer_count", "成交人数", "int"),
]
COMPARE_FIELDS = [item[0] for item in METRIC_DEFINITIONS] + ["trade_count", "ad_trade_amt", "ad_roi", "visitor_count"]

RANKING_FIELDS = [
    "store_id", "store_name", "platform_type",
    "paid_amount", "paid_units", "trade_count",
    "total_refund_amt", "total_success_refund_amt", "pre_ship_refund_amt", "post_ship_refund_amt",
    "ad_cost", "ad_click", "ad_pv", "ad_roi",
    "gross_sales", "net_sales", "gross_profit", "net_profit", "net_profit_margin",
]

RANKING_NUMBER_FIELDS = [field for field in RANKING_FIELDS if field not in {"store_id", "store_name", "platform_type"}]


def _number(value):
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _active_config():
    config = MCPServerConfig.objects.filter(
        enabled=True,
        data_sync_enabled=True,
    ).order_by("id").first()
    if not config:
        raise ValueError("尚未启用实时经营数据服务，请先在配置中心完成连接")
    return config


def _config_cache_scope(config):
    # Never reuse data after a connection, authorization or tenant change.
    identity = [config.pk, config.endpoint_url, config.auth_token_encrypted,
                config.organization_name, str(config.updated_at)]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]


def _stores(config, *, force_refresh=False):
    cache_key = f"realtime:stores:{_config_cache_scope(config)}"
    stores = None if force_refresh else cache.get(cache_key)
    if stores is None:
        stores = list_stores(config)
        cache.set(cache_key, stores, STORE_CACHE_SECONDS)
    return stores


def _scope_stores(stores, shop, allowed_shops):
    allowed = None if allowed_shops is None else {str(item) for item in allowed_shops if str(item).strip()}
    visible = [item for item in stores if allowed is None or item["store_name"] in allowed]
    if shop:
        if allowed is not None and shop not in allowed:
            raise PermissionError("当前角色无权查看该店铺")
        visible = [item for item in visible if item["store_name"] == shop]
        if not visible:
            raise ValueError("未找到所选店铺，请刷新店铺列表后重试")
    return visible


def _empty_payload(config, stores, today, warning):
    return {
        "date": today.isoformat(),
        "compare_date": (today - timedelta(days=1)).isoformat(),
        "data_through": timezone.localtime().strftime("%H:%M"),
        "source": {"name": "实时数据源", "status": "limited", "warning": warning},
        "available_shops": stores,
        "metrics": {
            key: {"label": label, "format": value_format, "current": None, "compare": None, "change_rate": None}
            for key, label, value_format in METRIC_DEFINITIONS
        },
        "hourly_trend": {"available": False, "hours": list(range(24)), "previous": [], "current": [], "warning": warning},
        "trend_granularity": "hour",
        "rankings": {"shop": [], "item": [], "platform_type": [], "sku_code": [], "op_manager": []},
    }


def _hourly_trend(today, stores):
    """No built-in source provides per-hour sales; report the gap instead of guessing.

    A compatible MCP or data API that returns hourly order amounts can be wired in here
    through its own adapter and tests.
    """
    return {
        "available": False, "hours": list(range(24)), "previous": [], "current": [],
        "warning": "当前数据源未提供小时级成交数据，小时趋势暂不可用",
    }


def _platform_rankings(shop_rows):
    grouped = {}
    for row in shop_rows:
        platform = str(row.get("platform_type") or "unknown")
        item = grouped.setdefault(platform, {"platform_type": platform})
        for field in RANKING_NUMBER_FIELDS:
            value = _number(row.get(field))
            if value is not None:
                item[field] = (item.get(field) or 0) + value
    for item in grouped.values():
        paid_amount = item.get("paid_amount") or 0
        item["net_profit_margin"] = (item.get("net_profit") or 0) / paid_amount if paid_amount else None
        item["ad_roi"] = (item.get("gross_sales") or 0) / item["ad_cost"] if item.get("ad_cost") else None
    return sorted(grouped.values(), key=lambda item: item.get("paid_amount") or 0, reverse=True)


def realtime_dashboard(*, shop="", allowed_shops=None, force_refresh=False):
    config = _active_config()
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    stores = _scope_stores(_stores(config, force_refresh=force_refresh), shop, allowed_shops)
    if allowed_shops is not None and not stores:
        return _empty_payload(config, [], today, "当前账号尚未分配可查看店铺")

    store_ids = [item["store_id"] for item in stores]
    scope_hash = hashlib.sha256(json.dumps(store_ids, sort_keys=True).encode()).hexdigest()[:16]
    cache_key = f"realtime:dashboard:{_config_cache_scope(config)}:{today.isoformat()}:{scope_hash}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    filters = {"store_id": store_ids} if store_ids else {}
    client = MCPHttpClient(config)
    compare = client.call_tool_json(COMPARE_TOOL, {
        "dataset": "shop",
        "granularity": "summary",
        "date_from": today.isoformat(),
        "date_to": today.isoformat(),
        "compare_date_from": yesterday.isoformat(),
        "compare_date_to": yesterday.isoformat(),
        "event_type": "PAID",
        "fields": COMPARE_FIELDS,
        "filters": filters,
        "user_query": "经营数据云仓实时首页：今日对比昨日",
    })
    ranking = client.call_tool_json(QUERY_TOOL, {
        "dataset": "shop",
        "granularity": "summary",
        "date_from": today.isoformat(),
        "date_to": today.isoformat(),
        "event_type": "PAID",
        "fields": RANKING_FIELDS,
        "filters": filters,
        "sort": [{"field": "paid_amount", "order": "desc"}],
        "page_size": 100,
        "user_query": "经营数据云仓实时首页：今日店铺完整经营排行榜",
    })
    report_args = {
        "date": today.isoformat(),
        "event_type": "PAID",
        "top_n": 10,
        "user_query": "经营数据云仓实时首页：今日排行榜",
    }
    if store_ids:
        report_args["store_id"] = store_ids
    report = client.call_tool_json(DAILY_REPORT_TOOL, report_args)
    hourly_trend = _hourly_trend(today, stores)

    raw_metrics = compare.get("metrics", {})
    metrics = {}
    for key, label, value_format in METRIC_DEFINITIONS:
        metric = raw_metrics.get(key, {}) if isinstance(raw_metrics, dict) else {}
        metrics[key] = {
            "label": label,
            "format": value_format,
            "current": _number(metric.get("current")),
            "compare": _number(metric.get("compare")),
            "change_rate": _number(metric.get("change_rate")),
        }

    result = {
        "date": today.isoformat(),
        "compare_date": yesterday.isoformat(),
        "data_through": timezone.localtime().strftime("%H:%M"),
        "source": {
            "name": "实时数据源",
            "status": "live",
            "warning": "今日指标、排行榜与小时趋势均来自已授权的实时经营数据连接",
        },
        "available_shops": stores,
        "metrics": metrics,
        "hourly_trend": hourly_trend,
        "trend_granularity": "hour",
        "rankings": {
            "shop": ranking.get("items", []),
            "item": report.get("top_items", {}).get("items", []),
            "platform_type": _platform_rankings(ranking.get("items", [])),
            "sku_code": [],
            "op_manager": [],
        },
    }
    cache.set(cache_key, result, CACHE_SECONDS)
    return result

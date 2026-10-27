import calendar
import json
import time
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from urllib import error, request

from django.db import transaction
from django.utils import timezone

from apps.warehouse.models import MonthlyProductFact, OperationStrategy, ProductCatalog, ProductData, StrategyAlert, StrategyRule
from apps.warehouse.services.integrations import ai_provider_credentials, record_integration_event


METRIC_LABELS = dict(StrategyRule.Metric.choices)
OPERATOR_LABELS = dict(StrategyRule.Operator.choices)


def product_url(platform, product_id):
    platform = (platform or "").lower()
    product_id = str(product_id or "")
    if not product_id:
        return ""
    if "淘宝" in platform or "taobao" in platform or "天猫" in platform or "tmall" in platform:
        return f"https://item.taobao.com/item.htm?id={product_id}"
    if "京东" in platform or platform == "jd":
        return f"https://item.jd.com/{product_id}.html"
    if "拼多多" in platform or "pdd" in platform:
        return f"https://mobile.yangkeduo.com/goods.html?goods_id={product_id}"
    return ""


def _ratio(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _month_end(month):
    year, month_number = [int(item) for item in month.split("-")]
    return date(year, month_number, calendar.monthrange(year, month_number)[1])


def metric_value(fact, metric):
    if metric == StrategyRule.Metric.ROI:
        return _ratio(fact.ad_revenue, fact.ad_cost)
    if metric == StrategyRule.Metric.REFUND_RATE:
        return _ratio(fact.refund_amount, fact.sales)
    if metric == StrategyRule.Metric.GROSS_MARGIN:
        return _ratio(fact.gross_profit, fact.sales)
    if metric == StrategyRule.Metric.NET_MARGIN:
        return _ratio(fact.net_profit, fact.net_sales)
    if metric == StrategyRule.Metric.PRODUCT_AGE_DAYS:
        if not fact.product_created_at:
            return None
        return Decimal((_month_end(fact.month) - fact.product_created_at.date()).days)
    value = getattr(fact, metric, None)
    return Decimal(value) if value is not None else None


def rule_matches(value, rule):
    if value is None:
        return False
    threshold = Decimal(rule.threshold)
    if rule.operator == StrategyRule.Operator.LT:
        return value < threshold
    if rule.operator == StrategyRule.Operator.LTE:
        return value <= threshold
    if rule.operator == StrategyRule.Operator.GT:
        return value > threshold
    if rule.operator == StrategyRule.Operator.GTE:
        return value >= threshold
    if rule.operator == StrategyRule.Operator.EQ:
        return value == threshold
    if rule.operator == StrategyRule.Operator.BETWEEN:
        return rule.threshold_max is not None and threshold <= value <= Decimal(rule.threshold_max)
    return False


def _scope_queryset(strategy, month):
    queryset = MonthlyProductFact.objects.filter(month=month)
    for field in ("organization", "platform", "shop", "category_path"):
        value = getattr(strategy, field)
        if value:
            queryset = queryset.filter(**{field: value})
    if strategy.strategy_type != OperationStrategy.StrategyType.ALL_PRODUCT:
        cutoff = _month_end(month)
        boundary = strategy.new_product_days
        fact_ids = []
        for fact in queryset.only("id", "product_created_at"):
            if not fact.product_created_at:
                continue
            age = (cutoff - fact.product_created_at.date()).days
            if strategy.strategy_type == OperationStrategy.StrategyType.NEW_PRODUCT and age <= boundary:
                fact_ids.append(fact.id)
            elif strategy.strategy_type == OperationStrategy.StrategyType.MATURE_PRODUCT and age > boundary:
                fact_ids.append(fact.id)
        queryset = queryset.filter(id__in=fact_ids)
    return queryset


def _format_value(metric, value):
    if metric in {StrategyRule.Metric.REFUND_RATE, StrategyRule.Metric.GROSS_MARGIN, StrategyRule.Metric.NET_MARGIN, StrategyRule.Metric.CONVERSION_RATE}:
        return f"{float(value) * 100:.1f}%"
    if metric in {StrategyRule.Metric.SALES, StrategyRule.Metric.REFUND_AMOUNT, StrategyRule.Metric.AD_COST, StrategyRule.Metric.GROSS_PROFIT, StrategyRule.Metric.NET_PROFIT}:
        return f"¥{float(value):,.2f}"
    return f"{float(value):,.2f}"


# ---- Structured new/mature product strategies ---------------------------------
# These helpers intentionally use ProductData (daily grain) and ProductCatalog
# (product identity/create time).  MonthlyProductFact remains the alert anchor so
# existing alert/plan APIs do not need a second foreign-key model.
NEW_WEEK_RANGES = {
    "week2": (8, 14),
    "week3": (15, 21),
    "week4": (22, 28),
    "week5": (29, 35),
}
NEW_WEEK_THRESHOLDS = {
    "week2": {"A": (4, 28), "B": (3, 21), "C": (1, 7), "D": (0, 0)},
    "week3": {"A": (5, 35), "B": (4, 28), "C": (1, 7), "D": (0, 0)},
    "week4": {"A": (8, 56), "B": (5, 35), "C": (1, 7), "D": (0, 0)},
    # The weekly threshold for B is deliberately 40, matching the supplied
    # business table (rather than deriving it from 8 * 7).
    "week5": {"A": (10, 70), "B": (8, 40), "C": (1, 7), "D": (0, 0)},
}


def _catalog_identity(catalog):
    return {
        "organization": catalog.organization or "未识别组织",
        "platform": catalog.platform or "未识别平台",
        "shop": catalog.shop or "未识别店铺",
        "shop_id": catalog.shop_id or "",
        "product_id": catalog.product_id,
        "product_name": catalog.product_name or catalog.product_id,
        "product_code": catalog.product_code or "",
        "product_created_at": catalog.product_created_at,
        "product_image_url": catalog.product_image_url or "",
    }


def _as_of_date(month):
    """Use the latest available daily row in *month*, not wall-clock time."""
    try:
        end = _month_end(month)
    except (TypeError, ValueError):
        return None
    return ProductData.objects.filter(
        record_type=ProductData.RecordType.PRODUCT,
        date__gte=end.replace(day=1), date__lte=min(end, timezone.localdate()),
    ).order_by("-date").values_list("date", flat=True).first()


def _structured_catalogs(strategy, as_of):
    queryset = ProductCatalog.objects.exclude(product_created_at__isnull=True)
    for field in ("organization", "platform", "shop"):
        value = getattr(strategy, field, "")
        if value:
            queryset = queryset.filter(**{field: value})
    if strategy.category_path:
        # Category is retained on monthly facts; never silently widen a scope.
        matching = MonthlyProductFact.objects.filter(category_path=strategy.category_path)
        identities = set(matching.values_list("organization", "platform", "shop", "product_id"))
        queryset = queryset.filter(pk__in=[catalog.pk for catalog in queryset if
            (catalog.organization, catalog.platform, catalog.shop, catalog.product_id) in identities])
    if strategy.strategy_code == OperationStrategy.StrategyCode.NEW_PRODUCT_35D:
        cutoff = as_of - timedelta(days=34)  # day 1 .. day 35 inclusive
        queryset = queryset.filter(product_created_at__date__gte=cutoff, product_created_at__date__lte=as_of)
    else:
        queryset = queryset.filter(product_created_at__date__lte=as_of - timedelta(days=35))
    return list(queryset)


def _daily_rows(catalog, start, end):
    return list(ProductData.objects.filter(
        shop=catalog.shop, product_id=catalog.product_id, date__gte=start, date__lte=end,
        record_type=ProductData.RecordType.PRODUCT,
    ).order_by("date"))


def _grade_new(cumulative):
    cumulative = int(cumulative or 0)
    if cumulative >= 500:
        return "A"
    if cumulative >= 100:
        return "B"
    if cumulative >= 1:
        return "C"
    return "D"


def _grade_mature(recent):
    recent = int(recent or 0)
    if recent >= 1000:
        return "A"
    if recent >= 500:
        return "B"
    if recent >= 100:
        return "C"
    if recent >= 1:
        return "D"
    return "E"


def _conversion_rate(rows):
    visitors = sum(int(row.visitors or 0) for row in rows)
    orders = sum(int(row.orders or 0) for row in rows)
    if visitors:
        return Decimal(orders) / Decimal(visitors)
    # No visits is unknown, not a reliable zero conversion rate. Averaging daily
    # conversion percentages would weight low/high-traffic days incorrectly.
    return None


def _conversion_band(value):
    if value >= Decimal("0.03"):
        return "high"
    if value >= Decimal("0.02"):
        return "middle"
    return "low"


def _monthly_fact_for_catalog(catalog, month, rows):
    """Get/create a monthly fact anchor for a daily-product alert."""
    identity = _catalog_identity(catalog)
    rows = [row for row in rows if row.date.strftime("%Y-%m") == month]
    defaults = {
        "category_path": "未分类",
        "product_name": identity["product_name"],
        "product_code": identity["product_code"],
        "product_created_at": identity["product_created_at"],
        "product_image_url": identity["product_image_url"],
        "sales": sum((Decimal(row.sales or 0) for row in rows), Decimal("0")),
        "sales_volume": sum(int(row.sales_volume or 0) for row in rows),
        "orders": sum(int(row.orders or 0) for row in rows),
        "visitors": sum(int(row.visitors or 0) for row in rows),
        "conversion_rate": _conversion_rate(rows),
        "source": "product_data_strategy",
        "raw_payload": {"strategy_anchor": True, "warning": "日粒度策略预警关联记录，不是完整月度采集"},
    }
    fact, _ = MonthlyProductFact.objects.get_or_create(
        organization=identity["organization"], month=month, platform=identity["platform"],
        shop=identity["shop"], product_id=identity["product_id"], defaults=defaults,
    )
    return fact


def _complete_daily_coverage(rows, start, end):
    return len({row.date for row in rows if start <= row.date <= end}) == (end - start).days + 1


def _identity_counts():
    # Daily records have no organization/platform column. Refuse an ambiguous
    # match instead of assigning one company's observations to another company.
    return Counter(ProductCatalog.objects.values_list("shop", "product_id"))


def _finish_structured(strategy, month, as_of, rules, catalogs, triggered, skipped, actor):
    now = timezone.now()
    ids = [alert.id for alert in triggered]
    # Preserve previous evidence when source coverage is missing. Only refresh
    # observed alerts; an unavailable source cannot prove that risk is resolved.
    report, reporter = _agent_report(strategy, triggered, actor)
    if ids:
        StrategyAlert.objects.filter(id__in=ids).update(agent_report=report, reporter_name=reporter, updated_at=now)
    summary = {
        "month": month, "as_of": as_of.isoformat() if as_of else None,
        "scanned_products": len(catalogs), "rules": len(rules), "alerts": len(triggered),
        "reporter": reporter, "strategy_code": strategy.strategy_code, "skipped": dict(skipped),
        "data_source": "商品档案及商品日粒度数据", "conversion_basis": "窗口订单数/访客数",
        "message": "暂无本月日粒度商品数据，未进行评估" if not as_of else "按可用数据日期评估；缺失记录不视为零销量",
    }
    strategy.last_run_at, strategy.last_run_summary = now, summary
    strategy.save(update_fields=["last_run_at", "last_run_summary", "updated_at"])
    return summary


def _structured_alert(strategy, rule, fact, month, observed, description, *, catalog=None, evaluation_date=None, suggestion=None, snapshot=None):
    value = Decimal(observed or 0)
    value_text = _format_value(rule.metric, value)
    identity = _catalog_identity(catalog) if catalog is not None else {
        "product_id": fact.product_id, "product_name": fact.product_name, "shop": fact.shop,
        "organization": fact.organization, "platform": fact.platform, "product_image_url": "",
    }
    title = rule.message_template.format(
        product=identity["product_name"] or identity["product_id"], shop=identity["shop"],
        metric=METRIC_LABELS.get(rule.metric, rule.metric), value=value_text,
    ) if rule.message_template else f"{identity['product_name'] or identity['product_id']}：{rule.name}"
    lookup = {"strategy": strategy, "rule": rule, "month": month}
    if catalog is not None:
        lookup.update({"product_catalog": catalog, "evaluation_date": evaluation_date})
        # A structured alert is daily and must not fabricate a monthly fact.
        defaults_fact = {"product_fact": None}
    else:
        lookup["product_fact"] = fact
        defaults_fact = {}
    alert, created = StrategyAlert.objects.update_or_create(
        **lookup,
        defaults={
            **defaults_fact,
            "organization": identity["organization"], "platform": identity["platform"], "shop": identity["shop"],
            "product_id": identity["product_id"], "product_name": identity["product_name"],
            "product_url": product_url(identity["platform"], identity["product_id"]),
            "operator_name": getattr(fact, "operator_name", "") if fact is not None else "",
            "metric": rule.metric, "observed_value": value,
            "threshold_snapshot": snapshot or {"operator": rule.operator, "threshold": str(rule.threshold), "weekly_threshold": str(rule.weekly_threshold) if rule.weekly_threshold is not None else None},
            "level": rule.level, "title": title, "description": description,
            "suggestion": suggestion if suggestion is not None else rule.suggestion,
            "evaluation_date": evaluation_date,
        },
    )
    if not created and alert.status == StrategyAlert.Status.RESOLVED:
        alert.status = StrategyAlert.Status.OPEN
        alert.save(update_fields=["status", "updated_at"])
    return alert


def _run_new_product_strategy(strategy, month, actor=None):
    as_of = _as_of_date(month)
    if not as_of:
        return {"month": month, "as_of": None, "scanned_products": 0, "rules": 0, "alerts": 0, "skipped": {"missing_daily_data": 1}, "message": "暂无日粒度商品数据"}
    catalogs = _structured_catalogs(strategy, as_of)
    rules = list(strategy.rules.filter(enabled=True))
    triggered, triggered_ids = [], set()
    skipped = Counter()
    for catalog in catalogs:
        created = catalog.product_created_at.date()
        age = (as_of - created).days + 1  # creation date is day 1
        if age < 1 or age > 35:
            continue
        stage = "final35" if age == 35 else next((name for name, (start, end) in NEW_WEEK_RANGES.items() if start <= age <= end), "week1")
        if stage == "week1":
            continue
        first35 = _daily_rows(catalog, created, min(as_of, created + timedelta(days=34)))
        if not first35:
            skipped["missing_daily_data"] += 1
            continue
        cumulative = sum(int(row.sales_volume or 0) for row in first35)
        grade = _grade_new(cumulative)
        if stage == "final35":
            if not _complete_daily_coverage(first35, created, created + timedelta(days=34)):
                skipped["incomplete_35d_coverage"] += 1
                continue
            fact = None
            for rule in rules:
                if rule.stage != stage or rule.product_grade != grade:
                    continue
                alert = _structured_alert(
                    strategy, rule, fact, month, cumulative,
                    f"新品第35天结束，35天累计销量 {cumulative} 件，判定为{grade}类。",
                    catalog=catalog, evaluation_date=as_of,
                    snapshot={"stage": stage, "product_grade": grade, "age_days": age, "cumulative_35d_sales": cumulative},
                )
                if alert.id not in triggered_ids:
                    triggered.append(alert)
                    triggered_ids.add(alert.id)
            continue
        start_day, end_day = NEW_WEEK_RANGES[stage]
        week_start = created + timedelta(days=start_day - 1)
        week_end = created + timedelta(days=end_day - 1)
        rows_week = _daily_rows(catalog, week_start, min(as_of, week_end))
        today_rows = [row for row in rows_week if row.date == as_of]
        if not today_rows:
            skipped["missing_today"] += 1
            continue
        daily_sales = sum(int(row.sales_volume or 0) for row in today_rows)
        weekly_sales = sum(int(row.sales_volume or 0) for row in rows_week)
        week_complete = as_of >= week_end and _complete_daily_coverage(rows_week, week_start, week_end)
        fact = None
        for rule in rules:
            if rule.stage != stage or rule.product_grade != grade:
                continue
            default_daily, default_weekly = NEW_WEEK_THRESHOLDS[stage][grade]
            daily_min = int(rule.threshold) if rule.threshold is not None else default_daily
            weekly_min = int(rule.weekly_threshold) if rule.weekly_threshold is not None else default_weekly
            # D is only meaningful at the end of a complete week; other grades
            # are checked daily and once again against the complete-week total.
            if grade == "D":
                matched = week_complete and weekly_sales == weekly_min
                observed = weekly_sales
                metric = "weekly_sales_volume"
            else:
                matched = daily_sales < daily_min or (week_complete and weekly_sales < weekly_min)
                observed = daily_sales if daily_sales < daily_min else weekly_sales
                metric = "daily_sales_volume" if daily_sales < daily_min else "weekly_sales_volume"
            if not matched:
                continue
            description = f"新品第{age}天，{grade}类；日销量 {daily_sales} 件，当前周累计 {weekly_sales} 件。"
            alert = _structured_alert(
                strategy, rule, fact, month, observed, description, catalog=catalog, evaluation_date=as_of,
                snapshot={"stage": stage, "product_grade": grade, "age_days": age, "daily_sales": daily_sales, "weekly_sales": weekly_sales, "daily_threshold": daily_min, "weekly_threshold": weekly_min, "metric": metric},
            )
            if alert.id not in triggered_ids:
                triggered.append(alert)
                triggered_ids.add(alert.id)
    now = timezone.now()
    stale = StrategyAlert.objects.filter(strategy=strategy, month=month).exclude(status=StrategyAlert.Status.CONVERTED)
    if triggered_ids:
        stale = stale.exclude(id__in=triggered_ids)
    stale.update(status=StrategyAlert.Status.RESOLVED, updated_at=now)
    report, reporter = _agent_report(strategy, triggered, actor)
    if triggered_ids:
        StrategyAlert.objects.filter(id__in=triggered_ids).update(agent_report=report, reporter_name=reporter, updated_at=now)
    summary = {"month": month, "as_of": as_of.isoformat(), "scanned_products": len(catalogs), "rules": len(rules), "alerts": len(triggered), "reporter": reporter, "strategy_code": strategy.strategy_code, "skipped": dict(skipped)}
    strategy.last_run_at, strategy.last_run_summary = now, summary
    strategy.save(update_fields=["last_run_at", "last_run_summary", "updated_at"])
    return summary


def _run_mature_product_strategy(strategy, month, actor=None):
    as_of = _as_of_date(month)
    if not as_of:
        return {"month": month, "as_of": None, "scanned_products": 0, "rules": 0, "alerts": 0, "skipped": {"missing_daily_data": 1}, "message": "暂无日粒度商品数据"}
    catalogs = _structured_catalogs(strategy, as_of)
    rules = list(strategy.rules.filter(enabled=True))
    triggered, triggered_ids = [], set()
    skipped = Counter()
    for catalog in catalogs:
        rows = _daily_rows(catalog, as_of - timedelta(days=29), as_of)
        recent_sales = sum(int(row.sales_volume or 0) for row in rows)
        grade, conversion = _grade_mature(recent_sales), _conversion_rate(rows)
        if not rows:
            skipped["missing_daily_data"] += 1
            continue
        if conversion is None:
            skipped["missing_conversion_coverage"] += 1
            continue
        if not _complete_daily_coverage(rows, as_of - timedelta(days=29), as_of):
            skipped["incomplete_30d_coverage"] += 1
            continue
        band = _conversion_band(conversion)
        fact = None
        for rule in rules:
            if rule.product_grade != grade or (rule.conversion_band and rule.conversion_band != band):
                continue
            actions = rule.suggestion or "按策略执行标题、主图、详情、评价、问大家、SKU优化；付费方向覆盖拉新-蓄水-收割-测图。"
            horse = {"high": "上等马", "middle": "中等马", "low": "下等马"}.get(band, band)
            description = f"老品近30天累计销量 {recent_sales} 件，{grade}类；转化率 {conversion * 100:.2f}%，判定为{horse}。"
            alert = _structured_alert(
                strategy, rule, fact, month, conversion, description, catalog=catalog, evaluation_date=as_of,
                suggestion=actions,
                snapshot={"product_grade": grade, "recent_30d_sales": recent_sales, "conversion_rate": str(conversion), "conversion_band": band, "strategy_direction": "拉升计划" if band == "high" else "优化计划"},
            )
            if alert.id not in triggered_ids:
                triggered.append(alert)
                triggered_ids.add(alert.id)
    now = timezone.now()
    stale = StrategyAlert.objects.filter(strategy=strategy, month=month).exclude(status=StrategyAlert.Status.CONVERTED)
    if triggered_ids:
        stale = stale.exclude(id__in=triggered_ids)
    stale.update(status=StrategyAlert.Status.RESOLVED, updated_at=now)
    report, reporter = _agent_report(strategy, triggered, actor)
    if triggered_ids:
        StrategyAlert.objects.filter(id__in=triggered_ids).update(agent_report=report, reporter_name=reporter, updated_at=now)
    summary = {"month": month, "as_of": as_of.isoformat(), "scanned_products": len(catalogs), "rules": len(rules), "alerts": len(triggered), "reporter": reporter, "strategy_code": strategy.strategy_code, "skipped": dict(skipped)}
    strategy.last_run_at, strategy.last_run_summary = now, summary
    strategy.save(update_fields=["last_run_at", "last_run_summary", "updated_at"])
    return summary


def _rule_report(strategy, alerts):
    critical = sum(item.level == StrategyRule.Level.CRITICAL for item in alerts)
    return (
        f"{strategy.name} 本轮命中 {len(alerts)} 个商品，其中严重 {critical} 个。"
        "请优先核对严重预警商品，确认数据后转为运营计划并指定负责人。"
    )


def _agent_report(strategy, alerts, actor=None):
    fallback = _rule_report(strategy, alerts)
    if strategy.report_mode != OperationStrategy.ReportMode.AGENT or not strategy.agent_provider_id or not alerts:
        return fallback, "系统规则播报"
    started_at = time.monotonic()
    try:
        credentials = ai_provider_credentials(strategy.agent_provider)
        if not credentials or not credentials["api_key"]:
            raise ValueError("所选智能体模型未配置 API Key")
        evidence = [{
            "商品": item.product_name,
            "店铺": item.shop,
            "规则": item.rule.name,
            "指标": METRIC_LABELS.get(item.metric, item.metric),
            "当前值": str(item.observed_value),
            "等级": item.level,
        } for item in alerts[:30]]
        prompt = (
            "你是电商运营策略预警智能体。请只依据给定证据，用中文输出一段不超过500字的预警播报，"
            "包含总体风险、优先商品、原因判断和行动建议，不得虚构缺失数据。"
            f"\n策略：{strategy.name}\n证据：{json.dumps(evidence, ensure_ascii=False)}"
        )
        body = {
            "model": credentials["model"], "stream": False,
            "messages": [{"role": "user", "content": prompt}], "max_tokens": 800,
        }
        req = request.Request(
            credentials["base_url"] + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {credentials['api_key']}"},
        )
        with request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read())
        report = payload["choices"][0]["message"]["content"].strip()
        record_integration_event("strategy_agent", strategy.agent_provider, "report", actor=actor, success=True, started_at=started_at, detail={"alerts": len(alerts)})
        return report or fallback, strategy.agent_provider.name
    except (ValueError, KeyError, IndexError, error.URLError, json.JSONDecodeError) as exc:
        record_integration_event("strategy_agent", strategy.agent_provider, "report", actor=actor, success=False, started_at=started_at, error_message=str(exc))
        return f"{fallback}（智能体播报失败，已回退系统规则：{exc}）", "系统规则播报"


@transaction.atomic
def run_strategy(strategy, month, actor=None):
    if not strategy.enabled:
        raise ValueError("策略未启用")
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month 必须使用 YYYY-MM 格式")
    if strategy.strategy_code == OperationStrategy.StrategyCode.NEW_PRODUCT_35D:
        return _run_new_product_strategy(strategy, month, actor)
    if strategy.strategy_code == OperationStrategy.StrategyCode.MATURE_PRODUCT_30D:
        return _run_mature_product_strategy(strategy, month, actor)
    rules = list(strategy.rules.filter(enabled=True))
    facts = list(_scope_queryset(strategy, month))
    triggered = []
    triggered_ids = set()
    now = timezone.now()
    for fact in facts:
        for rule in rules:
            value = metric_value(fact, rule.metric)
            if not rule_matches(value, rule):
                continue
            value_text = _format_value(rule.metric, value)
            title = rule.message_template.format(
                product=fact.product_name or fact.product_id, shop=fact.shop,
                metric=METRIC_LABELS.get(rule.metric, rule.metric), value=value_text,
            ) if rule.message_template else f"{fact.product_name or fact.product_id}：{rule.name}"
            alert, created = StrategyAlert.objects.update_or_create(
                strategy=strategy, rule=rule, product_fact=fact, month=month,
                defaults={
                    "organization": fact.organization, "platform": fact.platform, "shop": fact.shop,
                    "product_id": fact.product_id, "product_name": fact.product_name,
                    "product_url": product_url(fact.platform, fact.product_id), "operator_name": fact.operator_name,
                    "metric": rule.metric, "observed_value": value,
                    "threshold_snapshot": {"operator": rule.operator, "operator_label": OPERATOR_LABELS.get(rule.operator, rule.operator), "threshold": str(rule.threshold), "threshold_max": str(rule.threshold_max) if rule.threshold_max is not None else None},
                    "level": rule.level, "title": title,
                    "description": f"{METRIC_LABELS.get(rule.metric, rule.metric)}当前为 {value_text}，触发规则“{rule.name}”。",
                    "suggestion": rule.suggestion,
                },
            )
            if not created and alert.status == StrategyAlert.Status.RESOLVED:
                alert.status = StrategyAlert.Status.OPEN
                alert.save(update_fields=["status", "updated_at"])
            triggered.append(alert)
            triggered_ids.add(alert.id)
    stale = StrategyAlert.objects.filter(strategy=strategy, month=month).exclude(status=StrategyAlert.Status.CONVERTED)
    if triggered_ids:
        stale = stale.exclude(id__in=triggered_ids)
    stale.update(status=StrategyAlert.Status.RESOLVED, updated_at=now)
    report, reporter = _agent_report(strategy, triggered, actor)
    if triggered_ids:
        StrategyAlert.objects.filter(id__in=triggered_ids).update(agent_report=report, reporter_name=reporter, updated_at=now)
    summary = {"month": month, "scanned_products": len(facts), "rules": len(rules), "alerts": len(triggered), "reporter": reporter}
    strategy.last_run_at = now
    strategy.last_run_summary = summary
    strategy.save(update_fields=["last_run_at", "last_run_summary", "updated_at"])
    return summary


def run_enabled_strategies(month, actor=None, *, due_hour=None):
    queryset = OperationStrategy.objects.filter(enabled=True, schedule_enabled=True)
    if due_hour is not None:
        queryset = queryset.filter(schedule_hour=due_hour)
    summaries = []
    for strategy in queryset:
        summaries.append({"strategy_id": strategy.id, **run_strategy(strategy, month, actor)})
    return summaries

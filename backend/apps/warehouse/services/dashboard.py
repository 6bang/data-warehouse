from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce

from apps.warehouse.models import AbnormalRecord, OperationTask, ProductCatalog, ProductData


def _product_image_map(rows):
    """Resolve images only within the visible shop/product identity."""
    keys = {(row.get("shop", ""), row.get("product_id", "")) for row in rows if row.get("shop") and row.get("product_id")}
    if not keys:
        return {}
    shops = {key[0] for key in keys}
    product_ids = {key[1] for key in keys}
    result = {}
    for item in ProductCatalog.objects.filter(shop__in=shops, product_id__in=product_ids).exclude(product_image_url="").values(
        "shop", "product_id", "product_image_url", "updated_at"
    ).order_by("-updated_at"):
        key = (item["shop"], item["product_id"])
        if key in keys and key not in result:
            result[key] = item["product_image_url"]
    return result


def month_bounds(month):
    if isinstance(month, date):
        start = month.replace(day=1)
    else:
        try:
            year, number = map(int, str(month).split("-"))
            start = date(year, number, 1)
        except (TypeError, ValueError):
            raise ValueError("month 格式应为 YYYY-MM")
    end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    return start, end


def previous_month(month_start):
    return (month_start - timedelta(days=1)).replace(day=1)


def available_months(shop="", allowed_shops=None):
    queryset = ProductData.objects.filter(shop=shop) if shop else ProductData.objects.all()
    if allowed_shops is not None:
        queryset = queryset.filter(shop__in=allowed_shops)
    dates = queryset.values_list("date", flat=True).distinct().order_by("date")
    return sorted({item.strftime("%Y-%m") for item in dates}, reverse=True)


def _base_rows(start, end, shop="", allowed_shops=None):
    rows = ProductData.objects.filter(date__gte=start, date__lt=end)
    if allowed_shops is not None:
        rows = rows.filter(shop__in=allowed_shops)
    return rows.filter(shop=shop) if shop else rows


def _totals_for_range(start, end, shop="", allowed_shops=None):
    rows = _base_rows(start, end, shop, allowed_shops)
    summaries = rows.filter(record_type=ProductData.RecordType.SHOP_SUMMARY)
    summary_dates = list(summaries.values_list("date", flat=True).distinct())
    commerce = rows.filter(
        Q(record_type=ProductData.RecordType.SHOP_SUMMARY)
        | (Q(record_type=ProductData.RecordType.PRODUCT) & ~Q(date__in=summary_dates))
    )
    ad_rows = rows.filter(record_type=ProductData.RecordType.PRODUCT)
    commerce_totals = commerce.aggregate(
        sales=Coalesce(Sum("sales"), Decimal("0")),
        sales_volume=Coalesce(Sum("sales_volume"), 0),
        orders=Coalesce(Sum("orders"), 0),
        visitors=Coalesce(Sum("visitors"), 0),
        profit=Sum("profit"),
    )
    ads = ad_rows.aggregate(
        ad_cost=Coalesce(Sum("ad_cost"), Decimal("0")),
        ad_revenue=Coalesce(Sum("ad_revenue"), Decimal("0")),
    )
    visitors = commerce_totals["visitors"]
    orders = commerce_totals["orders"]
    return {
        **commerce_totals,
        **ads,
        "conversion_rate": Decimal(orders) / Decimal(visitors) if visitors else Decimal("0"),
        "roi": ads["ad_revenue"] / ads["ad_cost"] if ads["ad_cost"] else Decimal("0"),
    }


def _delta(current, previous):
    if current is None:
        return None
    current, previous = Decimal(current or 0), Decimal(previous or 0)
    return (current - previous) / previous if previous else None


def monthly_dashboard(month="", shop="", allowed_shops=None):
    months = available_months(shop, allowed_shops)
    month = month or (months[0] if months else "")
    if not month:
        return {"month": None, "available_months": [], "metrics": {}, "monthly_trend": [], "daily_trend": [], "abnormal": [], "task_summary": {}}
    start, end = month_bounds(month)
    previous_start = previous_month(start)
    last_data_date = _base_rows(start, end, shop, allowed_shops).aggregate(value=Max("date"))["value"]
    is_partial = bool(months and month == months[0] and last_data_date and last_data_date < end - timedelta(days=1))
    comparison_end = previous_start + (last_data_date - start + timedelta(days=1)) if is_partial else start
    current = _totals_for_range(start, end, shop, allowed_shops)
    previous = _totals_for_range(previous_start, comparison_end, shop, allowed_shops)
    metrics = {key: {"value": value, "change_rate": _delta(value, previous.get(key))} for key, value in current.items() if key != "ad_revenue"}

    daily_trend = []
    dates = _base_rows(start, end, shop, allowed_shops).values_list("date", flat=True).distinct().order_by("date")
    for day in dates:
        total = _totals_for_range(day, day + timedelta(days=1), shop, allowed_shops)
        daily_trend.append({"date": day, "sales": total["sales"], "visitors": total["visitors"], "ad_cost": total["ad_cost"], "roi": total["roi"]})

    monthly_trend = []
    for item in sorted(months[:12]):
        item_start, item_end = month_bounds(item)
        total = _totals_for_range(item_start, item_end, shop, allowed_shops)
        monthly_trend.append({"month": item, "sales": total["sales"], "ad_cost": total["ad_cost"], "profit": total["profit"], "roi": total["roi"]})

    abnormal_qs = AbnormalRecord.objects.filter(date__gte=start, date__lt=end).exclude(status=AbnormalRecord.Status.RESOLVED)
    if allowed_shops is not None:
        abnormal_qs = abnormal_qs.filter(shop__in=allowed_shops)
    if shop:
        abnormal_qs = abnormal_qs.filter(shop=shop)
    abnormal = list(abnormal_qs.order_by("level", "-change_rate").values("id", "date", "type", "level", "product_id", "shop", "description", "suggestion")[:12])
    abnormal_images = _product_image_map(abnormal)
    for item in abnormal:
        item["product_image_url"] = abnormal_images.get((item.get("shop", ""), item.get("product_id", "")), "")
    task_qs = OperationTask.objects.filter(created_at__date__gte=start, created_at__date__lt=end)
    task_counts = {item["status"]: item["count"] for item in task_qs.values("status").annotate(count=Count("id"))}
    return {
        "month": month,
        "previous_month": previous_start.strftime("%Y-%m"),
        "comparison_label": f"{previous_start:%Y-%m} 同期" if is_partial else f"{previous_start:%Y-%m} 整月",
        "is_partial": is_partial,
        "data_through": last_data_date,
        "available_months": months,
        "metrics": metrics,
        "monthly_trend": monthly_trend,
        "daily_trend": daily_trend,
        "abnormal_count": abnormal_qs.count(),
        "abnormal": abnormal,
        "task_summary": task_counts,
    }


def _growth_score(current, previous):
    current, previous = float(current or 0), float(previous or 0)
    if previous <= 0:
        return 60.0 if current <= 0 else 80.0
    return max(0.0, min(100.0, 60 + ((current - previous) / previous) * 120))


def monthly_product_ranking(month, shop="", search="", ordering="-sales", allowed_shops=None):
    start, end = month_bounds(month)
    rows = _base_rows(start, end, shop, allowed_shops).filter(record_type=ProductData.RecordType.PRODUCT)
    if search:
        rows = rows.filter(Q(product_id__icontains=search) | Q(product_name__icontains=search))
    grouped = list(rows.values("shop", "product_id", "product_name").annotate(
        sales=Coalesce(Sum("sales"), Decimal("0")),
        sales_volume=Coalesce(Sum("sales_volume"), 0),
        orders=Coalesce(Sum("orders"), 0),
        visitors=Coalesce(Sum("visitors"), 0),
        impressions=Coalesce(Sum("impressions"), 0),
        clicks=Coalesce(Sum("clicks"), 0),
        ad_cost=Coalesce(Sum("ad_cost"), Decimal("0")),
        ad_revenue=Coalesce(Sum("ad_revenue"), Decimal("0")),
        profit=Sum("profit"),
        stock=Max("stock"),
    ))
    previous_start = previous_month(start)
    latest_month = available_months(shop, allowed_shops)[:1]
    last_data_date = rows.aggregate(value=Max("date"))["value"]
    is_partial = bool(latest_month and month == latest_month[0] and last_data_date and last_data_date < end - timedelta(days=1))
    previous_end = previous_start + (last_data_date - start + timedelta(days=1)) if is_partial else start
    previous_rows = _base_rows(previous_start, previous_end, shop, allowed_shops).filter(record_type=ProductData.RecordType.PRODUCT)
    previous_map = {
        (item["shop"], item["product_id"]): item
        for item in previous_rows.values("shop", "product_id").annotate(
            sales=Coalesce(Sum("sales"), Decimal("0")), visitors=Coalesce(Sum("visitors"), 0),
            orders=Coalesce(Sum("orders"), 0), profit=Sum("profit"),
        )
    }
    for item in grouped:
        item["click_rate"] = Decimal(item["clicks"]) / Decimal(item["impressions"]) if item["impressions"] else Decimal("0")
        item["conversion_rate"] = Decimal(item["orders"]) / Decimal(item["visitors"]) if item["visitors"] else Decimal("0")
        item["roi"] = item["ad_revenue"] / item["ad_cost"] if item["ad_cost"] else Decimal("0")
        previous = previous_map.get((item["shop"], item["product_id"]), {})
        sales_score = _growth_score(item["sales"], previous.get("sales"))
        traffic_score = _growth_score(item["visitors"], previous.get("visitors"))
        previous_conversion = Decimal(previous.get("orders") or 0) / Decimal(previous.get("visitors") or 1)
        if previous_conversion:
            stability = max(0.0, min(100.0, 100 - abs(float((item["conversion_rate"] - previous_conversion) / previous_conversion)) * 180))
        else:
            stability = 70.0 if item["conversion_rate"] else 50.0
        profit_health = 60.0 if item["profit"] is None or not item["sales"] else max(0.0, min(100.0, float(item["profit"] / item["sales"]) / 0.25 * 100))
        item["health_components"] = {"sales_growth": round(sales_score, 1), "traffic_growth": round(traffic_score, 1), "conversion_stability": round(stability, 1), "profit_health": round(profit_health, 1)}
        item["health_score"] = round(sales_score * .35 + traffic_score * .25 + stability * .2 + profit_health * .2, 1)
        item["month"] = month
        item["id"] = f"{item['shop']}:{item['product_id']}"
    image_map = _product_image_map(grouped)
    for item in grouped:
        item["product_image_url"] = image_map.get((item.get("shop", ""), item.get("product_id", "")), "")
    allowed = {"sales", "sales_volume", "visitors", "conversion_rate", "ad_cost", "roi", "profit", "stock", "health_score"}
    key = ordering.lstrip("-") if ordering.lstrip("-") in allowed else "sales"
    grouped.sort(key=lambda item: (item.get(key) is not None, item.get(key) or 0), reverse=ordering.startswith("-"))
    return grouped


def monthly_shop_ranking(month, search="", ordering="-sales", allowed_shops=None):
    """Aggregate a month by shop using the same metric domains as product ranking."""
    start, end = month_bounds(month)
    shops = list(_base_rows(start, end, allowed_shops=allowed_shops).order_by().values_list("shop", flat=True).distinct())
    rows = []
    for shop_name in shops:
        if search and search.lower() not in shop_name.lower():
            continue
        current = _totals_for_range(start, end, shop_name, allowed_shops)
        previous_start = previous_month(start)
        latest_month = available_months(shop_name, allowed_shops)[:1]
        last_data_date = _base_rows(start, end, shop_name, allowed_shops).aggregate(value=Max("date"))["value"]
        is_partial = bool(latest_month and month == latest_month[0] and last_data_date and last_data_date < end - timedelta(days=1))
        previous_end = previous_start + (last_data_date - start + timedelta(days=1)) if is_partial else start
        previous = _totals_for_range(previous_start, previous_end, shop_name, allowed_shops)
        profit = current["profit"]
        sales = current["sales"]
        rows.append({
            "id": shop_name,
            "month": month,
            "shop": shop_name,
            **current,
            "profit_rate": profit / sales if profit is not None and sales else None,
            "sales_change_rate": _delta(sales, previous["sales"]),
            "visitors_change_rate": _delta(current["visitors"], previous["visitors"]),
        })
    allowed = {"sales", "sales_volume", "orders", "visitors", "conversion_rate", "ad_cost", "roi", "profit", "profit_rate", "sales_change_rate"}
    key = ordering.lstrip("-") if ordering.lstrip("-") in allowed else "sales"
    rows.sort(key=lambda item: (item.get(key) is not None, item.get(key) or 0), reverse=ordering.startswith("-"))
    return rows


def dashboard_summary(day=None, shop=""):
    month = day.strftime("%Y-%m") if day else ""
    return monthly_dashboard(month, shop)

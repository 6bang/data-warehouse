from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.warehouse.models import DataSyncJob, MonthlyProductFact


GROUP_FIELDS = {
    "platform": ("platform",),
    "shop": ("platform", "shop"),
    "category": ("category_path",),
    "product": ("platform", "shop", "category_path", "product_id", "product_name", "product_image_url", "operator_name"),
    "operator": ("operator_name",),
}

ORDER_FIELDS = {"sales", "orders", "refund_amount", "ad_cost", "ad_revenue", "gross_profit", "net_profit", "products"}


def _number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _ratio(numerator, denominator):
    numerator = _number(numerator)
    denominator = _number(denominator)
    return round(numerator / denominator, 4) if numerator is not None and denominator else None


def business_queryset(params):
    queryset = MonthlyProductFact.objects.all()
    allowed_shops = params.get("_allowed_shops")
    if allowed_shops is not None:
        queryset = queryset.filter(shop__in=allowed_shops)
    for field in ("organization", "month", "platform", "shop", "category_path", "operator_name"):
        value = params.get(field)
        if value:
            queryset = queryset.filter(**{field: value})
    search = params.get("search")
    if search:
        queryset = queryset.filter(
            Q(product_id__icontains=search) | Q(product_name__icontains=search) |
            Q(category_path__icontains=search) | Q(shop__icontains=search)
        )
    return queryset


def business_dimensions(params):
    base = MonthlyProductFact.objects.all()
    allowed_shops = params.get("_allowed_shops")
    if allowed_shops is not None:
        base = base.filter(shop__in=allowed_shops)
    organizations = list(base.values_list("organization", flat=True).distinct().order_by("organization"))
    selected_org = params.get("organization") or (organizations[0] if organizations else "")
    scoped = base.filter(organization=selected_org) if selected_org else base.none()
    months = list(scoped.values_list("month", flat=True).distinct().order_by("-month"))
    selected_month = params.get("month") or (months[0] if months else "")
    month_scope = scoped.filter(month=selected_month) if selected_month else scoped.none()
    latest_sync = DataSyncJob.objects.filter(organization=selected_org, period=selected_month).first()
    source_labels = {
        "mcp_sync": "经营数据接口一键同步",
    }
    source_label = source_labels.get(latest_sync.source_system, "商品数据导入") if latest_sync else "尚未同步"
    is_mcp_sync = bool(latest_sync and latest_sync.source_system == "mcp_sync")
    return {
        "organizations": organizations,
        "selected": {"organization": selected_org, "month": selected_month},
        "months": months,
        "platforms": list(month_scope.values_list("platform", flat=True).distinct().order_by("platform")),
        "shops": list(month_scope.values_list("shop", flat=True).distinct().order_by("shop")),
        "categories": list(month_scope.values_list("category_path", flat=True).distinct().order_by("category_path")),
        "operators": list(month_scope.values_list("operator_name", flat=True).distinct().order_by("operator_name")),
        "coverage": {
            "available": [
                "sales", "orders", "refund_amount", "ad_cost", "ad_revenue", "gross_profit", "net_profit",
                *(["sales_volume", "visitors", "conversion_rate", "stock"] if is_mcp_sync else []),
            ],
            "unavailable": ["click_rate", *([] if is_mcp_sync else ["sales_volume", "visitors", "conversion_rate", "stock"])],
            "source": source_label,
        },
        "latest_sync": {
            "status": latest_sync.status,
            "rows": latest_sync.success_rows,
            "finished_at": latest_sync.finished_at,
            "source_name": latest_sync.source_name,
        } if latest_sync else None,
    }


def monthly_business(params):
    group_by = params.get("group_by", "platform")
    if group_by not in GROUP_FIELDS:
        raise ValueError("group_by 仅支持 platform/shop/category/product/operator")
    queryset = business_queryset(params)
    totals = queryset.aggregate(
        products=Count("product_id", distinct=True),
        sales=Sum("sales"), gross_sales=Sum("gross_sales"), net_sales=Sum("net_sales"),
        sales_volume=Sum("sales_volume"), orders=Sum("orders"), visitors=Sum("visitors"), stock=Sum("stock"),
        refund_amount=Sum("refund_amount"), ad_cost=Sum("ad_cost"),
        ad_revenue=Sum("ad_revenue"), gross_profit=Sum("gross_profit"), net_profit=Sum("net_profit"),
    )
    summary = {key: _number(value) for key, value in totals.items()}
    summary.update({
        "roi": _ratio(summary["ad_revenue"], summary["ad_cost"]),
        "refund_rate": _ratio(summary["refund_amount"], summary["sales"]),
        "gross_margin": _ratio(summary["gross_profit"], summary["sales"]),
        "net_margin": _ratio(summary["net_profit"], summary["net_sales"]),
    })

    fields = GROUP_FIELDS[group_by]
    rows = queryset.values(*fields).annotate(
        products=Count("product_id", distinct=True), sales=Sum("sales"), gross_sales=Sum("gross_sales"),
        net_sales=Sum("net_sales"), sales_volume=Sum("sales_volume"), orders=Sum("orders"),
        visitors=Sum("visitors"), stock=Sum("stock"), refund_amount=Sum("refund_amount"),
        ad_cost=Sum("ad_cost"), ad_revenue=Sum("ad_revenue"), gross_profit=Sum("gross_profit"),
        net_profit=Sum("net_profit"),
    )
    ordering = params.get("ordering", "-sales")
    raw_order = ordering.lstrip("-")
    rows = rows.order_by(ordering if raw_order in ORDER_FIELDS else "-sales")
    try:
        limit = min(max(int(params.get("limit", 300)), 1), 1000)
    except ValueError:
        limit = 300

    result = []
    for row in rows[:limit]:
        item = {key: _number(value) for key, value in row.items()}
        item.update({
            "roi": _ratio(item["ad_revenue"], item["ad_cost"]),
            "refund_rate": _ratio(item["refund_amount"], item["sales"]),
            "gross_margin": _ratio(item["gross_profit"], item["sales"]),
            "net_margin": _ratio(item["net_profit"], item["net_sales"]),
        })
        result.append(item)
    return {"group_by": group_by, "count": len(result), "summary": summary, "results": result}

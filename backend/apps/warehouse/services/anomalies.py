from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg

from apps.warehouse.models import AbnormalRecord, ProductData


def _rate(current, baseline):
    current, baseline = Decimal(current or 0), Decimal(baseline or 0)
    return (current - baseline) / baseline if baseline else Decimal("0")


def _level(change_rate):
    return AbnormalRecord.Level.CRITICAL if change_rate <= Decimal("-0.35") else AbnormalRecord.Level.WARNING


def _upsert(row, abnormal_type, metric, current, baseline, description, suggestion, level=None):
    change = _rate(current, baseline)
    reason = f"当前值 {current}，上一有效日 {baseline}，变化 {change:.1%}。"
    record, _ = AbnormalRecord.objects.update_or_create(
        date=row.date,
        shop=row.shop,
        product_id=row.product_id,
        type=abnormal_type,
        metric=metric,
        defaults={
            "product_data": row,
            "description": description,
            "level": level or _level(change),
            "current_value": current or 0,
            "baseline_value": baseline or 0,
            "change_rate": change,
            "ai_analysis": reason,
            "suggestion": suggestion,
            "status": AbnormalRecord.Status.OPEN,
        },
    )
    return record


def detect_anomalies(target_date, shop=""):
    queryset = ProductData.objects.filter(date=target_date)
    if shop:
        queryset = queryset.filter(shop=shop)
    shops = queryset.values_list("shop", flat=True).distinct()
    AbnormalRecord.objects.filter(date=target_date, shop__in=shops).update(status=AbnormalRecord.Status.RESOLVED)
    detected = []

    for row in queryset.iterator():
        previous = ProductData.objects.filter(shop=row.shop, product_id=row.product_id, date__lt=row.date).order_by("-date").first()
        if previous:
            comparisons = [
                ("sales", AbnormalRecord.Type.SALES, row.sales, previous.sales, "销售额", "检查流量入口、商品承接和价格活动，优先定位跌幅最大的渠道。"),
                ("visitors", AbnormalRecord.Type.TRAFFIC, row.visitors, previous.visitors, "访客", "检查自然搜索和广告展现/点击，优化低点击主图和关键词。"),
                ("conversion_rate", AbnormalRecord.Type.CONVERSION, row.conversion_rate, previous.conversion_rate, "转化率", "检查详情页、价格、评价和库存，逐项排除购买阻力。"),
            ]
            for metric, abnormal_type, current, baseline, label, suggestion in comparisons:
                change = _rate(current, baseline)
                if baseline and change <= Decimal("-0.20"):
                    detected.append(_upsert(
                        row, abnormal_type, metric, current, baseline,
                        f"{row.product_name or row.shop} {label}下降 {abs(change):.1%}", suggestion,
                    ))

            cost_change = _rate(row.ad_cost, previous.ad_cost)
            roi_change = _rate(row.roi, previous.roi)
            if previous.ad_cost and cost_change >= Decimal("0.25") and (row.roi < Decimal("1.5") or roi_change <= Decimal("-0.20")):
                detected.append(_upsert(
                    row, AbnormalRecord.Type.AD, "ad_cost_roi", row.roi, previous.roi,
                    f"{row.product_name} 广告花费上升 {cost_change:.1%}，ROI 为 {row.roi}",
                    "暂停高花费低成交单元，检查素材点击率、定向和落地页承接。",
                    AbnormalRecord.Level.CRITICAL if row.roi < 1 else AbnormalRecord.Level.WARNING,
                ))

        if row.stock is not None:
            avg_sales = ProductData.objects.filter(
                shop=row.shop, product_id=row.product_id,
                date__gte=row.date - timedelta(days=6), date__lte=row.date,
            ).aggregate(value=Avg("sales_volume"))["value"] or 0
            days_left = Decimal(row.stock) / Decimal(str(avg_sales)) if avg_sales else Decimal("999")
            if row.stock <= 10 or days_left < 7:
                detected.append(_upsert(
                    row, AbnormalRecord.Type.STOCK, "stock_days", days_left, Decimal("7"),
                    f"{row.product_name} 预计库存可售 {days_left:.1f} 天",
                    "确认在途库存和补货周期，避免广告放量后断货。",
                    AbnormalRecord.Level.CRITICAL if days_left < 3 else AbnormalRecord.Level.WARNING,
                ))
    return detected


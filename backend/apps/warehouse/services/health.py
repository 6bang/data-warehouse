from decimal import Decimal

from apps.warehouse.models import ProductData


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _growth_score(current, previous, neutral=60.0):
    current, previous = float(current or 0), float(previous or 0)
    if previous <= 0:
        return neutral if current <= 0 else 80.0
    growth = (current - previous) / previous
    return _clamp(60 + growth * 120)


def get_previous_row(row):
    return ProductData.objects.filter(
        shop=row.shop,
        product_id=row.product_id,
        date__lt=row.date,
    ).order_by("-date").first()


def calculate_health(row, previous=None):
    previous = previous or get_previous_row(row)
    sales_score = _growth_score(row.sales, previous.sales if previous else 0)
    traffic_score = _growth_score(row.visitors, previous.visitors if previous else 0)

    if previous and previous.conversion_rate:
        change = abs(float(row.conversion_rate - previous.conversion_rate) / float(previous.conversion_rate))
        conversion_score = _clamp(100 - change * 180)
    else:
        conversion_score = 70.0 if row.conversion_rate else 50.0

    if row.profit is None or not row.sales:
        profit_score = 60.0
        margin = None
    else:
        margin = float(Decimal(row.profit) / Decimal(row.sales))
        profit_score = _clamp(margin / 0.25 * 100)

    components = {
        "sales_growth": round(sales_score, 1),
        "traffic_growth": round(traffic_score, 1),
        "conversion_stability": round(conversion_score, 1),
        "profit_health": round(profit_score, 1),
    }
    total = sales_score * 0.35 + traffic_score * 0.25 + conversion_score * 0.20 + profit_score * 0.20
    return {"score": round(total, 1), "components": components, "profit_margin": margin}


"""Import a monthly product report that the user exported to a local Excel file.

File import only: this module never logs in to, or calls, any third-party service.
"""
import hashlib
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.warehouse.models import DataSyncJob, MonthlyProductFact
from apps.warehouse.services.product_catalog import sync_catalog_from_facts


REQUIRED_COLUMNS = {"商品ID", "平台类型", "店铺ID", "商品标题", "全类目名称", "成交金额", "成交笔数"}


def _missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)


def _text(value, fallback=""):
    if _missing(value):
        return fallback
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    result = str(value).strip()
    return fallback if result in {"-", "--", "—", "无", "未设置"} else result


def _decimal(value):
    if _missing(value) or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _integer(value):
    number = _decimal(value)
    return max(int(number or 0), 0)


def _datetime(value):
    if _missing(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    result = parsed.to_pydatetime()
    return timezone.make_aware(result, timezone.get_current_timezone()) if timezone.is_naive(result) else result


def _json_value(value):
    if _missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _file_checksum(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_monthly_product_export(file_path, organization, month, source_system="excel"):
    if not organization.strip():
        raise ValueError("organization 不能为空")
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month 必须使用 YYYY-MM 格式")

    path = Path(file_path)
    checksum = _file_checksum(path)
    frame = pd.read_excel(path, dtype={"商品ID": str, "店铺ID": str, "运营ID": str, "商品外部编码": str})
    missing_columns = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing_columns:
        raise ValueError(f"导出文件缺少必需字段：{', '.join(missing_columns)}")

    job = DataSyncJob.objects.create(
        organization=organization.strip(),
        source_system=source_system,
        period=month,
        source_name=path.name,
        source_checksum=checksum,
        total_rows=len(frame.index),
    )
    success_rows = 0
    errors = []
    try:
        with transaction.atomic():
            for index, row in frame.iterrows():
                product_id = _text(row.get("商品ID"))
                if not product_id:
                    errors.append({"row": int(index) + 2, "message": "商品ID为空"})
                    continue
                platform = _text(row.get("平台类型"), "未识别平台")
                shop = _text(row.get("店铺ID"), "未识别店铺")
                operator_id = _text(row.get("运营ID"))
                defaults = {
                    "shop_id": shop,
                    "category_path": _text(row.get("全类目名称"), "未分类"),
                    "product_name": _text(row.get("商品标题")),
                    "product_code": _text(row.get("商品外部编码")),
                    "product_image_url": _text(row.get("商品图片URL")),
                    "product_created_at": _datetime(row.get("商品创建时间")),
                    "operator_id": operator_id,
                    "operator_name": operator_id or "未分配运营",
                    "product_cost": _decimal(row.get("货品成本")),
                    "gross_sales": _decimal(row.get("毛销售额")),
                    "sales": _decimal(row.get("成交金额")) or Decimal("0.00"),
                    "net_sales": _decimal(row.get("净销售额")),
                    "orders": _integer(row.get("成交笔数")),
                    "refund_amount": _decimal(row.get("总退款金额")),
                    "ad_cost": _decimal(row.get("广告花费")),
                    "ad_revenue": _decimal(row.get("广告交易额")) or _decimal(row.get("广告直接交易额")),
                    "gross_profit": _decimal(row.get("毛利润")),
                    "net_profit": _decimal(row.get("净利润")),
                    "source": f"{source_system}_export",
                    "source_name": path.name,
                    "source_checksum": checksum,
                    "raw_payload": {str(key): _json_value(value) for key, value in row.items()},
                }
                MonthlyProductFact.objects.update_or_create(
                    organization=organization.strip(),
                    month=month,
                    platform=platform,
                    shop=shop,
                    product_id=product_id,
                    defaults=defaults,
                )
                success_rows += 1

        queryset = MonthlyProductFact.objects.filter(organization=organization.strip(), month=month)
        sync_catalog_from_facts(queryset, source=f"{source_system}_export")
        totals = queryset.aggregate(
            sales=Sum("sales"), orders=Sum("orders"), refunds=Sum("refund_amount"),
            ad_cost=Sum("ad_cost"), ad_revenue=Sum("ad_revenue"),
            gross_profit=Sum("gross_profit"), net_profit=Sum("net_profit"),
        )
        summary = {
            "products": queryset.count(),
            "platforms": queryset.values("platform").distinct().count(),
            "shops": queryset.values("shop").distinct().count(),
            "categories": queryset.values("category_path").distinct().count(),
            **{key: float(value or 0) for key, value in totals.items()},
        }
        job.status = DataSyncJob.Status.SUCCEEDED if not errors else DataSyncJob.Status.FAILED
        job.success_rows = success_rows
        job.failed_rows = len(errors)
        job.summary = {**summary, "row_errors": errors[:50]}
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "success_rows", "failed_rows", "summary", "finished_at", "updated_at"])
        return job
    except Exception as exc:
        job.status = DataSyncJob.Status.FAILED
        job.success_rows = success_rows
        job.failed_rows = max(len(frame.index) - success_rows, 0)
        job.error = str(exc)[:1000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "success_rows", "failed_rows", "error", "finished_at", "updated_at"])
        raise

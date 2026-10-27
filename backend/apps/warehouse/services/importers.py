import json
import math
import subprocess
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib import parse, request

import pandas as pd
from django.conf import settings
from django.db import transaction

from apps.warehouse.models import ImportBatch, ProductData
from apps.warehouse.services.integrations import get_feishu_integration, get_feishu_tenant_token


FIELD_ALIASES = {
    "date": ["date", "日期", "统计日期"],
    "shop": ["shop", "店铺", "店铺名称"],
    "product_id": ["product_id", "商品ID", "商品id", "主体ID"],
    "product_name": ["product_name", "商品名称", "主体名称"],
    "sales": ["sales", "销售额", "支付金额"],
    "sales_volume": ["sales_volume", "销量", "支付件数"],
    "orders": ["orders", "订单数", "支付买家数", "总成交笔数"],
    "visitors": ["visitors", "访客", "访客数", "商品访客数"],
    "page_views": ["page_views", "浏览量", "商品浏览量"],
    "impressions": ["impressions", "展现量"],
    "clicks": ["clicks", "点击量"],
    "click_rate": ["click_rate", "点击率"],
    "conversion_rate": ["conversion_rate", "转化率", "支付转化率", "商品支付转化率", "点击转化率"],
    "ad_cost": ["ad_cost", "广告费", "广告花费", "花费"],
    "ad_revenue": ["ad_revenue", "广告成交金额", "总成交金额"],
    "roi": ["roi", "ROI", "投入产出比"],
    "profit": ["profit", "利润", "毛利润"],
    "stock": ["stock", "库存"],
}


def _is_empty(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or value == ""


def _pick(row, field):
    for alias in FIELD_ALIASES[field]:
        if alias in row and not _is_empty(row[alias]):
            return row[alias]
    return None


def _decimal(value, default=Decimal("0")):
    if _is_empty(value):
        return default
    text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    try:
        result = Decimal(text)
        return result / Decimal("100") if percent else result
    except (InvalidOperation, ValueError):
        return default


def _integer(value, default=0):
    return max(0, int(_decimal(value, Decimal(default))))


def _date(value):
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.date()


def _json_safe(row):
    result = {}
    for key, value in row.items():
        if _is_empty(value):
            result[str(key)] = None
        elif isinstance(value, (pd.Timestamp, date)):
            result[str(key)] = value.isoformat()
        else:
            try:
                json.dumps(value)
                result[str(key)] = value
            except TypeError:
                result[str(key)] = str(value)
    return result


def normalize_row(row, data_type, default_shop):
    row = {str(k).strip(): v for k, v in row.items()}
    row_date = _pick(row, "date")
    if _is_empty(row_date):
        raise ValueError("缺少日期/统计日期")

    shop = str(_pick(row, "shop") or default_shop).strip()
    if data_type == "shop":
        product_id = "__SHOP_TOTAL__"
        product_name = "店铺每日汇总"
        record_type = ProductData.RecordType.SHOP_SUMMARY
    else:
        product_id = str(_pick(row, "product_id") or "").strip()
        if not product_id:
            raise ValueError("缺少商品ID/主体ID")
        product_name = str(_pick(row, "product_name") or product_id).strip()
        record_type = ProductData.RecordType.PRODUCT

    normalized = {
        "date": _date(row_date),
        "shop": shop,
        "product_id": product_id,
        "product_name": product_name,
        "record_type": record_type,
        "raw_payload": _json_safe(row),
    }
    numeric_fields = ["sales", "click_rate", "conversion_rate", "ad_cost", "ad_revenue", "roi", "profit"]
    integer_fields = ["sales_volume", "orders", "visitors", "page_views", "impressions", "clicks", "stock"]
    for field in numeric_fields:
        value = _pick(row, field)
        normalized[field] = None if field == "profit" and _is_empty(value) else _decimal(value)
    for field in integer_fields:
        value = _pick(row, field)
        normalized[field] = None if field == "stock" and _is_empty(value) else _integer(value)
    return normalized


@transaction.atomic
def import_rows(rows, batch):
    batch.status = ImportBatch.Status.PROCESSING
    batch.total_rows = len(rows)
    batch.save(update_fields=["status", "total_rows", "updated_at"])
    errors = []
    success = 0

    for index, raw_row in enumerate(rows, start=2):
        try:
            data = normalize_row(raw_row, batch.data_type, batch.shop)
            lookup = {key: data[key] for key in ("date", "shop", "product_id")}
            row, _ = ProductData.objects.get_or_create(**lookup, defaults={
                "product_name": data["product_name"],
                "record_type": data["record_type"],
            })
            if batch.data_type == "paid":
                update_fields = ["product_name", "impressions", "clicks", "click_rate", "conversion_rate", "ad_cost", "ad_revenue", "roi"]
            elif batch.data_type == "shop":
                update_fields = ["product_name", "record_type", "sales", "sales_volume", "orders", "visitors", "page_views", "conversion_rate"]
            else:
                update_fields = ["product_name", "record_type", "sales", "sales_volume", "orders", "visitors", "page_views", "conversion_rate", "profit", "stock"]
                for optional in ("impressions", "clicks", "click_rate", "ad_cost", "ad_revenue", "roi"):
                    if _pick(raw_row, optional) is not None:
                        update_fields.append(optional)
            for field in update_fields:
                setattr(row, field, data[field])
            row.source = batch.source
            row.import_batch = batch
            merged_payload = dict(row.raw_payload or {})
            merged_payload.update(data["raw_payload"])
            row.raw_payload = merged_payload
            row.save(update_fields=list(set(update_fields + ["source", "import_batch", "raw_payload", "updated_at"])))
            success += 1
        except Exception as exc:
            if len(errors) < 50:
                errors.append({"row": index, "message": str(exc)})

    batch.success_rows = success
    batch.failed_rows = len(rows) - success
    batch.error_summary = errors
    batch.status = ImportBatch.Status.SUCCEEDED if not batch.failed_rows else (ImportBatch.Status.PARTIAL if success else ImportBatch.Status.FAILED)
    batch.save(update_fields=["success_rows", "failed_rows", "error_summary", "status", "updated_at"])
    return batch


def rows_from_upload(upload):
    name = upload.name.lower()
    if name.endswith(".csv"):
        try:
            frame = pd.read_csv(upload, encoding="utf-8-sig")
        except UnicodeDecodeError:
            upload.seek(0)
            frame = pd.read_csv(upload, encoding="gb18030")
    elif name.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(upload)
    else:
        raise ValueError("仅支持 .xlsx、.xls、.csv")
    return frame.to_dict(orient="records")


class FeishuBaseAdapter:
    def _run(self, args):
        command = [settings.LARK_CLI_BIN, *args]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        output = completed.stdout or completed.stderr
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError(f"飞书 CLI 返回无法解析: {output[-500:]}") from exc
        if completed.returncode != 0 or payload.get("ok") is False:
            error = payload.get("error", {})
            raise ValueError(error.get("message") or "飞书 Base 读取失败")
        return payload

    def _resolve_url(self, url):
        parsed = parse.urlparse(url)
        parts = [item for item in parsed.path.split("/") if item]
        try:
            base_token = parts[parts.index("base") + 1]
        except (ValueError, IndexError) as exc:
            raise ValueError("无法识别飞书 Base 链接") from exc
        table_id = parse.parse_qs(parsed.query).get("table", [""])[0]
        if not base_token or not table_id.startswith("tbl"):
            raise ValueError("链接没有选中数据表，请提供带 table 参数的飞书 Base 链接")
        return base_token, table_id

    def _read_openapi(self, config, url, max_rows):
        base_token, table_id = self._resolve_url(url)
        token = get_feishu_tenant_token(config)
        rows, page_token, has_more = [], "", False
        while len(rows) < max_rows:
            query = {"page_size": "500"}
            if page_token:
                query["page_token"] = page_token
            endpoint = (
                f"https://open.feishu.cn/open-apis/bitable/v1/apps/{parse.quote(base_token)}/"
                f"tables/{parse.quote(table_id)}/records?{parse.urlencode(query)}"
            )
            req = request.Request(endpoint, headers={"Authorization": f"Bearer {token}"})
            with request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read())
            if payload.get("code") != 0:
                raise ValueError(payload.get("msg") or "飞书 Base 读取失败")
            data = payload.get("data", {})
            items = data.get("items", [])
            rows.extend(item.get("fields", {}) for item in items)
            has_more = bool(data.get("has_more"))
            page_token = data.get("page_token", "")
            if not has_more or not items:
                break
        if has_more and len(rows) >= max_rows:
            raise ValueError(f"单表记录超过 {max_rows} 行，请按月份或视图拆分后导入")
        return rows[:max_rows], {"base_token": base_token, "table_id": table_id, "adapter": "openapi"}

    def read(self, url, max_rows=50000):
        config = get_feishu_integration()
        if config and config.app_id and config.app_secret_encrypted:
            return self._read_openapi(config, url or config.default_base_url, max_rows)
        resolved = self._run(["base", "+url-resolve", "--url", url, "--as", "user"])
        data = resolved.get("data", {})
        base_token = data.get("base_token")
        table_id = data.get("table_id") or data.get("block_id")
        if not base_token or not str(table_id).startswith("tbl"):
            raise ValueError("链接没有选中数据表，请提供带 table 参数的飞书 Base 链接")

        rows, offset, has_more = [], 0, False
        while len(rows) < max_rows:
            page = self._run([
                "base", "+record-list", "--base-token", base_token, "--table-id", table_id,
                "--offset", str(offset), "--limit", "200", "--json", "--as", "user",
            ]).get("data", {})
            fields = page.get("fields", [])
            values = page.get("data", [])
            rows.extend(dict(zip(fields, row)) for row in values)
            has_more = bool(page.get("has_more"))
            if not has_more or not values:
                break
            offset += len(values)
        if has_more and len(rows) >= max_rows:
            raise ValueError(f"单表记录超过 {max_rows} 行，请按月份或视图拆分后导入")
        return rows[:max_rows], {"base_token": base_token, "table_id": table_id}

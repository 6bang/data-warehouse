from decimal import Decimal

import pytest

from apps.warehouse.models import ImportBatch, ProductData
from apps.warehouse.services.importers import import_rows, normalize_row


def test_normalize_feishu_product_row():
    row = normalize_row({
        "统计日期": "2026-08-01",
        "商品ID": "10001",
        "商品名称": "测试商品",
        "支付金额": "1,299.50",
        "支付件数": 3,
        "商品访客数": 100,
        "商品支付转化率": "3.00%",
    }, "product", "旗舰店")
    assert row["date"].isoformat() == "2026-08-01"
    assert row["sales"] == Decimal("1299.50")
    assert row["conversion_rate"] == Decimal("0.03")
    assert row["shop"] == "旗舰店"


@pytest.mark.django_db
def test_paid_import_merges_existing_product():
    ProductData.objects.create(date="2026-08-01", shop="旗舰店", product_id="10001", product_name="测试商品", sales=999)
    batch = ImportBatch.objects.create(source="feishu", data_type="paid", shop="旗舰店")
    import_rows([{
        "日期": "2026-08-01", "主体ID": "10001", "主体名称": "测试商品",
        "花费": 100, "总成交金额": 500, "投入产出比": 5, "点击率": 0.05,
    }], batch)
    row = ProductData.objects.get(product_id="10001")
    assert row.sales == Decimal("999")
    assert row.ad_cost == Decimal("100")
    assert row.roi == Decimal("5")
    assert ProductData.objects.count() == 1


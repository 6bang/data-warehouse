"""Independent acceptance tests for the 商品档案 lifecycle and plan workflow.

These tests intentionally exercise the public API rather than the implementation
helpers.  The business rule is that the creation date is day 1: days 1--35 are
new products and day 36 onward is a mature product.  Missing/future dates are
reported as unknown and can be filtered separately.
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Optional

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.warehouse.models import ProductCatalog


AS_OF = date(2026, 9, 19)


@pytest.fixture
def admin_client(monkeypatch):
    """Authenticated client with a deterministic application-local date."""

    monkeypatch.setattr(timezone, "localdate", lambda value=None: AS_OF if value is None else value.date())
    user = User.objects.create_superuser(
        username="catalog-lifecycle-admin",
        email="catalog-lifecycle@example.com",
        password="test-only-password",
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


def create_catalog(product_id: str, created_on: Optional[date]):
    created_at = None
    if created_on is not None:
        created_at = datetime.combine(created_on, datetime.min.time(), tzinfo=dt_timezone.utc)
    return ProductCatalog.objects.create(
        organization="验收组织",
        platform="淘宝",
        shop="验收店",
        product_id=product_id,
        product_name=f"验收商品-{product_id}",
        product_code=f"CODE-{product_id}",
        product_created_at=created_at,
    )


@pytest.mark.django_db
def test_catalog_api_exposes_day_one_35_36_and_unknown_lifecycle(admin_client):
    create_catalog("day-1", AS_OF)
    create_catalog("day-35", AS_OF - timedelta(days=34))
    create_catalog("day-36", AS_OF - timedelta(days=35))
    create_catalog("future", AS_OF + timedelta(days=1))
    create_catalog("missing", None)

    response = admin_client.get("/api/v1/product-catalog/?page_size=100")
    assert response.status_code == 200, response.data
    rows = {row["product_id"]: row for row in response.data["results"]}

    assert (rows["day-1"]["product_age_days"], rows["day-1"]["lifecycle"], rows["day-1"]["lifecycle_label"]) == (1, "new", "新品")
    assert (rows["day-35"]["product_age_days"], rows["day-35"]["lifecycle"]) == (35, "new")
    assert (rows["day-36"]["product_age_days"], rows["day-36"]["lifecycle"], rows["day-36"]["lifecycle_label"]) == (36, "mature", "老品")
    assert (rows["future"]["product_age_days"], rows["future"]["lifecycle"]) == (0, "unknown")
    assert (rows["missing"]["product_age_days"], rows["missing"]["lifecycle_label"]) == (None, "未知")


@pytest.mark.django_db
def test_catalog_api_filters_new_mature_and_unknown(admin_client):
    create_catalog("day-1", AS_OF)
    create_catalog("day-35", AS_OF - timedelta(days=34))
    create_catalog("day-36", AS_OF - timedelta(days=35))
    create_catalog("future", AS_OF + timedelta(days=1))
    create_catalog("missing", None)

    def ids(lifecycle):
        response = admin_client.get(f"/api/v1/product-catalog/?lifecycle={lifecycle}&page_size=100")
        assert response.status_code == 200, response.data
        return {row["product_id"] for row in response.data["results"]}

    assert ids("new") == {"day-1", "day-35"}
    assert ids("mature") == {"day-36"}
    assert ids("unknown") == {"future", "missing"}


@pytest.mark.django_db
def test_product_catalog_can_create_operation_plan(admin_client):
    create_catalog("plan-product", AS_OF - timedelta(days=3))
    payload = {
        "plan_name": "新品首周优化计划",
        "organization": "验收组织",
        "shop": "验收店",
        "product_id": "plan-product",
        "product_name": "验收商品-plan-product",
        "objective": "提升新品点击和转化",
        "actions": "完成主图测图与详情页优化",
        "start_date": str(AS_OF),
        "deadline": str(AS_OF + timedelta(days=7)),
    }
    response = admin_client.post("/api/v1/operation-plans/", payload, format="json")
    assert response.status_code == 201, response.data
    assert response.data["product_id"] == "plan-product"
    assert response.data["product_name"] == "验收商品-plan-product"
    assert response.data["status"] == "pending"

"""An empty or invisible dataset is valid input, including an explicit month."""
from datetime import date

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.warehouse.models import AbnormalRecord, AccessRole, AccountProfile, ProductData


def assert_empty_explicit_month(data):
    assert data["month"] == "2025-01"
    assert data["available_months"] == []
    assert data["is_partial"] is False
    assert data["data_through"] is None
    assert data["daily_trend"] == data["monthly_trend"] == data["abnormal"] == []
    assert data["abnormal_count"] == 0
    assert data["task_summary"] == {}
    for key in ["sales", "sales_volume", "orders", "visitors", "ad_cost", "conversion_rate", "roi"]:
        assert data["metrics"][key]["value"] == 0
        assert data["metrics"][key]["change_rate"] is None
    # No recorded profit stays unknown; do not invent a zero-profit fact.
    assert data["metrics"]["profit"]["value"] is None


@pytest.mark.django_db
def test_empty_database_explicit_month_is_successful_zero_statistics():
    user = User.objects.create_superuser("empty-dashboard-admin", password="Fixture-Only-729!")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/dashboard/?month=2025-01")
    assert response.status_code == 200
    assert_empty_explicit_month(response.data)


@pytest.mark.django_db
def test_empty_database_omitted_month_returns_existing_empty_contract():
    user = User.objects.create_superuser("empty-dashboard-admin", password="Fixture-Only-729!")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/dashboard/")
    assert response.status_code == 200
    assert response.data == {"month": None, "available_months": [], "metrics": {}, "monthly_trend": [], "daily_trend": [], "abnormal": [], "task_summary": {}}


@pytest.mark.django_db
@pytest.mark.parametrize("allowed_shops", [[], ["empty-authorized-shop"]])
def test_no_visible_rows_does_not_reveal_other_shops_months_metrics_or_alerts(allowed_shops):
    role = AccessRole.objects.create(name="测试看板角色", code="fixture-dashboard", data_scope=AccessRole.DataScope.ASSIGNED, permissions=["dashboard.view"])
    user = User.objects.create_user("empty-scoped-dashboard", password="Fixture-Only-729!")
    AccountProfile.objects.create(user=user, access_role=role, allowed_shops=allowed_shops, approval_status=AccountProfile.ApprovalStatus.APPROVED)
    ProductData.objects.create(date=date(2025, 1, 2), shop="hidden-shop", product_id="HIDDEN-FIXTURE", sales=987, visitors=123)
    AbnormalRecord.objects.create(date=date(2025, 1, 2), shop="hidden-shop", product_id="HIDDEN-FIXTURE", type=AbnormalRecord.Type.SALES, metric="sales", description="hidden-fixture-description")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/dashboard/?month=2025-01")
    assert response.status_code == 200
    assert_empty_explicit_month(response.data)
    assert "HIDDEN-FIXTURE" not in str(response.data)
    assert client.get("/api/v1/dashboard/").data["available_months"] == []
    assert client.get("/api/v1/dashboard/?month=2025-01&shop=hidden-shop").status_code == 403

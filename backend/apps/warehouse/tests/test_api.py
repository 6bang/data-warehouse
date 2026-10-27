import pytest
from datetime import date
from django.contrib.auth.models import User
from unittest.mock import patch
from rest_framework.test import APIClient

from apps.warehouse.models import AccountProfile, FeishuIntegration, OperationTask, ProductData
from apps.warehouse.services.secrets import encrypt_secret


@pytest.mark.django_db
def test_task_status_machine():
    user = User.objects.create_user("operator", password="secret")
    task = OperationTask.objects.create(task_name="优化主图", owner=user)
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(f"/api/v1/tasks/{task.id}/transition/", {"status": "completed", "result": "已替换"}, format="json")
    assert response.status_code == 400

    response = client.post(f"/api/v1/tasks/{task.id}/transition/", {"status": "in_progress"}, format="json")
    assert response.status_code == 200
    response = client.post(f"/api/v1/tasks/{task.id}/transition/", {"status": "completed", "result": "已替换"}, format="json")
    assert response.status_code == 200
    assert response.data["result"] == "已替换"


@pytest.mark.django_db
def test_registration_requires_admin_approval_before_login():
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {
            "username": "new_operator",
            "display_name": "新运营",
            "email": "operator@example.com",
            "password": "fixture-strong-pass-123",
            "password_confirm": "fixture-strong-pass-123",
        },
        format="json",
    )
    assert response.status_code == 201

    user = User.objects.get(username="new_operator")
    assert user.is_active is False
    assert user.profile.role == AccountProfile.Role.OPERATOR
    assert user.profile.approval_status == AccountProfile.ApprovalStatus.PENDING

    response = client.post(
        "/api/v1/auth/token/",
        {"username": "new_operator", "password": "fixture-strong-pass-123"},
        format="json",
    )
    assert response.status_code == 401
    assert "等待管理员审批" in response.data["error"]["detail"]

    admin = User.objects.create_superuser("reviewer", password="admin-pass-123")
    client.force_authenticate(admin)
    response = client.post(f"/api/v1/accounts/{user.id}/approve/", {"note": "资料确认"}, format="json")
    assert response.status_code == 200
    assert response.data["approval_status"] == "approved"

    user.refresh_from_db()
    assert user.is_active is True
    assert user.profile.reviewed_by == admin

    client.force_authenticate(user=None)
    response = client.post(
        "/api/v1/auth/token/",
        {"username": "new_operator", "password": "fixture-strong-pass-123"},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data


@pytest.mark.django_db
def test_feishu_login_is_tenant_scoped_and_requires_approval():
    FeishuIntegration.objects.create(
        name="飞书登录",
        app_id="cli_test",
        app_secret_encrypted=encrypt_secret("secret"),
        allowed_tenant_keys="tenant_company",
        enabled=True,
    )
    client = APIClient()
    session = client.session
    session["feishu_oauth_state"] = "state-1"
    session.save()
    with patch(
        "apps.warehouse.views.exchange_code",
        return_value={"open_id": "ou_user_1", "tenant_key": "tenant_company", "name": "飞书员工"},
    ):
        response = client.get("/api/v1/auth/feishu/callback/?code=code-1&state=state-1")
    assert response.status_code == 302
    user = User.objects.get(username="feishu_ou_user_1")
    assert user.is_active is False
    assert user.profile.approval_status == AccountProfile.ApprovalStatus.PENDING
    response = client.post("/api/v1/auth/feishu/exchange/", {}, format="json")
    assert response.status_code == 403

    session = client.session
    session["feishu_oauth_state"] = "state-2"
    session.save()
    with patch(
        "apps.warehouse.views.exchange_code",
        return_value={"open_id": "ou_external", "tenant_key": "tenant_external", "name": "外部用户"},
    ):
        response = client.get("/api/v1/auth/feishu/callback/?code=code-2&state=state-2")
    assert response.status_code == 302
    assert "tenant_denied" in response.url


@pytest.mark.django_db
def test_operator_cannot_review_accounts():
    operator = User.objects.create_user("operator-review", password="secret-pass")
    client = APIClient()
    client.force_authenticate(operator)
    response = client.get("/api/v1/accounts/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_monthly_shop_ranking_groups_real_rows():
    user = User.objects.create_user("shop-viewer", password="secret-pass")
    ProductData.objects.create(
        date=date(2026, 8, 1), shop="旗舰店", product_id="A1", product_name="商品A",
        sales=100, sales_volume=2, orders=2, visitors=20, ad_cost=10, ad_revenue=30, profit=40,
    )
    ProductData.objects.create(
        date=date(2026, 8, 2), shop="旗舰店", product_id="A1", product_name="商品A",
        sales=150, sales_volume=3, orders=3, visitors=30, ad_cost=20, ad_revenue=40, profit=50,
    )
    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/shops/monthly/?month=2026-08")
    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["shop"] == "旗舰店"
    assert row["sales"] == 250
    assert row["orders"] == 5
    assert round(float(row["roi"]), 2) == 2.33

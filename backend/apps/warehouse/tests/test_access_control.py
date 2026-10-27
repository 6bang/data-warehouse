from datetime import date

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.warehouse.models import AccessRole, AccountProfile, ProductData


@pytest.mark.django_db
def test_assigned_shop_role_filters_rows_and_blocks_ungranted_module():
    role = AccessRole.objects.create(
        name="华南店铺阅读者",
        code="south_viewer",
        data_scope=AccessRole.DataScope.ASSIGNED,
        permissions=["products.view"],
    )
    user = User.objects.create_user("scoped-user", password="secret-pass")
    AccountProfile.objects.create(
        user=user,
        access_role=role,
        allowed_shops=["深圳店"],
        approval_status=AccountProfile.ApprovalStatus.APPROVED,
    )
    ProductData.objects.create(date=date(2026, 8, 1), shop="深圳店", product_id="SZ-1", sales=100)
    ProductData.objects.create(date=date(2026, 8, 1), shop="上海店", product_id="SH-1", sales=200)

    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/products/?date=2026-08-01")
    assert response.status_code == 200
    assert [item["product_id"] for item in response.data["results"]] == ["SZ-1"]

    assert client.get("/api/v1/dashboard/").status_code == 403
    assert client.post("/api/v1/mcp/business/", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, format="json").status_code == 403


@pytest.mark.django_db
def test_admin_approval_assigns_role_and_shop_scope():
    role = AccessRole.objects.create(
        name="指定店铺编辑者",
        code="assigned_editor",
        data_scope=AccessRole.DataScope.ASSIGNED,
        permissions=["dashboard.view", "tasks.view", "tasks.edit"],
    )
    applicant = User.objects.create_user("applicant", password="secret-pass", is_active=False)
    AccountProfile.objects.create(
        user=applicant,
        requested_role_code="editor",
        approval_status=AccountProfile.ApprovalStatus.PENDING,
    )
    admin = User.objects.create_superuser("access-admin", password="admin-pass")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(
        f"/api/v1/accounts/{applicant.id}/approve/",
        {"access_role": role.id, "allowed_shops": ["深圳店"], "note": "负责华南店铺"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["role"] == "assigned_editor"
    assert response.data["allowed_shops"] == ["深圳店"]
    assert response.data["permission_codes"] == ["dashboard.view", "tasks.edit", "tasks.view"]

    applicant.refresh_from_db()
    assert applicant.is_active is True
    assert applicant.profile.access_role == role

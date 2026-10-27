"""Acceptance tests for scoped product-image synchronization.

These tests intentionally exercise the image-only path independently from the
upstream integrations: a bad URL or a missing source image must never alter
identity or sales facts.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.warehouse.models import (
    AccessRole,
    AccountProfile,
    MonthlyProductFact,
    ProductCatalog,
)
from apps.warehouse.services.product_images import (
    backfill_product_images,
    enrich_product_images,
    normalize_product_image_url,
    resolve_product_image,
)


def test_normalize_product_image_url_accepts_https_and_protocol_relative_only():
    assert normalize_product_image_url("  https://cdn.example.test/a.jpg  ") == "https://cdn.example.test/a.jpg"
    assert normalize_product_image_url("//cdn.example.test/a.jpg") == "https://cdn.example.test/a.jpg"
    for value in (
        "javascript:alert(1)",
        "data:image/png;base64,abc",
        "ftp://cdn.example.test/a.jpg",
        "https:///missing-host.jpg",
        "https://user:password@cdn.example.test/a.jpg",
        "https://cdn.example.test/a bad.jpg",
        None,
        123,
    ):
        assert normalize_product_image_url(value) == ""


def test_resolve_product_image_reads_known_attachment_fields_but_not_arbitrary_urls():
    assert resolve_product_image({"pic_url": "https://cdn.example.test/a.jpg"}) == "https://cdn.example.test/a.jpg"
    assert resolve_product_image({"attachments": [{"download_url": "https://cdn.example.test/b.jpg"}]}) == "https://cdn.example.test/b.jpg"
    assert resolve_product_image({"description": "https://cdn.example.test/not-an-image.jpg"}) == ""
    assert resolve_product_image({"raw_payload": {"商品图片URL": "https://cdn.example.test/c.jpg"}}) == "https://cdn.example.test/c.jpg"


@pytest.mark.django_db
def test_enrich_uses_exact_four_part_identity_and_does_not_overwrite_existing_image():
    MonthlyProductFact.objects.create(
        organization="Org-A", month="2026-07", platform="淘宝", shop="Shop-A", product_id="same",
        product_image_url="https://cdn.example.test/a.jpg", sales=Decimal("321"),
    )
    MonthlyProductFact.objects.create(
        organization="Org-A", month="2026-08", platform="京东", shop="Shop-A", product_id="same",
        product_image_url="https://cdn.example.test/jd.jpg", sales=Decimal("654"),
    )
    MonthlyProductFact.objects.create(
        organization="Org-B", month="2026-09", platform="淘宝", shop="Shop-A", product_id="same",
        product_image_url="https://cdn.example.test/other-org.jpg", sales=Decimal("999"),
    )
    rows = [
        {"organization": "Org-A", "platform": "淘宝", "shop": "Shop-A", "product_id": "same", "product_image_url": ""},
        {"organization": "Org-A", "platform": "京东", "shop": "Shop-A", "product_id": "same", "product_image_url": ""},
        {"organization": "Org-A", "platform": "淘宝", "shop": "Shop-B", "product_id": "same", "product_image_url": ""},
        {"organization": "Org-A", "platform": "淘宝", "shop": "Shop-A", "product_id": "same", "product_image_url": "https://cdn.example.test/already.jpg"},
        {"organization": "", "platform": "淘宝", "shop": "Shop-A", "product_id": "same", "product_image_url": ""},
    ]
    enrich_product_images(rows)
    assert rows[0]["product_image_url"] == "https://cdn.example.test/a.jpg"
    assert rows[1]["product_image_url"] == "https://cdn.example.test/jd.jpg"
    assert rows[2]["product_image_url"] == ""
    assert rows[3]["product_image_url"] == "https://cdn.example.test/already.jpg"
    assert rows[4]["product_image_url"] == ""


@pytest.mark.django_db
def test_enrich_prefers_newest_valid_month_and_does_not_touch_metrics():
    MonthlyProductFact.objects.create(
        organization="Org", month="2026-06", platform="淘宝", shop="Shop", product_id="p",
        product_image_url="https://cdn.example.test/old.jpg", sales=Decimal("10"), orders=2,
    )
    MonthlyProductFact.objects.create(
        organization="Org", month="2026-08", platform="淘宝", shop="Shop", product_id="p",
        product_image_url="", sales=Decimal("20"), orders=3,
    )
    MonthlyProductFact.objects.create(
        organization="Org", month="2026-07", platform="淘宝", shop="Shop", product_id="p",
        product_image_url="https://cdn.example.test/mid.jpg", sales=Decimal("30"), orders=4,
    )
    row = {"organization": "Org", "platform": "淘宝", "shop": "Shop", "product_id": "p", "product_image_url": ""}
    before = list(MonthlyProductFact.objects.values_list("sales", "orders"))
    enrich_product_images([row])
    assert row["product_image_url"] == "https://cdn.example.test/mid.jpg"
    assert list(MonthlyProductFact.objects.values_list("sales", "orders")) == before


@pytest.mark.django_db
def test_backfill_and_command_are_image_only_idempotent_and_dry_run_is_read_only(capsys):
    fact = MonthlyProductFact.objects.create(
        organization="Org", month="2026-08", platform="淘宝", shop="Shop", product_id="p",
        product_image_url="", sales=Decimal("123.45"), orders=7, gross_profit=Decimal("8.25"),
    )
    ProductCatalog.objects.create(
        organization="Org", platform="淘宝", shop="Shop", product_id="p",
        product_image_url="https://cdn.example.test/master.jpg",
    )
    preview = backfill_product_images(organization="Org", dry_run=True)
    fact.refresh_from_db()
    assert preview["updated"] >= 1
    assert fact.product_image_url == ""
    assert fact.sales == Decimal("123.45") and fact.orders == 7 and fact.gross_profit == Decimal("8.25")

    call_command("sync_product_images", "--organization", "Org")
    fact.refresh_from_db()
    assert fact.product_image_url == "https://cdn.example.test/master.jpg"
    metrics = (fact.sales, fact.orders, fact.gross_profit)
    call_command("sync_product_images", "--organization", "Org")
    fact.refresh_from_db()
    assert (fact.sales, fact.orders, fact.gross_profit) == metrics
    assert "商品图片同步" in capsys.readouterr().out


@pytest.mark.django_db
def test_product_catalog_api_is_paginated_and_shop_scoped():
    role = AccessRole.objects.create(
        name="指定店铺", code="assigned-images", data_scope=AccessRole.DataScope.ASSIGNED, permissions=["products.view"]
    )
    user = User.objects.create_user("image-reader", password="secret")
    AccountProfile.objects.create(
        user=user, access_role=role, allowed_shops=["Shop-A"], approval_status=AccountProfile.ApprovalStatus.APPROVED
    )
    ProductCatalog.objects.create(
        organization="Org", platform="淘宝", shop="Shop-A", product_id="A",
        product_name="A", product_image_url="https://cdn.example.test/a.jpg",
    )
    ProductCatalog.objects.create(
        organization="Org", platform="淘宝", shop="Shop-B", product_id="B",
        product_name="B", product_image_url="https://cdn.example.test/b.jpg",
    )
    client = APIClient(); client.force_authenticate(user)
    response = client.get("/api/v1/product-catalog/?organization=Org&page_size=1")
    assert response.status_code == 200
    assert {key for key in ("count", "results") if key in response.data} == {"count", "results"}
    assert response.data["count"] == 1
    assert response.data["results"][0]["product_image_url"] == "https://cdn.example.test/a.jpg"
    assert client.get("/api/v1/product-catalog/?organization=Other").data["count"] == 0


@pytest.mark.django_db
def test_command_rejects_unknown_config_without_writing():
    with pytest.raises(CommandError):
        call_command("sync_product_images", "--config-id", "999999")

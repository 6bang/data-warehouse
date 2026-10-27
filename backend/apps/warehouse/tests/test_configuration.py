import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.warehouse.models import AIProviderConfig, FeishuIntegration, MCPServerConfig
from apps.warehouse.services.ai import run_analysis
from apps.warehouse.services.secrets import decrypt_secret, encrypt_secret


@pytest.mark.django_db
def test_secret_encryption_round_trip():
    encrypted = encrypt_secret("super-secret-value")
    assert encrypted != "super-secret-value"
    assert "super-secret-value" not in encrypted
    assert decrypt_secret(encrypted) == "super-secret-value"


@pytest.mark.django_db
def test_admin_can_save_feishu_secret_without_api_leak():
    admin = User.objects.create_superuser("config-admin", password="secret-pass")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.post(
        "/api/v1/configuration/feishu/",
        {
            "name": "飞书",
            "app_id": "cli_test",
            "app_secret": "fixture-feishu-secret",
            "default_base_url": "https://example.feishu.cn/base/token?table=tbl123",
            "enabled": True,
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["has_app_secret"] is True
    assert "app_secret" not in response.data
    assert "app_secret_encrypted" not in response.data
    config = FeishuIntegration.objects.get()
    assert config.app_secret_encrypted != "fixture-feishu-secret"
    assert decrypt_secret(config.app_secret_encrypted) == "fixture-feishu-secret"


@pytest.mark.django_db
def test_third_party_account_password_connector_is_not_shipped():
    admin = User.objects.create_superuser("source-admin", password="secret-pass")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.post(
        "/api/v1/configuration/chachazhan/",
        {"name": "测试数据源", "login_identifier": "demo-user", "password": "secret-pass"},
        format="json",
    )
    assert response.status_code == 404
    summary = client.get("/api/v1/configuration/summary/")
    assert summary.status_code == 200
    assert "chachazhan" not in summary.data
    from apps.warehouse import models
    assert not hasattr(models, "ChachazhanIntegration")


@pytest.mark.django_db
def test_only_one_default_ai_provider_and_agent_reads_database_config():
    admin = User.objects.create_superuser("ai-admin", password="secret-pass")
    client = APIClient()
    client.force_authenticate(admin)
    with patch("apps.warehouse.serializers.validate_outbound_url", side_effect=lambda value, **_: value):
        first = client.post(
            "/api/v1/configuration/ai-providers/",
            {"name": "模型A", "provider": "custom", "api_base_url": "https://model-a.example/v1", "model": "model-a", "api_key": "key-a", "enabled": True, "is_default": True},
            format="json",
        )
        second = client.post(
            "/api/v1/configuration/ai-providers/",
            {"name": "模型B", "provider": "deepseek", "api_base_url": "https://model-b.example/v1", "model": "model-b", "api_key": "key-b", "enabled": True, "is_default": True},
            format="json",
        )
    assert first.status_code == 201
    assert second.status_code == 201
    assert AIProviderConfig.objects.get(name="模型A").is_default is False
    assert AIProviderConfig.objects.get(name="模型B").is_default is True
    assert "api_key" not in second.data and "api_key_encrypted" not in second.data

    model_payload = {
        "choices": [{"message": {"role": "assistant", "content": json.dumps({"problems": [], "reasons": [], "suggestions": ["继续观察"], "actions": []})}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
    }
    response_mock = MagicMock()
    response_mock.__enter__.return_value.read.return_value = json.dumps(model_payload).encode()
    with patch("apps.warehouse.services.ai.request.urlopen", return_value=response_mock) as urlopen:
        run = run_analysis(admin, question="测试数据库模型配置")
    assert run.provider == "openai_compatible"
    assert run.model == "model-b"
    assert run.prompt_tokens == 12
    assert urlopen.call_args.args[0].full_url == "https://model-b.example/v1/chat/completions"


@pytest.mark.django_db
def test_mcp_requires_explicit_tool_allowlist_for_agent():
    admin = User.objects.create_superuser("mcp-admin", password="secret-pass")
    client = APIClient()
    client.force_authenticate(admin)
    payload = {
        "name": "查询服务",
        "endpoint_url": "https://mcp.example/mcp",
        "auth_type": "none",
        "enabled": True,
        "agent_query_enabled": True,
        "allowed_tools": [],
        "protocol_version": "2025-06-18",
    }
    with patch("apps.warehouse.serializers.validate_outbound_url", side_effect=lambda value, **_: value):
        response = client.post("/api/v1/configuration/mcp-servers/", payload, format="json")
    assert response.status_code == 400
    assert MCPServerConfig.objects.count() == 0


@pytest.mark.django_db
def test_operator_cannot_access_configuration():
    operator = User.objects.create_user("config-operator", password="secret-pass")
    client = APIClient()
    client.force_authenticate(operator)
    assert client.get("/api/v1/configuration/summary/").status_code == 403

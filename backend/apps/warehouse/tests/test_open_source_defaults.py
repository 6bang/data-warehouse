"""Offline security regressions for the distributable application's defaults."""
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.warehouse.models import AccountProfile, FeishuIntegration, AIProviderConfig, MCPServerConfig
from apps.warehouse.services.integrations import validate_outbound_url
from apps.warehouse.services.secrets import decrypt_secret, encrypt_secret


@pytest.mark.django_db
def test_bootstrap_missing_password_creates_nothing(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "fixture-bootstrap")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    output = StringIO()
    call_command("bootstrap_admin", stdout=output)
    assert "Skipped" in output.getvalue()
    assert not User.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("password", ["short", "12345678901234567890", "password1234"])
def test_bootstrap_rejects_weak_password_without_creating_account(monkeypatch, password):
    monkeypatch.setenv("ADMIN_USERNAME", "fixture-bootstrap")
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    with pytest.raises(CommandError):
        call_command("bootstrap_admin")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_bootstrap_creates_strong_admin_without_logging_password(monkeypatch):
    password = "Fixture!Password-With-Entropy-729"
    monkeypatch.setenv("ADMIN_USERNAME", "fixture-bootstrap")
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    output = StringIO()
    call_command("bootstrap_admin", stdout=output)
    user = User.objects.get(username="fixture-bootstrap")
    assert user.is_staff and user.is_superuser and user.check_password(password)
    profile = AccountProfile.objects.get(user=user)
    assert profile.approval_status == AccountProfile.ApprovalStatus.APPROVED
    assert profile.role == AccountProfile.Role.ADMIN
    assert password not in output.getvalue()


@pytest.mark.django_db
def test_bootstrap_never_resets_existing_admin_or_promotes_existing_user(monkeypatch):
    admin = User.objects.create_superuser("fixture-existing", password="Fixture!Original-729")
    before = admin.password
    monkeypatch.setenv("ADMIN_USERNAME", admin.username)
    monkeypatch.setenv("ADMIN_PASSWORD", "Fixture!Replacement-729")
    monkeypatch.setenv("ADMIN_RESET_PASSWORD", "1")
    call_command("bootstrap_admin", stdout=StringIO())
    admin.refresh_from_db()
    assert admin.password == before
    ordinary = User.objects.create_user("fixture-ordinary", password="Fixture!Original-729")
    monkeypatch.setenv("ADMIN_USERNAME", ordinary.username)
    with pytest.raises(CommandError):
        call_command("bootstrap_admin")
    ordinary.refresh_from_db()
    assert not ordinary.is_staff and not ordinary.is_superuser


@pytest.mark.django_db
def test_bootstrap_rejects_empty_username(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "  ")
    with pytest.raises(CommandError):
        call_command("bootstrap_admin")
    assert not User.objects.exists()


def test_integration_encryption_requires_explicit_valid_key(settings):
    for key in ["", "fixture-not-a-valid-fernet-key"]:
        settings.INTEGRATION_ENCRYPTION_KEY = key
        with pytest.raises(ValueError):
            encrypt_secret("fixture-value")
    settings.INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()
    cipher = encrypt_secret("fixture-value")
    assert decrypt_secret(cipher) == "fixture-value"
    settings.INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()
    with pytest.raises(ValueError):
        decrypt_secret(cipher)


@pytest.mark.django_db
def test_missing_encryption_key_is_api_error_without_partial_configuration(settings):
    settings.INTEGRATION_ENCRYPTION_KEY = ""
    admin = User.objects.create_superuser("fixture-admin", password="Fixture-Only-Password-729!")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.post("/api/v1/configuration/feishu/", {"name": "测试连接", "app_id": "fixture-app", "app_secret": "fixture-secret"}, format="json")
    assert response.status_code == 400
    assert not FeishuIntegration.objects.exists()
    assert "fixture-secret" not in str(response.data)


def test_new_optional_integrations_are_disabled_and_have_no_default_endpoints():
    for config in [AIProviderConfig(), MCPServerConfig()]:
        assert config.enabled is False
    assert AIProviderConfig().api_base_url == ""
    assert MCPServerConfig().endpoint_url == ""


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_outbound_connections_reject_private_dns_answers(address):
    with patch("apps.warehouse.services.integrations.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 443))]):
        with pytest.raises(ValueError):
            validate_outbound_url("https://source.example.invalid/api")


def test_outbound_connections_accept_explicit_public_endpoint_but_reject_userinfo():
    with patch("apps.warehouse.services.integrations.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        assert validate_outbound_url("https://source.example.invalid/api") == "https://source.example.invalid/api"
        with pytest.raises(ValueError):
            validate_outbound_url("https://user:fixture@source.example.invalid/api")


def settings_process(extra):
    environment = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1", **extra}
    return subprocess.run(
        [sys.executable, "-c", "import config.settings as s; print(s.DATABASES['default']['ENGINE']); print(s.ALLOWED_HOSTS); print(bool(s.AI_API_BASE_URL or s.FEISHU_OAUTH_REDIRECT_URI or s.FEISHU_ALLOWED_TENANT_KEYS))"],
        cwd=Path(__file__).resolve().parents[3], env=environment, capture_output=True, text=True, check=False,
    )


def test_settings_defaults_are_local_and_unconnected():
    result = settings_process({})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["django.db.backends.sqlite3", "['localhost', '127.0.0.1', '[::1]']", "False"]


@pytest.mark.parametrize("extra", [
    {"DJANGO_DEBUG": "0"},
    {"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "x" * 60, "DJANGO_ALLOWED_HOSTS": "localhost"},
    {"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "Fixture-Only-Strong-Signing-Key-" * 3, "DJANGO_ALLOWED_HOSTS": "*"},
])
def test_production_settings_refuse_unsafe_defaults(extra):
    result = settings_process(extra)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


def test_production_settings_accept_explicit_safe_configuration():
    result = settings_process({"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "Fixture-Only-Strong-Signing-Key-" * 3, "DJANGO_ALLOWED_HOSTS": "localhost"})
    assert result.returncode == 0, result.stderr

import ipaddress
import json
import socket
import time
from urllib import error, parse, request

from django.utils import timezone

from apps.warehouse.models import AIProviderConfig, ConnectionStatus, FeishuIntegration, IntegrationEventLog
from apps.warehouse.services.secrets import decrypt_secret


def record_integration_event(integration_type, config, action, *, actor=None, success=True, started_at=None, detail=None, error_message="", ai_run=None):
    duration_ms = max(0, int((time.monotonic() - started_at) * 1000)) if started_at else 0
    return IntegrationEventLog.objects.create(
        integration_type=integration_type,
        integration_id=getattr(config, "id", None),
        action=action,
        actor=actor,
        ai_analysis_run=ai_run,
        success=success,
        duration_ms=duration_ms,
        detail=detail or {},
        error=error_message[:500],
    )


def validate_outbound_url(value, *, allow_private=False):
    parsed = parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("连接地址必须是有效的 HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("连接地址不能包含用户名或密码")
    if parsed.scheme != "https" and not allow_private:
        raise ValueError("公网连接必须使用 HTTPS")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("连接地址无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        restricted = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        if restricted and not allow_private:
            raise ValueError("连接地址指向内网或受限地址；如确需连接，请显式允许内网")
    return value


def _json_request(url, *, payload=None, headers=None, timeout=20):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"远端接口返回 HTTP {exc.code}: {body}") from exc


def get_feishu_integration():
    return FeishuIntegration.objects.filter(enabled=True).order_by("id").first()


def get_feishu_tenant_token(config):
    secret = decrypt_secret(config.app_secret_encrypted)
    if not config.app_id or not secret:
        raise ValueError("请先填写飞书 App ID 和 App Secret")
    payload = _json_request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
        payload={"app_id": config.app_id, "app_secret": secret},
    )
    if payload.get("code") != 0 or not payload.get("tenant_access_token"):
        raise ValueError(payload.get("msg") or "飞书凭据验证失败")
    return payload["tenant_access_token"]


def test_feishu_connection(config, actor=None):
    started_at = time.monotonic()
    try:
        get_feishu_tenant_token(config)
        config.connection_status = ConnectionStatus.CONNECTED
        config.last_error = ""
        success, message = True, "飞书应用连接成功"
    except Exception as exc:
        config.connection_status = ConnectionStatus.ERROR
        config.last_error = str(exc)[:500]
        success, message = False, str(exc)
    config.last_tested_at = timezone.now()
    config.save(update_fields=["connection_status", "last_error", "last_tested_at", "updated_at"])
    record_integration_event("feishu", config, "test", actor=actor, success=success, started_at=started_at, error_message="" if success else message)
    return success, message


def get_active_ai_provider():
    return AIProviderConfig.objects.filter(enabled=True, is_default=True).first() or AIProviderConfig.objects.filter(enabled=True).first()


def ai_provider_credentials(config=None):
    config = config or get_active_ai_provider()
    if not config:
        return None
    return {
        "config": config,
        "base_url": config.api_base_url.rstrip("/"),
        "api_key": decrypt_secret(config.api_key_encrypted),
        "model": config.model,
        "provider": config.provider,
    }


def test_ai_connection(config, actor=None):
    started_at = time.monotonic()
    try:
        validate_outbound_url(config.api_base_url)
        credentials = ai_provider_credentials(config)
        if not credentials["api_key"]:
            raise ValueError("请先填写 API Key")
        payload = _json_request(
            credentials["base_url"] + "/chat/completions",
            payload={
                "model": credentials["model"],
                "messages": [{"role": "user", "content": "只回复 OK"}],
                "max_tokens": 8,
                "stream": False,
            },
            headers={"Authorization": f"Bearer {credentials['api_key']}"},
            timeout=30,
        )
        if not payload.get("choices"):
            raise ValueError("模型接口未返回 choices")
        config.connection_status = ConnectionStatus.CONNECTED
        config.last_error = ""
        success, message = True, "模型连接成功"
    except Exception as exc:
        config.connection_status = ConnectionStatus.ERROR
        config.last_error = str(exc)[:500]
        success, message = False, str(exc)
    config.last_tested_at = timezone.now()
    config.save(update_fields=["connection_status", "last_error", "last_tested_at", "updated_at"])
    record_integration_event("ai", config, "test", actor=actor, success=success, started_at=started_at, detail={"model": config.model}, error_message="" if success else message)
    return success, message

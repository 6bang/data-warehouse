import secrets
from urllib.parse import urlencode

from django.conf import settings

from apps.warehouse.services.integrations import _json_request, get_feishu_integration
from apps.warehouse.services.secrets import decrypt_secret


FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def oauth_redirect_uri(request):
    configured = getattr(settings, "FEISHU_OAUTH_REDIRECT_URI", "")
    if configured:
        return configured
    return request.build_absolute_uri("/api/v1/auth/feishu/callback/")


def new_state():
    return secrets.token_urlsafe(32)


def authorization_url(config, redirect_uri, state):
    scopes = getattr(settings, "FEISHU_OAUTH_SCOPES", "")
    params = {
        "client_id": config.app_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if scopes:
        params["scope"] = scopes
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(config, code, redirect_uri):
    secret = decrypt_secret(config.app_secret_encrypted)
    if not config.app_id or not secret:
        raise ValueError("飞书应用尚未配置 App ID 或 App Secret")
    token_payload = _json_request(
        FEISHU_TOKEN_URL,
        payload={
            "grant_type": "authorization_code",
            "client_id": config.app_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=20,
    )
    if token_payload.get("code") not in (None, 0) or not token_payload.get("access_token"):
        raise ValueError(token_payload.get("msg") or "飞书授权码换取访问令牌失败")
    user_payload = _json_request(
        FEISHU_USER_INFO_URL,
        headers={"Authorization": f"Bearer {token_payload['access_token']}"},
        timeout=20,
    )
    if user_payload.get("code") != 0:
        raise ValueError(user_payload.get("msg") or "无法获取飞书用户信息")
    return user_payload.get("data") or {}


def allowed_tenant_keys(config=None):
    raw = getattr(config, "allowed_tenant_keys", "") or getattr(settings, "FEISHU_ALLOWED_TENANT_KEYS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def ensure_allowed_tenant(user_info, config=None):
    tenant_key = str(user_info.get("tenant_key") or "").strip()
    allowed = allowed_tenant_keys(config)
    if not allowed:
        raise ValueError("系统尚未配置允许登录的飞书企业租户，请联系管理员")
    if not tenant_key or tenant_key not in allowed:
        raise PermissionError("该飞书账号不属于允许登录的企业")
    return tenant_key


def display_name(user_info):
    return str(user_info.get("name") or user_info.get("en_name") or "飞书用户").strip()[:150]

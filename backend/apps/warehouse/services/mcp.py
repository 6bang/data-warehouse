import json
import hashlib
import re
import secrets
import time
from urllib import error, request

from django.utils import timezone

from apps.warehouse.models import ConnectionStatus, MCPAccessToken, MCPServerConfig
from apps.warehouse.services.integrations import record_integration_event, validate_outbound_url
from apps.warehouse.services.secrets import decrypt_secret


BUSINESS_MCP_TOOL_NAMES = {"list_business_dimensions", "query_monthly_metrics", "query_realtime_metrics"}
MCP_PERMISSION_CATALOG = [
    {"group": "data", "label": "数据权限", "items": [
        {"code": "realtime.view", "label": "查看实时经营数据"},
        {"code": "monthly.view", "label": "查看月度经营数据"},
        {"code": "dimensions.view", "label": "查看组织与数据维度"},
    ]},
    {"group": "automation", "label": "自动化权限", "items": [
        {"code": "analysis.run", "label": "发起 AI 分析"},
        {"code": "tasks.create", "label": "创建运营任务"},
        {"code": "sync.request", "label": "请求数据刷新"},
    ]},
    {"group": "other", "label": "其他功能权限", "items": [
        {"code": "export.data", "label": "导出经营数据"},
    ]},
]
MCP_PERMISSION_CODES = {item["code"] for group in MCP_PERMISSION_CATALOG for item in group["items"]}
MCP_TOOL_PERMISSION_MAP = {
    "query_realtime_metrics": "realtime.view",
    "query_monthly_metrics": "monthly.view",
    "list_business_dimensions": "dimensions.view",
}


def generate_mcp_access_token():
    raw = f"mcp_{secrets.token_urlsafe(32)}"
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw[:16]


def get_mcp_access_token(raw_token):
    if not raw_token or not raw_token.startswith("mcp_"):
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = MCPAccessToken.objects.select_related("owner", "owner__profile").filter(
        token_hash=token_hash, enabled=True, approval_status=MCPAccessToken.ApprovalStatus.APPROVED,
    ).first()
    if not token or (token.expires_at and token.expires_at <= timezone.now()):
        return None
    MCPAccessToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    return token


def _response_payload(response):
    raw = response.read().decode("utf-8")
    content_type = response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type:
        data_lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
        if not data_lines:
            return {}
        return json.loads(data_lines[-1])
    return json.loads(raw) if raw else {}


def tool_result_json(result):
    """Return structured JSON from either MCP structuredContent or text content."""
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    if isinstance(structured, dict):
        return structured
    for item in result.get("content", []) if isinstance(result, dict) else []:
        if item.get("type") != "text" or not item.get("text"):
            continue
        try:
            payload = json.loads(item["text"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("MCP 工具未返回可解析的结构化数据")


class MCPHttpClient:
    def __init__(self, config):
        self.config = config
        self.session_id = ""
        self.request_id = 0

    def _headers(self, method, name=""):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.config.protocol_version,
            "Mcp-Method": method,
        }
        if name:
            headers["Mcp-Name"] = name
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        if self.config.auth_type == MCPServerConfig.AuthType.BEARER:
            token = decrypt_secret(self.config.auth_token_encrypted)
            if token:
                token = token.strip()
                if token.lower().startswith("bearer "):
                    token = token[7:].strip()
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _post(self, method, params=None, *, notification=False):
        validate_outbound_url(self.config.endpoint_url, allow_private=self.config.allow_private_network)
        self.request_id += 1
        body = {"jsonrpc": "2.0", "method": method}
        if not notification:
            body["id"] = self.request_id
        if params is not None:
            body["params"] = params
        name = params.get("name", "") if isinstance(params, dict) else ""
        req = request.Request(
            self.config.endpoint_url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(method, name),
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                if response.headers.get("MCP-Session-Id"):
                    self.session_id = response.headers["MCP-Session-Id"]
                if notification and response.status in {202, 204}:
                    return {}
                payload = _response_payload(response)
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
            raise ValueError(f"MCP 返回 HTTP {exc.code}: {body_text}") from exc
        if payload.get("error"):
            raise ValueError(payload["error"].get("message", "MCP 请求失败"))
        return payload.get("result", {})

    def initialize(self):
        result = self._post("initialize", {
            "protocolVersion": self.config.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "commerce-warehouse-agent", "version": "0.2.0"},
        })
        self._post("notifications/initialized", notification=True)
        return result

    def list_tools(self):
        self.initialize()
        return self._post("tools/list", {}).get("tools", [])

    def call_tool(self, name, arguments):
        self.initialize()
        return self._post("tools/call", {"name": name, "arguments": arguments or {}})

    def call_tool_json(self, name, arguments=None):
        return tool_result_json(self.call_tool(name, arguments or {}))


def discover_mcp_tools(config, actor=None):
    started_at = time.monotonic()
    try:
        validate_outbound_url(config.endpoint_url, allow_private=config.allow_private_network)
        tools = MCPHttpClient(config).list_tools()
        safe_tools = [{"name": item.get("name", ""), "description": item.get("description", ""), "inputSchema": item.get("inputSchema", {"type": "object"})} for item in tools if item.get("name")]
        config.discovered_tools = safe_tools
        config.allowed_tools = [name for name in config.allowed_tools if name in {item["name"] for item in safe_tools}]
        config.connection_status = ConnectionStatus.CONNECTED
        config.last_error = ""
        success, message = True, f"连接成功，发现 {len(safe_tools)} 个工具"
    except Exception as exc:
        config.connection_status = ConnectionStatus.ERROR
        config.last_error = str(exc)[:500]
        success, message = False, str(exc)
    config.last_tested_at = timezone.now()
    config.save(update_fields=["discovered_tools", "allowed_tools", "connection_status", "last_error", "last_tested_at", "updated_at"])
    record_integration_event("mcp", config, "discover", actor=actor, success=success, started_at=started_at, detail={"tool_count": len(config.discovered_tools)}, error_message="" if success else message)
    return success, message


def build_agent_mcp_tools():
    definitions, mapping = [], {}
    servers = MCPServerConfig.objects.filter(enabled=True, agent_query_enabled=True, connection_status=ConnectionStatus.CONNECTED)
    for server in servers:
        allowed = set(server.allowed_tools)
        for tool in server.discovered_tools:
            if tool.get("name") not in allowed:
                continue
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", tool["name"])[:40]
            function_name = f"mcp_{server.id}_{safe_name}"[:64]
            definitions.append({
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": f"[{server.name}] {tool.get('description', tool['name'])}",
                    "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                },
            })
            mapping[function_name] = (server, tool["name"])
    return definitions, mapping


def execute_agent_mcp_tool(function_name, arguments, mapping, ai_run=None):
    if function_name not in mapping:
        raise ValueError("未授权的 MCP 工具")
    server, tool_name = mapping[function_name]
    if tool_name not in server.allowed_tools or not server.enabled or not server.agent_query_enabled:
        raise ValueError("该 MCP 工具未开放给智能体")
    started_at = time.monotonic()
    try:
        result = MCPHttpClient(server).call_tool(tool_name, arguments)
        record_integration_event("mcp", server, "agent_tool_call", success=True, started_at=started_at, detail={"tool": tool_name}, ai_run=ai_run)
        return result
    except Exception as exc:
        record_integration_event("mcp", server, "agent_tool_call", success=False, started_at=started_at, detail={"tool": tool_name}, error_message=str(exc), ai_run=ai_run)
        raise

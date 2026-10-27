from copy import deepcopy

from rest_framework.permissions import BasePermission


PERMISSION_GROUPS = [
    {
        "code": "overview",
        "name": "经营驾驶舱",
        "modules": [
            {"code": "dashboard", "name": "实时数据 / 经营总览", "actions": [("view", "查看")]},
        ],
    },
    {
        "code": "bi",
        "name": "数据 BI 看板",
        "modules": [
            {"code": "business", "name": "综合经营 BI", "actions": [("view", "查看"), ("export", "导出")]},
            {"code": "shops", "name": "店铺经营 BI", "actions": [("view", "查看"), ("export", "导出")]},
            {"code": "products", "name": "商品经营 BI", "actions": [("view", "查看"), ("export", "导出")]},
        ],
    },
    {
        "code": "operations",
        "name": "运营策略与任务",
        "modules": [
            {"code": "strategy_alerts", "name": "运营策略预警", "actions": [("view", "查看"), ("edit", "处理")]},
            {"code": "strategies", "name": "运营策略", "actions": [("view", "查看"), ("create", "新建"), ("edit", "编辑"), ("delete", "删除"), ("run", "执行")]},
            {"code": "operation_plans", "name": "运营计划", "actions": [("view", "查看"), ("create", "新建"), ("edit", "编辑"), ("delete", "删除")]},
            {"code": "tasks", "name": "运营任务中心", "actions": [("view", "查看"), ("create", "新建"), ("edit", "编辑"), ("delete", "删除")]},
        ],
    },
    {
        "code": "ai",
        "name": "AI 工具区",
        "modules": [
            {"code": "ai_analysis", "name": "AI 分析中心", "actions": [("view", "查看"), ("create", "发起分析")]},
            {"code": "mcp_query", "name": "智能体 / MCP 查询", "actions": [("use", "允许调用")]},
        ],
    },
    {
        "code": "data",
        "name": "数据接入",
        "modules": [
            {"code": "data_sync", "name": "数据同步", "actions": [("view", "查看"), ("manage", "执行与管理")]},
            {"code": "data_import", "name": "数据导入", "actions": [("view", "查看记录"), ("manage", "执行导入")]},
        ],
    },
    {
        "code": "system",
        "name": "系统管理",
        "modules": [
            {"code": "configuration", "name": "配置中心", "actions": [("view", "查看"), ("manage", "管理")]},
            {"code": "accounts", "name": "用户审批", "actions": [("view", "查看"), ("manage", "审批与分配角色")]},
            {"code": "roles", "name": "角色权限", "actions": [("view", "查看"), ("manage", "管理")]},
        ],
    },
]


def permission_catalog():
    groups = deepcopy(PERMISSION_GROUPS)
    for group in groups:
        for module in group["modules"]:
            module["actions"] = [
                {"code": action, "name": name, "permission": f"{module['code']}.{action}"}
                for action, name in module["actions"]
            ]
    return groups


def all_permission_codes():
    return {
        f"{module['code']}.{action}"
        for group in PERMISSION_GROUPS
        for module in group["modules"]
        for action, _ in module["actions"]
    }


def default_permission_codes(role_code):
    all_codes = all_permission_codes()
    if role_code in {"owner", "admin"}:
        return all_codes
    if role_code in {"editor", "operator"}:
        blocked = {code for code in all_codes if code.startswith(("configuration.", "accounts.", "roles.", "data_sync."))}
        return all_codes - blocked
    return {code for code in all_codes if code.endswith(".view")}


def permission_codes_for_user(user):
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return all_permission_codes()
    profile = getattr(user, "profile", None)
    role = getattr(profile, "access_role", None)
    if role and role.is_active:
        return set(role.permissions or []) & all_permission_codes()
    legacy_role = getattr(profile, "role", "operator")
    return default_permission_codes(legacy_role)


def user_has_permission(user, code):
    return code in permission_codes_for_user(user)


def allowed_shops_for_user(user):
    if not user or not user.is_authenticated or user.is_superuser:
        return None
    profile = getattr(user, "profile", None)
    role = getattr(profile, "access_role", None)
    if not role or role.data_scope == "all":
        return None
    return [str(item) for item in (profile.allowed_shops or []) if str(item).strip()]


def scope_queryset_by_shop(queryset, user, field="shop"):
    allowed = allowed_shops_for_user(user)
    return queryset if allowed is None else queryset.filter(**{f"{field}__in": allowed})


class HasWarehousePermission(BasePermission):
    message = "当前角色没有此功能权限"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        module = getattr(view, "permission_module", "")
        if not module:
            return True
        action = getattr(view, "permission_action", "") or self._action(request, view)
        return user_has_permission(request.user, f"{module}.{action}")

    @staticmethod
    def _action(request, view):
        custom = {
            "run": "run", "run_all": "run", "transition": "edit", "set_status": "edit",
            "convert_plan": "edit", "from_abnormal": "create", "detect": "edit",
        }
        if getattr(view, "action", "") in custom:
            return custom[view.action]
        module = getattr(view, "permission_module", "")
        if module in {"accounts", "roles", "configuration", "data_sync"} and request.method not in {"GET", "HEAD", "OPTIONS"}:
            return "manage"
        if getattr(view, "action", "") in {"approve", "reject", "update_access", "file", "feishu"}:
            return "manage"
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return "view"
        if request.method == "POST":
            return "create"
        if request.method in {"PUT", "PATCH"}:
            return "edit"
        if request.method == "DELETE":
            return "delete"
        return "view"

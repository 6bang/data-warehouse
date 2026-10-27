from rest_framework.permissions import BasePermission
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.warehouse.access_control import user_has_permission
from apps.warehouse.services.mcp import get_mcp_access_token


class BusinessMCPAuthentication(BaseAuthentication):
    """Authenticate external Agents with a revocable mcp_* token.

    JWT authentication remains available on the same endpoint for internal
    callers. This authenticator only handles the dedicated MCP token prefix.
    """

    www_authenticate_realm = "business-mcp"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        scheme, _, raw_token = header.partition(" ")
        if scheme.lower() != "bearer" or not raw_token.startswith("mcp_"):
            return None
        token = get_mcp_access_token(raw_token)
        if not token:
            raise AuthenticationFailed("MCP 密钥无效、已停用或已过期")
        return token.owner, token

    def authenticate_header(self, request):
        return f'Bearer realm="{self.www_authenticate_realm}"'


class IsAdminRole(BasePermission):
    message = "仅管理员可以执行此操作"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.role == "admin") or user_has_permission(request.user, "configuration.manage")

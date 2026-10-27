from django.contrib.auth.models import User
import json
import re

from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import OpenApiTypes, extend_schema

from apps.warehouse.models import (
    AccessRole,
    AccountProfile,
    AbnormalRecord,
    AIAnalysisRun,
    AIProviderConfig,
    FeishuIntegration,
    ImportBatch,
    IntegrationEventLog,
    MCPAccessToken,
    MCPServerConfig,
    MonthlyProductFact,
    OperationPlan,
    OperationStrategy,
    OperationTask,
    ProductCatalog,
    ProductData,
    StrategyAlert,
)
from apps.warehouse.serializers import (
    AccessRoleSerializer,
    AbnormalRecordSerializer,
    AccountAccessSerializer,
    AccountReviewSerializer,
    AIAnalysisRequestSerializer,
    AIAnalysisRunSerializer,
    AIProviderConfigSerializer,
    FeishuImportSerializer,
    FeishuIntegrationSerializer,
    ImportBatchSerializer,
    IntegrationEventLogSerializer,
    MCPServerConfigSerializer,
    MCPAccessTokenSerializer,
    OperationPlanSerializer,
    OperationStrategySerializer,
    OperationTaskSerializer,
    ProductCatalogSerializer,
    ProductDataSerializer,
    RegistrationSerializer,
    StrategyAlertSerializer,
    TaskTransitionSerializer,
    UserSerializer,
)
from apps.warehouse.access_control import (
    HasWarehousePermission,
    allowed_shops_for_user,
    permission_catalog,
    scope_queryset_by_shop,
)
from apps.warehouse.permissions import BusinessMCPAuthentication
from apps.warehouse.services.ai import run_analysis
from apps.warehouse.services.anomalies import detect_anomalies
from apps.warehouse.services.dashboard import (
    available_months,
    month_bounds,
    monthly_dashboard,
    monthly_product_ranking,
    monthly_shop_ranking,
)
from apps.warehouse.services.importers import FeishuBaseAdapter, import_rows, rows_from_upload
from apps.warehouse.services.integrations import get_feishu_integration, test_ai_connection, test_feishu_connection
from apps.warehouse.services.mcp import discover_mcp_tools, generate_mcp_access_token, MCP_TOOL_PERMISSION_MAP
from apps.warehouse.services.mcp_sync import list_stores as list_mcp_stores
from apps.warehouse.services.mcp_sync import sync_month as sync_mcp_month
from apps.warehouse.services.realtime import realtime_dashboard
from apps.warehouse.services.business import business_dimensions, monthly_business
from apps.warehouse.services.strategies import run_enabled_strategies, run_strategy
from apps.warehouse.services.feishu_oauth import (
    authorization_url,
    display_name,
    ensure_allowed_tenant,
    exchange_code,
    new_state,
    oauth_redirect_uri,
)


class MeView(APIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RegistrationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegistrationSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "注册申请已提交，请等待管理员审批",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


def _feishu_login_redirect(reason):
    return redirect(f"/login?feishu={reason}")


class FeishuLoginStartView(APIView):
    """Start Feishu OAuth without exposing App Secret to the browser."""

    permission_classes = [AllowAny]

    def get(self, request):
        config = get_feishu_integration()
        if not config or not config.app_id or not config.app_secret_encrypted:
            return _feishu_login_redirect("not_configured")
        state = new_state()
        request.session["feishu_oauth_state"] = state
        request.session.save()
        return redirect(authorization_url(config, oauth_redirect_uri(request), state))


class FeishuLoginCallbackView(APIView):
    """Validate OAuth state, identify the tenant and stage a one-time login."""

    permission_classes = [AllowAny]

    def get(self, request):
        state = request.query_params.get("state", "")
        expected_state = request.session.pop("feishu_oauth_state", "")
        request.session.save()
        if not state or not expected_state or state != expected_state:
            return _feishu_login_redirect("invalid_state")
        if request.query_params.get("error"):
            return _feishu_login_redirect("cancelled")
        code = request.query_params.get("code", "")
        config = get_feishu_integration()
        if not code or not config:
            return _feishu_login_redirect("oauth_failed")
        try:
            user_info = exchange_code(config, code, oauth_redirect_uri(request))
            tenant_key = ensure_allowed_tenant(user_info, config)
        except PermissionError:
            return _feishu_login_redirect("tenant_denied")
        except Exception:
            return _feishu_login_redirect("oauth_failed")

        open_id = str(user_info.get("open_id") or "").strip()
        if not open_id:
            return _feishu_login_redirect("oauth_failed")
        now = timezone.now()
        profile = AccountProfile.objects.select_related("user").filter(feishu_open_id=open_id).first()
        if profile is None:
            safe_open_id = re.sub(r"[^A-Za-z0-9_-]", "", open_id)[-100:] or new_state()[:24]
            username = f"feishu_{safe_open_id}"[:150]
            if User.objects.filter(username=username).exists():
                username = f"{username[:120]}_{new_state()[:20]}"
            user = User.objects.create(
                username=username,
                first_name=display_name(user_info),
                email=str(user_info.get("email") or "")[:254],
                is_active=False,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            profile = AccountProfile.objects.create(
                user=user,
                role=AccountProfile.Role.OPERATOR,
                requested_role_code="viewer",
                registration_reason="飞书账号首次登录注册",
                approval_status=AccountProfile.ApprovalStatus.PENDING,
                feishu_open_id=open_id,
                feishu_union_id=str(user_info.get("union_id") or "")[:100],
                feishu_user_id=str(user_info.get("user_id") or "")[:100],
                feishu_tenant_key=tenant_key,
                feishu_last_login_at=now,
            )
        else:
            user = profile.user
            profile.feishu_union_id = str(user_info.get("union_id") or profile.feishu_union_id)[:100]
            profile.feishu_user_id = str(user_info.get("user_id") or profile.feishu_user_id)[:100]
            profile.feishu_tenant_key = tenant_key
            profile.feishu_last_login_at = now
            profile.save(update_fields=[
                "feishu_union_id", "feishu_user_id", "feishu_tenant_key", "feishu_last_login_at", "updated_at",
            ])

        request.session["feishu_login_user_id"] = user.id
        request.session.save()
        return _feishu_login_redirect("complete")


class FeishuLoginExchangeView(APIView):
    """Exchange the callback's same-site session for this app's JWT pair."""

    permission_classes = [AllowAny]

    def post(self, request):
        user_id = request.session.pop("feishu_login_user_id", None)
        request.session.save()
        if not user_id:
            return Response({"detail": "飞书登录状态已失效，请重新登录"}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.select_related("profile").filter(pk=user_id).first()
        if not user:
            return Response({"detail": "飞书账号不存在"}, status=status.HTTP_400_BAD_REQUEST)
        profile = getattr(user, "profile", None)
        if not user.is_active or not profile or profile.approval_status != AccountProfile.ApprovalStatus.APPROVED:
            reason = "账号正在等待管理员审批" if profile and profile.approval_status == AccountProfile.ApprovalStatus.PENDING else "账号注册申请未获批准，请联系管理员"
            return Response({"detail": reason, "approval_status": getattr(profile, "approval_status", "pending")}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        return Response({"refresh": str(refresh), "access": str(refresh.access_token)})


class AccountViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "accounts"

    def get_queryset(self):
        queryset = User.objects.select_related("profile", "profile__access_role", "profile__reviewed_by").order_by("-date_joined")
        approval_status = self.request.query_params.get("approval_status")
        if approval_status:
            queryset = queryset.filter(profile__approval_status=approval_status)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(first_name__icontains=search) | Q(email__icontains=search)
            )
        return queryset

    def _review(self, request, user, approval_status):
        if user.is_superuser:
            return Response({"detail": "不能修改超级管理员的审批状态"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AccountReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = AccountProfile.objects.get_or_create(user=user)
        profile.approval_status = approval_status
        profile.review_note = serializer.validated_data["note"]
        profile.reviewed_by = request.user
        profile.reviewed_at = timezone.now()
        if approval_status == AccountProfile.ApprovalStatus.APPROVED:
            access_role = serializer.validated_data.get("access_role")
            if access_role is None:
                access_role = AccessRole.objects.filter(
                    code=profile.requested_role_code or "viewer", is_active=True
                ).first() or AccessRole.objects.filter(code="viewer", is_active=True).first()
            profile.access_role = access_role
            profile.role = AccountProfile.Role.ADMIN if access_role and access_role.code == "admin" else AccountProfile.Role.OPERATOR
            if "allowed_shops" in serializer.validated_data:
                profile.allowed_shops = serializer.validated_data["allowed_shops"]
        profile.save()
        user.is_active = approval_status == AccountProfile.ApprovalStatus.APPROVED
        user.save(update_fields=["is_active"])
        user.refresh_from_db()
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review(request, self.get_object(), AccountProfile.ApprovalStatus.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review(request, self.get_object(), AccountProfile.ApprovalStatus.REJECTED)

    @action(detail=True, methods=["post"])
    def update_access(self, request, pk=None):
        user = self.get_object()
        if user.is_superuser:
            return Response({"detail": "不能修改系统所有者权限"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = AccountAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = AccountProfile.objects.get_or_create(user=user)
        role = serializer.validated_data["access_role"]
        profile.access_role = role
        profile.allowed_shops = serializer.validated_data.get("allowed_shops", [])
        profile.role = AccountProfile.Role.ADMIN if role.code == "admin" else AccountProfile.Role.OPERATOR
        profile.save(update_fields=["access_role", "allowed_shops", "role", "updated_at"])
        user.refresh_from_db()
        return Response(UserSerializer(user).data)


class AccessRoleViewSet(viewsets.ModelViewSet):
    serializer_class = AccessRoleSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "roles"

    def get_queryset(self):
        return AccessRole.objects.annotate(member_count=Count("members")).order_by("sort_order", "id")

    def perform_create(self, serializer):
        serializer.save(role_type=AccessRole.RoleType.CUSTOM)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.role_type == AccessRole.RoleType.SYSTEM:
            return Response({"detail": "系统角色不能删除"}, status=status.HTTP_400_BAD_REQUEST)
        if role.members.exists():
            return Response({"detail": "该角色仍有成员，不能删除"}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        shops = set(ProductData.objects.order_by().values_list("shop", flat=True).distinct())
        shops.update(MonthlyProductFact.objects.order_by().values_list("shop", flat=True).distinct())
        return Response({"permission_groups": permission_catalog(), "shops": sorted(item for item in shops if item)})


class ConfigurationSummaryView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        feishu = FeishuIntegration.objects.order_by("id").first()
        active_ai = AIProviderConfig.objects.filter(enabled=True, is_default=True).first() or AIProviderConfig.objects.filter(enabled=True).first()
        return Response({
            "feishu": FeishuIntegrationSerializer(feishu).data if feishu else None,
            "active_ai_provider": AIProviderConfigSerializer(active_ai).data if active_ai else None,
            "mcp": {
                "total": MCPServerConfig.objects.count(),
                "connected": MCPServerConfig.objects.filter(connection_status="connected").count(),
                "agent_enabled": MCPServerConfig.objects.filter(enabled=True, agent_query_enabled=True).count(),
                "data_sync_enabled": MCPServerConfig.objects.filter(enabled=True, data_sync_enabled=True).count(),
            },
        })


class MCPDataSyncView(APIView):
    """One-click monthly import backed by an administrator-approved MCP source."""

    permission_classes = [HasWarehousePermission]
    permission_module = "data_sync"

    def get(self, request):
        sources = MCPServerConfig.objects.filter(enabled=True, data_sync_enabled=True).order_by("name")
        return Response({
            "sources": [
                {
                    "id": item.id,
                    "name": "经营数据源",
                    "organization_name": item.organization_name,
                    "connection_status": item.connection_status,
                    "last_synced_at": item.last_synced_at,
                    "last_error": item.last_error,
                }
                for item in sources
            ]
        })

    def post(self, request):
        source_id = request.data.get("source_id")
        try:
            config = MCPServerConfig.objects.get(pk=source_id, enabled=True, data_sync_enabled=True)
        except (MCPServerConfig.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "未找到可用的经营数据源"}, status=status.HTTP_400_BAD_REQUEST)
        action_name = request.data.get("action", "sync")
        try:
            if action_name == "stores":
                return Response({"stores": list_mcp_stores(config)})
            if action_name != "sync":
                return Response({"detail": "不支持的同步操作"}, status=status.HTTP_400_BAD_REQUEST)
            month = str(request.data.get("month") or timezone.localdate().strftime("%Y-%m"))
            store_ids = request.data.get("store_ids") or []
            if not isinstance(store_ids, list):
                return Response({"detail": "store_ids 必须是数组"}, status=status.HTTP_400_BAD_REQUEST)
            job = sync_mcp_month(
                config,
                month,
                organization=str(request.data.get("organization_name") or config.organization_name),
                store_ids=store_ids,
                actor=request.user,
            )
            return Response({
                "success": True,
                "message": f"{month} 经营数据同步完成",
                "job_id": job.id,
                "summary": job.summary,
            })
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class FeishuIntegrationViewSet(viewsets.ModelViewSet):
    queryset = FeishuIntegration.objects.select_related("updated_by")
    serializer_class = FeishuIntegrationSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    def perform_create(self, serializer):
        if FeishuIntegration.objects.exists():
            raise serializers.ValidationError({"detail": "MVP 仅支持一个飞书连接，请编辑现有配置"})
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        success, message = test_feishu_connection(self.get_object(), request.user)
        return Response({"success": success, "message": message}, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


class AIProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = AIProviderConfig.objects.select_related("updated_by")
    serializer_class = AIProviderConfigSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    def _save(self, serializer):
        with transaction.atomic():
            instance = serializer.save(updated_by=self.request.user)
            if instance.is_default:
                AIProviderConfig.objects.exclude(pk=instance.pk).update(is_default=False)
            elif not AIProviderConfig.objects.filter(enabled=True, is_default=True).exists() and instance.enabled:
                instance.is_default = True
                instance.save(update_fields=["is_default", "updated_at"])
        return instance

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        success, message = test_ai_connection(self.get_object(), request.user)
        return Response({"success": success, "message": message}, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def set_default(self, request, pk=None):
        config = self.get_object()
        if not config.enabled:
            return Response({"detail": "请先启用该模型"}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            AIProviderConfig.objects.update(is_default=False)
            config.is_default = True
            config.save(update_fields=["is_default", "updated_at"])
        return Response(AIProviderConfigSerializer(config).data)


class MCPServerConfigViewSet(viewsets.ModelViewSet):
    queryset = MCPServerConfig.objects.select_related("updated_by")
    serializer_class = MCPServerConfigSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def discover(self, request, pk=None):
        success, message = discover_mcp_tools(self.get_object(), request.user)
        return Response({"success": success, "message": message}, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)


class MCPAccessTokenViewSet(viewsets.ModelViewSet):
    queryset = MCPAccessToken.objects.select_related("owner", "created_by", "reviewed_by")
    serializer_class = MCPAccessTokenSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    def perform_create(self, serializer):
        raw_token, token_hash, token_prefix = generate_mcp_access_token()
        self._issued_token = raw_token
        owner = serializer.validated_data.get("owner") or self.request.user
        serializer.save(
            owner=owner,
            token_hash=token_hash,
            token_prefix=token_prefix,
            created_by=self.request.user,
            agent_name=serializer.validated_data.get("agent_name") or serializer.validated_data.get("name") or "飞书经营智能体",
            approval_status=MCPAccessToken.ApprovalStatus.PENDING,
        )

    def perform_update(self, serializer):
        changed_fields = {"agent_name", "agent_platform", "agent_id", "allowed_tools", "permission_codes", "allowed_shops", "expires_at", "owner"}
        requires_review = bool(changed_fields.intersection(serializer.validated_data))
        extra = {"updated_at": timezone.now()}
        if requires_review:
            extra.update({
                "approval_status": MCPAccessToken.ApprovalStatus.PENDING,
                "reviewed_by": None,
                "reviewed_at": None,
                "enabled": False,
            })
        serializer.save(**extra)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data["token"] = self._issued_token
        response.data["token_notice"] = "密钥只显示这一次，请立即复制到飞书智能体的 MCP Authorization Bearer 配置中"
        return response

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        token = self.get_object()
        decision = request.data.get("approval_status")
        valid = {choice for choice, _label in MCPAccessToken.ApprovalStatus.choices}
        if decision not in valid:
            return Response({"detail": "审核状态必须是 pending、approved 或 rejected"}, status=status.HTTP_400_BAD_REQUEST)
        token.approval_status = decision
        token.review_note = str(request.data.get("review_note", ""))[:500]
        token.reviewed_by = request.user
        token.reviewed_at = timezone.now()
        if decision in {MCPAccessToken.ApprovalStatus.PENDING, MCPAccessToken.ApprovalStatus.REJECTED}:
            token.enabled = False
        elif decision == MCPAccessToken.ApprovalStatus.APPROVED:
            token.enabled = True
        token.save(update_fields=["approval_status", "review_note", "reviewed_by", "reviewed_at", "enabled", "updated_at"])
        return Response(self.get_serializer(token).data)


class IntegrationEventLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = IntegrationEventLog.objects.select_related("actor")
    serializer_class = IntegrationEventLogSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "configuration"

    def get_queryset(self):
        queryset = super().get_queryset()
        integration_type = self.request.query_params.get("integration_type")
        return queryset.filter(integration_type=integration_type) if integration_type else queryset


class DashboardView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "dashboard"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            allowed_shops = allowed_shops_for_user(request.user)
            shop = request.query_params.get("shop", "")
            if allowed_shops is not None and shop and shop not in allowed_shops:
                return Response({"detail": "当前角色无权查看该店铺"}, status=status.HTTP_403_FORBIDDEN)
            return Response(monthly_dashboard(request.query_params.get("month", ""), shop, allowed_shops))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class RealtimeDashboardView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "dashboard"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            return Response(realtime_dashboard(
                shop=request.query_params.get("shop", ""),
                allowed_shops=allowed_shops_for_user(request.user),
                force_refresh=request.query_params.get("refresh") == "1",
            ))
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class ShopMonthlyView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "shops"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        month = request.query_params.get("month")
        if not month:
            months = available_months(allowed_shops=allowed_shops_for_user(request.user))
            month = months[0] if months else ""
        if not month:
            return Response({"count": 0, "results": []})
        try:
            rows = monthly_shop_ranking(
                month,
                request.query_params.get("search", ""),
                request.query_params.get("ordering", "-sales"),
                allowed_shops_for_user(request.user),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"count": len(rows), "results": rows})


class BusinessDimensionsView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "business"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        params = dict(request.query_params.items())
        params["_allowed_shops"] = allowed_shops_for_user(request.user)
        return Response(business_dimensions(params))


class MonthlyBusinessView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "business"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            params = dict(request.query_params.items())
            params["_allowed_shops"] = allowed_shops_for_user(request.user)
            return Response(monthly_business(params))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BusinessMCPView(APIView):
    """只读业务 MCP Server；使用当前登录用户的 JWT 完成组织级审计与授权。"""
    permission_classes = [HasWarehousePermission]
    authentication_classes = [BusinessMCPAuthentication, JWTAuthentication]
    permission_module = "mcp_query"
    permission_action = "use"

    TOOLS = [
        {
            "name": "list_business_dimensions",
            "description": "列出可查询的组织、月份、平台、店铺、品类和运营人员。",
            "inputSchema": {
                "type": "object",
                "properties": {"organization": {"type": "string"}, "month": {"type": "string"}},
            },
        },
        {
            "name": "query_monthly_metrics",
            "description": "按平台、店铺、品类、商品或运营人员汇总月度经营指标。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "organization": {"type": "string"}, "month": {"type": "string"},
                    "platform": {"type": "string"}, "shop": {"type": "string"},
                    "category_path": {"type": "string"}, "operator_name": {"type": "string"},
                    "group_by": {"type": "string", "enum": ["platform", "shop", "category", "product", "operator"]},
                    "ordering": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "required": ["organization", "month"],
            },
        },
        {
            "name": "query_realtime_metrics",
            "description": "查询当前已接入数据源的今日实时经营指标和按小时趋势。",
            "inputSchema": {
                "type": "object",
                "properties": {"shop": {"type": "string"}, "force_refresh": {"type": "boolean"}},
            },
        },
    ]

    @staticmethod
    def _rpc_result(request_id, result):
        return Response({"jsonrpc": "2.0", "id": request_id, "result": result})

    def post(self, request):
        request_id = request.data.get("id")
        method = request.data.get("method")
        if method == "initialize":
            return self._rpc_result(request_id, {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "commerce-warehouse-business", "version": "1.1.0"},
            })
        if method == "notifications/initialized":
            return Response(status=status.HTTP_204_NO_CONTENT)
        if method == "tools/list":
            tools = self.TOOLS
            access_token = getattr(request, "auth", None)
            if isinstance(access_token, MCPAccessToken):
                allowed = set(access_token.allowed_tools or [])
                permissions = set(access_token.permission_codes or [])
                tools = [tool for tool in self.TOOLS if tool["name"] in allowed and MCP_TOOL_PERMISSION_MAP.get(tool["name"]) in permissions]
            return self._rpc_result(request_id, {"tools": tools})
        if method == "tools/call":
            params = request.data.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            access_token = getattr(request, "auth", None)
            if isinstance(access_token, MCPAccessToken):
                if name not in set(access_token.allowed_tools or []):
                    return self._rpc_result(request_id, {
                        "content": [{"type": "text", "text": "该 MCP 密钥未授权此工具"}], "isError": True,
                    })
                required_permission = MCP_TOOL_PERMISSION_MAP.get(name)
                if required_permission and required_permission not in set(access_token.permission_codes or []):
                    return self._rpc_result(request_id, {
                        "content": [{"type": "text", "text": "该 MCP 密钥未授权此权限"}], "isError": True,
                    })
                token_shops = [str(item) for item in (access_token.allowed_shops or []) if str(item).strip()]
                arguments["_allowed_shops"] = token_shops or allowed_shops_for_user(request.user)
            else:
                arguments["_allowed_shops"] = allowed_shops_for_user(request.user)
            try:
                if name == "list_business_dimensions":
                    result = business_dimensions(arguments)
                elif name == "query_monthly_metrics":
                    result = monthly_business(arguments)
                elif name == "query_realtime_metrics":
                    result = realtime_dashboard(
                        shop=arguments.get("shop", ""),
                        allowed_shops=arguments.get("_allowed_shops"),
                        force_refresh=bool(arguments.get("force_refresh", False)),
                    )
                else:
                    raise ValueError("工具不存在或未授权")
                return self._rpc_result(request_id, {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                    "structuredContent": result,
                    "isError": False,
                })
            except ValueError as exc:
                return self._rpc_result(request_id, {
                    "content": [{"type": "text", "text": str(exc)}], "isError": True,
                })
        return Response({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }, status=status.HTTP_400_BAD_REQUEST)


class ProductCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductCatalogSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "products"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(ProductCatalog.objects.all(), self.request.user)
        params = self.request.query_params
        for field in ("organization", "platform", "shop"):
            if params.get(field):
                queryset = queryset.filter(**{field: params[field]})
        if params.get("search"):
            term = params["search"]
            queryset = queryset.filter(
                Q(product_id__icontains=term)
                | Q(product_name__icontains=term)
                | Q(product_code__icontains=term)
            )
        if params.get("created_from"):
            queryset = queryset.filter(product_created_at__date__gte=params["created_from"])
        if params.get("created_to"):
            queryset = queryset.filter(product_created_at__date__lte=params["created_to"])
        # 生命周期是展示层的派生字段，不落库。使用本地日期边界筛选，兼容
        # MySQL/SQLite，并且与序列化器中的“创建日为第 1 天”规则一致。
        lifecycle = params.get("lifecycle", "").strip().lower()
        today = timezone.localdate()
        if lifecycle == "new":
            queryset = queryset.filter(
                product_created_at__date__gte=today - timedelta(days=34),
                product_created_at__date__lte=today,
            )
        elif lifecycle == "mature":
            queryset = queryset.filter(product_created_at__date__lte=today - timedelta(days=35))
        elif lifecycle == "unknown":
            queryset = queryset.filter(
                Q(product_created_at__isnull=True) | Q(product_created_at__date__gt=today)
            )
        ordering = params.get("ordering", "-product_created_at")
        allowed = {"product_created_at", "product_name", "product_code", "shop", "product_id", "last_seen_month"}
        raw = ordering.lstrip("-")
        return queryset.order_by(ordering if raw in allowed else "-product_created_at")


class ProductDataViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductDataSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "products"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(
            ProductData.objects.filter(record_type=ProductData.RecordType.PRODUCT), self.request.user
        )
        params = self.request.query_params
        if params.get("date"):
            queryset = queryset.filter(date=params["date"])
        else:
            latest = queryset.aggregate(value=Max("date"))["value"]
            if latest:
                queryset = queryset.filter(date=latest)
        if params.get("shop"):
            queryset = queryset.filter(shop=params["shop"])
        if params.get("search"):
            queryset = queryset.filter(Q(product_id__icontains=params["search"]) | Q(product_name__icontains=params["search"]))
        ordering = params.get("ordering", "-sales")
        allowed = {"sales", "sales_volume", "visitors", "conversion_rate", "ad_cost", "roi", "profit", "stock", "date"}
        raw = ordering.lstrip("-")
        return queryset.order_by(ordering if raw in allowed else "-sales")

    @action(detail=False, methods=["get"])
    def monthly(self, request):
        month = request.query_params.get("month")
        if not month:
            months = available_months(
                request.query_params.get("shop", ""), allowed_shops_for_user(request.user)
            )
            month = months[0] if months else ""
        if not month:
            return self.get_paginated_response([])
        try:
            rows = monthly_product_ranking(
                month,
                request.query_params.get("shop", ""),
                request.query_params.get("search", ""),
                request.query_params.get("ordering", "-sales"),
                allowed_shops_for_user(request.user),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(page)


class AbnormalRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AbnormalRecordSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "strategy_alerts"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(AbnormalRecord.objects.all(), self.request.user)
        for field in ("date", "shop", "product_id", "type", "level", "status"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    @action(detail=False, methods=["post"], permission_classes=[HasWarehousePermission])
    def detect(self, request):
        day = request.data.get("date")
        if not day:
            return Response({"detail": "date 必填"}, status=status.HTTP_400_BAD_REQUEST)
        shop = request.data.get("shop", "")
        allowed_shops = allowed_shops_for_user(request.user)
        if allowed_shops is not None and (not shop or shop not in allowed_shops):
            return Response({"detail": "请选择一个已授权店铺"}, status=status.HTTP_403_FORBIDDEN)
        records = detect_anomalies(day, shop)
        return Response({"created_or_updated": len(records), "records": AbnormalRecordSerializer(records, many=True).data})


class ImportBatchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ImportBatch.objects.select_related("operator")
    serializer_class = ImportBatchSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "data_import"

    def get_queryset(self):
        return scope_queryset_by_shop(super().get_queryset(), self.request.user)

    def _run_detection(self, batch):
        dates = batch.product_rows.values_list("date", flat=True).distinct()
        return sum(len(detect_anomalies(day, batch.shop)) for day in dates)

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser], permission_classes=[HasWarehousePermission])
    def file(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "file 必填"}, status=status.HTTP_400_BAD_REQUEST)
        data_type = request.data.get("data_type", "product")
        if data_type not in {"product", "paid", "shop"}:
            return Response({"detail": "data_type 仅支持 product/paid/shop"}, status=status.HTTP_400_BAD_REQUEST)
        shop = request.data.get("shop") or "默认店铺"
        allowed_shops = allowed_shops_for_user(request.user)
        if allowed_shops is not None and shop not in allowed_shops:
            return Response({"detail": "当前角色无权向该店铺导入数据"}, status=status.HTTP_403_FORBIDDEN)
        batch = ImportBatch.objects.create(
            source=ImportBatch.Source.EXCEL,
            data_type=data_type,
            source_name=upload.name,
            shop=shop,
            operator=request.user,
        )
        try:
            import_rows(rows_from_upload(upload), batch)
            detected = self._run_detection(batch) if request.data.get("run_detection", "true").lower() != "false" else 0
            payload = ImportBatchSerializer(batch).data
            payload["detected_abnormal"] = detected
            return Response(payload, status=status.HTTP_201_CREATED)
        except Exception as exc:
            batch.status = ImportBatch.Status.FAILED
            batch.error_summary = [{"message": str(exc)}]
            batch.save(update_fields=["status", "error_summary", "updated_at"])
            return Response({"detail": str(exc), "batch_id": batch.id}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[HasWarehousePermission])
    def feishu(self, request):
        serializer = FeishuImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        allowed_shops = allowed_shops_for_user(request.user)
        if allowed_shops is not None and values["shop"] not in allowed_shops:
            return Response({"detail": "当前角色无权向该店铺同步数据"}, status=status.HTTP_403_FORBIDDEN)
        config = get_feishu_integration()
        source_url = values.get("url") or (config.default_base_url if config else "")
        if not source_url:
            return Response({"detail": "请输入飞书 Base 链接，或先在配置中心设置默认 Base"}, status=status.HTTP_400_BAD_REQUEST)
        batch = ImportBatch.objects.create(
            source=ImportBatch.Source.FEISHU,
            data_type=values["data_type"],
            source_name=source_url,
            shop=values["shop"],
            operator=request.user,
        )
        try:
            rows, metadata = FeishuBaseAdapter().read(source_url)
            batch.source_name = f"{source_url}#{metadata['table_id']}"
            batch.save(update_fields=["source_name", "updated_at"])
            import_rows(rows, batch)
            detected = self._run_detection(batch) if values["run_detection"] else 0
            payload = ImportBatchSerializer(batch).data
            payload["detected_abnormal"] = detected
            return Response(payload, status=status.HTTP_201_CREATED)
        except Exception as exc:
            batch.status = ImportBatch.Status.FAILED
            batch.error_summary = [{"message": str(exc)}]
            batch.save(update_fields=["status", "error_summary", "updated_at"])
            return Response({"detail": str(exc), "batch_id": batch.id}, status=status.HTTP_400_BAD_REQUEST)


class AIAnalysisViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = AIAnalysisRun.objects.select_related("requester")
    serializer_class = AIAnalysisRunSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "ai_analysis"

    @extend_schema(request=AIAnalysisRequestSerializer, responses=AIAnalysisRunSerializer)
    def create(self, request):
        serializer = AIAnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = run_analysis(request.user, **serializer.validated_data)
        return Response(AIAnalysisRunSerializer(run).data, status=status.HTTP_201_CREATED)


class OperationTaskViewSet(viewsets.ModelViewSet):
    queryset = OperationTask.objects.select_related("owner", "abnormal_record", "ai_analysis_run")
    serializer_class = OperationTaskSerializer
    permission_classes = [HasWarehousePermission]
    permission_module = "tasks"

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ("status", "owner_id", "product_id", "source"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        month = self.request.query_params.get("month")
        if month:
            try:
                start, end = month_bounds(month)
                queryset = queryset.filter(created_at__date__gte=start, created_at__date__lt=end)
            except ValueError:
                return queryset.none()
        return queryset

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        task = self.get_object()
        serializer = TaskTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data["status"]
        allowed = {
            OperationTask.Status.PENDING: {OperationTask.Status.IN_PROGRESS},
            OperationTask.Status.IN_PROGRESS: {OperationTask.Status.COMPLETED},
            OperationTask.Status.COMPLETED: {OperationTask.Status.REVIEWED},
            OperationTask.Status.REVIEWED: set(),
        }
        if target not in allowed[task.status]:
            return Response({"detail": f"不允许从 {task.status} 流转到 {target}"}, status=status.HTTP_400_BAD_REQUEST)
        task.status = target
        if "result" in serializer.validated_data:
            task.result = serializer.validated_data["result"]
        if "review_result" in serializer.validated_data:
            task.review_result = serializer.validated_data["review_result"]
        if target == OperationTask.Status.COMPLETED:
            task.completed_at = timezone.now()
        if target == OperationTask.Status.REVIEWED:
            task.reviewed_at = timezone.now()
        task.save()
        return Response(OperationTaskSerializer(task).data)

    @action(detail=False, methods=["post"])
    def from_abnormal(self, request):
        abnormal_id = request.data.get("abnormal_record_id")
        try:
            abnormal = AbnormalRecord.objects.get(pk=abnormal_id)
        except AbnormalRecord.DoesNotExist:
            return Response({"detail": "异常记录不存在"}, status=status.HTTP_404_NOT_FOUND)
        task = OperationTask.objects.create(
            task_name=request.data.get("task_name") or f"处理：{abnormal.description[:120]}",
            product_id=abnormal.product_id,
            problem=abnormal.description,
            ai_suggestion=abnormal.suggestion,
            source=OperationTask.Source.ABNORMAL,
            abnormal_record=abnormal,
            owner_id=request.data.get("owner_id") or None,
            deadline=request.data.get("deadline") or None,
        )
        abnormal.status = AbnormalRecord.Status.ACKNOWLEDGED
        abnormal.save(update_fields=["status", "updated_at"])
        return Response(OperationTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class StrategyOptionsView(APIView):
    permission_classes = [HasWarehousePermission]
    permission_module = "strategies"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        params = dict(request.query_params.items())
        params["_allowed_shops"] = allowed_shops_for_user(request.user)
        dimensions = business_dimensions(params)
        providers = AIProviderConfig.objects.filter(enabled=True).values("id", "name", "provider", "model")
        users = User.objects.filter(is_active=True).values("id", "username", "first_name")
        return Response({"dimensions": dimensions, "agents": list(providers), "users": list(users)})


class OperationStrategyViewSet(viewsets.ModelViewSet):
    serializer_class = OperationStrategySerializer
    queryset = OperationStrategy.objects.prefetch_related("rules").select_related("agent_provider", "created_by")
    permission_classes = [HasWarehousePermission]
    permission_module = "strategies"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(super().get_queryset(), self.request.user)
        for field in ("strategy_type", "enabled", "organization", "shop"):
            value = self.request.query_params.get(field)
            if value != "" and value is not None:
                queryset = queryset.filter(**{field: value})
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        strategy = self.get_object()
        month = str(request.data.get("month") or MonthlyProductFact.objects.order_by("-month").values_list("month", flat=True).first() or "")
        try:
            return Response(run_strategy(strategy, month, request.user))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def run_all(self, request):
        month = str(request.data.get("month") or MonthlyProductFact.objects.order_by("-month").values_list("month", flat=True).first() or "")
        try:
            results = run_enabled_strategies(month, request.user)
            return Response({"month": month, "strategies": len(results), "results": results})
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyAlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StrategyAlertSerializer
    queryset = StrategyAlert.objects.select_related("strategy", "rule", "product_fact", "product_catalog")
    permission_classes = [HasWarehousePermission]
    permission_module = "strategy_alerts"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(super().get_queryset(), self.request.user)
        for field in ("month", "status", "level", "strategy_id", "organization", "shop", "product_id"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        alert = self.get_object()
        target = request.data.get("status")
        if target not in {StrategyAlert.Status.OPEN, StrategyAlert.Status.ACKNOWLEDGED, StrategyAlert.Status.RESOLVED}:
            return Response({"detail": "状态仅支持 open/acknowledged/resolved"}, status=status.HTTP_400_BAD_REQUEST)
        alert.status = target
        alert.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=["post"])
    def convert_plan(self, request, pk=None):
        alert = self.get_object()
        if hasattr(alert, "plan"):
            return Response(OperationPlanSerializer(alert.plan).data)
        plan = OperationPlan.objects.create(
            plan_name=request.data.get("plan_name") or f"处理：{alert.title[:160]}",
            strategy=alert.strategy, alert=alert, organization=alert.organization, shop=alert.shop,
            product_id=alert.product_id, product_name=alert.product_name, product_url=alert.product_url,
            objective=request.data.get("objective") or alert.description,
            actions=request.data.get("actions") or alert.suggestion or alert.agent_report,
            owner_id=request.data.get("owner_id") or None,
            start_date=request.data.get("start_date") or timezone.localdate(),
            deadline=request.data.get("deadline") or None,
            created_by=request.user,
        )
        alert.status = StrategyAlert.Status.CONVERTED
        alert.save(update_fields=["status", "updated_at"])
        return Response(OperationPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class OperationPlanViewSet(viewsets.ModelViewSet):
    serializer_class = OperationPlanSerializer
    queryset = OperationPlan.objects.select_related(
        "strategy", "alert", "alert__product_fact", "alert__product_catalog", "owner", "created_by"
    )
    permission_classes = [HasWarehousePermission]
    permission_module = "operation_plans"

    def get_queryset(self):
        queryset = scope_queryset_by_shop(super().get_queryset(), self.request.user)
        for field in ("status", "owner_id", "strategy_id", "organization", "shop", "product_id"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        plan = self.get_object()
        target = request.data.get("status")
        allowed = {
            OperationPlan.Status.PENDING: {OperationPlan.Status.IN_PROGRESS},
            OperationPlan.Status.IN_PROGRESS: {OperationPlan.Status.COMPLETED},
            OperationPlan.Status.COMPLETED: {OperationPlan.Status.REVIEWED},
            OperationPlan.Status.REVIEWED: set(),
        }
        if target not in allowed[plan.status]:
            return Response({"detail": f"不允许从 {plan.status} 流转到 {target}"}, status=status.HTTP_400_BAD_REQUEST)
        plan.status = target
        if "result" in request.data:
            plan.result = request.data["result"]
        if "review_result" in request.data:
            plan.review_result = request.data["review_result"]
        if target == OperationPlan.Status.COMPLETED:
            plan.completed_at = timezone.now()
        if target == OperationPlan.Status.REVIEWED:
            plan.reviewed_at = timezone.now()
        plan.save()
        return Response(self.get_serializer(plan).data)

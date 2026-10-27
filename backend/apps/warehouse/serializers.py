from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from drf_spectacular.utils import extend_schema_field

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
    OperationPlan,
    OperationStrategy,
    OperationTask,
    ProductCatalog,
    ProductData,
    StrategyAlert,
    StrategyRule,
)
from apps.warehouse.access_control import all_permission_codes, permission_codes_for_user
from apps.warehouse.services.health import calculate_health
from apps.warehouse.services.integrations import validate_outbound_url
from apps.warehouse.services.mcp_sync import ALLOWED_SYNC_INTERVALS, next_scheduled_at
from apps.warehouse.services.mcp import BUSINESS_MCP_TOOL_NAMES, MCP_PERMISSION_CODES, MCP_TOOL_PERMISSION_MAP
from apps.warehouse.services.secrets import encrypt_secret


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    role_name = serializers.SerializerMethodField()
    access_role_id = serializers.SerializerMethodField()
    permission_codes = serializers.SerializerMethodField()
    data_scope = serializers.SerializerMethodField()
    allowed_shops = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    registration_reason = serializers.SerializerMethodField()
    requested_role_code = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()
    approval_status_label = serializers.SerializerMethodField()
    reviewed_by_name = serializers.CharField(source="profile.reviewed_by.username", read_only=True, default="")
    reviewed_at = serializers.DateTimeField(source="profile.reviewed_at", read_only=True, allow_null=True)
    review_note = serializers.CharField(source="profile.review_note", read_only=True, default="")
    registered_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "role", "role_name", "access_role_id",
            "permission_codes", "data_scope", "allowed_shops", "department", "registration_reason",
            "requested_role_code", "is_active",
            "approval_status", "approval_status_label", "reviewed_by_name", "reviewed_at",
            "review_note", "registered_at",
        ]

    @extend_schema_field(serializers.CharField())
    def get_role(self, obj):
        if obj.is_superuser:
            return "owner"
        profile = getattr(obj, "profile", None)
        return getattr(getattr(profile, "access_role", None), "code", None) or getattr(profile, "role", "operator")

    @extend_schema_field(serializers.CharField())
    def get_role_name(self, obj):
        if obj.is_superuser:
            return "所有者"
        profile = getattr(obj, "profile", None)
        role = getattr(profile, "access_role", None)
        return role.name if role else ("管理员" if getattr(profile, "role", "") == "admin" else "运营人员")

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_access_role_id(self, obj):
        return getattr(getattr(obj, "profile", None), "access_role_id", None)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permission_codes(self, obj):
        return sorted(permission_codes_for_user(obj))

    @extend_schema_field(serializers.CharField())
    def get_data_scope(self, obj):
        if obj.is_superuser:
            return AccessRole.DataScope.ALL
        role = getattr(getattr(obj, "profile", None), "access_role", None)
        return role.data_scope if role else AccessRole.DataScope.ALL

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_allowed_shops(self, obj):
        return list(getattr(getattr(obj, "profile", None), "allowed_shops", []) or [])

    def _profile_value(self, obj, name, default=""):
        return getattr(getattr(obj, "profile", None), name, default)

    @extend_schema_field(serializers.CharField())
    def get_department(self, obj):
        return self._profile_value(obj, "department")

    @extend_schema_field(serializers.CharField())
    def get_registration_reason(self, obj):
        return self._profile_value(obj, "registration_reason")

    @extend_schema_field(serializers.CharField())
    def get_requested_role_code(self, obj):
        return self._profile_value(obj, "requested_role_code", "viewer")

    @extend_schema_field(serializers.CharField())
    def get_approval_status(self, obj):
        if obj.is_superuser:
            return AccountProfile.ApprovalStatus.APPROVED
        return getattr(getattr(obj, "profile", None), "approval_status", AccountProfile.ApprovalStatus.APPROVED)

    @extend_schema_field(serializers.CharField())
    def get_approval_status_label(self, obj):
        if obj.is_superuser:
            return AccountProfile.ApprovalStatus.APPROVED.label
        profile = getattr(obj, "profile", None)
        return profile.get_approval_status_display() if profile else AccountProfile.ApprovalStatus.APPROVED.label


class RegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(
        min_length=3,
        max_length=150,
        validators=[RegexValidator(r"^[\w.@+-]+$", "用户名只能包含字母、数字和 @/./+/-/_")],
    )
    display_name = serializers.CharField(min_length=2, max_length=50)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    department = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    requested_role_code = serializers.ChoiceField(choices=[("editor", "编辑者"), ("viewer", "阅读者")], default="viewer")
    registration_reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("该用户名已被使用")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("该邮箱已被使用")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "两次输入的密码不一致"})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data["display_name"],
            email=validated_data.get("email", ""),
            is_active=False,
        )
        AccountProfile.objects.create(
            user=user,
            role=AccountProfile.Role.OPERATOR,
            department=validated_data.get("department", ""),
            requested_role_code=validated_data.get("requested_role_code", "viewer"),
            registration_reason=validated_data.get("registration_reason", ""),
            approval_status=AccountProfile.ApprovalStatus.PENDING,
        )
        return user


class AccountReviewSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    access_role = serializers.PrimaryKeyRelatedField(queryset=AccessRole.objects.filter(is_active=True), required=False, allow_null=True)
    allowed_shops = serializers.ListField(child=serializers.CharField(max_length=150), required=False)

    def validate_access_role(self, value):
        if value and value.code == "owner":
            raise serializers.ValidationError("所有者角色不能通过审批分配")
        return value


class AccountAccessSerializer(serializers.Serializer):
    access_role = serializers.PrimaryKeyRelatedField(queryset=AccessRole.objects.filter(is_active=True))
    allowed_shops = serializers.ListField(child=serializers.CharField(max_length=150), required=False, default=list)

    def validate_access_role(self, value):
        if value.code == "owner":
            raise serializers.ValidationError("所有者角色不能分配给普通账户")
        return value


class AccessRoleSerializer(serializers.ModelSerializer):
    role_type_label = serializers.CharField(source="get_role_type_display", read_only=True)
    data_scope_label = serializers.CharField(source="get_data_scope_display", read_only=True)
    permission_count = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = AccessRole
        fields = "__all__"
        read_only_fields = ["role_type", "created_at", "updated_at"]

    @extend_schema_field(serializers.IntegerField())
    def get_permission_count(self, obj):
        return len(obj.permissions or [])

    def validate_permissions(self, value):
        allowed = all_permission_codes()
        invalid = sorted(set(value or []) - allowed)
        if invalid:
            raise serializers.ValidationError(f"存在未知权限：{', '.join(invalid)}")
        return sorted(set(value or []))

    def validate_code(self, value):
        if self.instance and self.instance.role_type == AccessRole.RoleType.SYSTEM and value != self.instance.code:
            raise serializers.ValidationError("系统角色编码不能修改")
        return value


class AccountTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        user = User.objects.filter(username=attrs.get(self.username_field, "")).select_related("profile").first()
        if user and not user.is_active:
            approval_status = getattr(getattr(user, "profile", None), "approval_status", "")
            if approval_status == AccountProfile.ApprovalStatus.PENDING:
                raise AuthenticationFailed("账号正在等待管理员审批", code="approval_pending")
            if approval_status == AccountProfile.ApprovalStatus.REJECTED:
                raise AuthenticationFailed("账号注册申请未获批准，请联系管理员", code="approval_rejected")
        return super().validate(attrs)


class MCPAccessTokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True)
    owner = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False,
    )
    owner_name = serializers.SerializerMethodField()
    approval_status_label = serializers.CharField(source="get_approval_status_display", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MCPAccessToken
        fields = [
            "id", "name", "agent_name", "agent_platform", "agent_id", "token_prefix", "token",
            "owner", "owner_name", "allowed_tools", "permission_codes", "allowed_shops", "enabled",
            "approval_status", "approval_status_label", "review_note", "reviewed_by_name", "reviewed_at",
            "expires_at", "last_used_at", "created_at",
        ]
        read_only_fields = [
            "token_prefix", "token", "last_used_at", "created_at", "approval_status",
            "approval_status_label", "reviewed_by_name", "reviewed_at",
        ]

    def validate_allowed_tools(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("工具白名单必须是字符串数组")
        invalid = sorted(set(value) - BUSINESS_MCP_TOOL_NAMES)
        if invalid:
            raise serializers.ValidationError(f"存在未开放的 MCP 工具：{', '.join(invalid)}")
        if not value:
            raise serializers.ValidationError("至少选择一个 MCP 工具")
        return sorted(set(value))

    def validate_permission_codes(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("权限编码必须是字符串数组")
        invalid = sorted(set(value) - MCP_PERMISSION_CODES)
        if invalid:
            raise serializers.ValidationError(f"存在未开放的 MCP 权限：{', '.join(invalid)}")
        return sorted(set(value))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "permission_codes" not in attrs:
            tools = attrs.get("allowed_tools", getattr(self.instance, "allowed_tools", []))
            attrs["permission_codes"] = sorted({MCP_TOOL_PERMISSION_MAP[name] for name in tools if name in MCP_TOOL_PERMISSION_MAP})
        return attrs

    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return ""
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username

    def validate_owner(self, value):
        profile = getattr(value, "profile", None)
        if not value.is_superuser and (not profile or profile.approval_status != AccountProfile.ApprovalStatus.APPROVED):
            raise serializers.ValidationError("密钥归属账号必须是已审批通过的账号")
        if "mcp_query.use" not in permission_codes_for_user(value):
            raise serializers.ValidationError("密钥归属账号没有智能体 / MCP 查询权限")
        return value


def prepare_encrypted_secret(validated_data, input_field, encrypted_field):
    """Encrypt before any database write, with an actionable API validation error."""
    value = validated_data.pop(input_field, "")
    if value:
        try:
            validated_data[encrypted_field] = encrypt_secret(value)
        except ValueError as exc:
            raise serializers.ValidationError({input_field: str(exc)}) from exc


class FeishuIntegrationSerializer(serializers.ModelSerializer):
    app_secret = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    has_app_secret = serializers.SerializerMethodField()
    connection_status_label = serializers.CharField(source="get_connection_status_display", read_only=True)

    class Meta:
        model = FeishuIntegration
        exclude = ["app_secret_encrypted"]
        read_only_fields = ["connection_status", "last_tested_at", "last_error", "updated_by"]

    @extend_schema_field(serializers.BooleanField())
    def get_has_app_secret(self, obj):
        return bool(obj.app_secret_encrypted)

    def create(self, validated_data):
        prepare_encrypted_secret(validated_data, "app_secret", "app_secret_encrypted")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        prepare_encrypted_secret(validated_data, "app_secret", "app_secret_encrypted")
        return super().update(instance, validated_data)


class AIProviderConfigSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    has_api_key = serializers.SerializerMethodField()
    provider_label = serializers.CharField(source="get_provider_display", read_only=True)
    connection_status_label = serializers.CharField(source="get_connection_status_display", read_only=True)

    class Meta:
        model = AIProviderConfig
        exclude = ["api_key_encrypted"]
        read_only_fields = ["connection_status", "last_tested_at", "last_error", "updated_by"]

    @extend_schema_field(serializers.BooleanField())
    def get_has_api_key(self, obj):
        return bool(obj.api_key_encrypted)

    def validate_api_base_url(self, value):
        try:
            return validate_outbound_url(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def create(self, validated_data):
        prepare_encrypted_secret(validated_data, "api_key", "api_key_encrypted")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        prepare_encrypted_secret(validated_data, "api_key", "api_key_encrypted")
        return super().update(instance, validated_data)


class MCPServerConfigSerializer(serializers.ModelSerializer):
    auth_token = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    has_auth_token = serializers.SerializerMethodField()
    auth_type_label = serializers.CharField(source="get_auth_type_display", read_only=True)
    connection_status_label = serializers.CharField(source="get_connection_status_display", read_only=True)
    next_scheduled_at = serializers.SerializerMethodField()

    class Meta:
        model = MCPServerConfig
        exclude = ["auth_token_encrypted"]
        read_only_fields = [
            "discovered_tools", "connection_status", "last_tested_at", "last_synced_at", "last_sync_attempted_at",
            "consecutive_sync_failures", "sync_in_progress", "sync_started_at", "last_error", "updated_by",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_auth_token(self, obj):
        return bool(obj.auth_token_encrypted)

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_next_scheduled_at(self, obj):
        return next_scheduled_at(obj)

    def validate(self, attrs):
        endpoint = attrs.get("endpoint_url", getattr(self.instance, "endpoint_url", ""))
        allow_private = attrs.get("allow_private_network", getattr(self.instance, "allow_private_network", False))
        try:
            validate_outbound_url(endpoint, allow_private=allow_private)
        except ValueError as exc:
            raise serializers.ValidationError({"endpoint_url": str(exc)}) from exc
        enabled = attrs.get("enabled", getattr(self.instance, "enabled", False))
        agent_enabled = attrs.get("agent_query_enabled", getattr(self.instance, "agent_query_enabled", False))
        data_sync_enabled = attrs.get("data_sync_enabled", getattr(self.instance, "data_sync_enabled", False))
        schedule_enabled = attrs.get("schedule_enabled", getattr(self.instance, "schedule_enabled", False))
        schedule_interval = attrs.get("schedule_interval_minutes", getattr(self.instance, "schedule_interval_minutes", 120))
        organization_name = attrs.get("organization_name", getattr(self.instance, "organization_name", ""))
        auth_type = attrs.get("auth_type", getattr(self.instance, "auth_type", MCPServerConfig.AuthType.NONE))
        has_token = bool(attrs.get("auth_token") or getattr(self.instance, "auth_token_encrypted", ""))
        allowed_tools = attrs.get("allowed_tools", getattr(self.instance, "allowed_tools", []))
        if agent_enabled and (not enabled or not allowed_tools):
            raise serializers.ValidationError({"agent_query_enabled": "开放给智能体前必须启用服务并选择至少一个只读工具"})
        if not isinstance(allowed_tools, list) or not all(isinstance(item, str) for item in allowed_tools):
            raise serializers.ValidationError({"allowed_tools": "工具白名单必须是字符串数组"})
        if data_sync_enabled:
            if not enabled:
                raise serializers.ValidationError({"data_sync_enabled": "启用一键同步前必须先启用 MCP 服务"})
            if auth_type != MCPServerConfig.AuthType.BEARER or not has_token:
                raise serializers.ValidationError({"auth_token": "经营数据一键同步必须配置 Bearer Token"})
            if not str(organization_name).strip():
                raise serializers.ValidationError({"organization_name": "请填写数据归属企业"})
        if schedule_interval not in ALLOWED_SYNC_INTERVALS:
            raise serializers.ValidationError({"schedule_interval_minutes": "同步频率仅支持 5 分钟、30 分钟、1 小时、2 小时、6 小时或每天"})
        if schedule_enabled and not data_sync_enabled:
            raise serializers.ValidationError({"schedule_enabled": "开启自动同步前必须先启用经营数据一键同步"})
        return attrs

    def create(self, validated_data):
        prepare_encrypted_secret(validated_data, "auth_token", "auth_token_encrypted")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        prepare_encrypted_secret(validated_data, "auth_token", "auth_token_encrypted")
        return super().update(instance, validated_data)


class IntegrationEventLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = IntegrationEventLog
        fields = "__all__"


class ImportBatchSerializer(serializers.ModelSerializer):
    operator_name = serializers.CharField(source="operator.username", read_only=True)

    class Meta:
        model = ImportBatch
        fields = "__all__"
        read_only_fields = ["status", "total_rows", "success_rows", "failed_rows", "error_summary", "operator"]


class ProductDataSerializer(serializers.ModelSerializer):
    health_score = serializers.SerializerMethodField()
    health_components = serializers.SerializerMethodField()
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductData
        fields = [
            "id", "date", "shop", "product_id", "product_name", "sales", "sales_volume", "orders",
            "visitors", "page_views", "impressions", "clicks", "click_rate", "conversion_rate", "ad_cost",
            "ad_revenue", "roi", "profit", "stock", "source", "health_score", "health_components", "updated_at",
            "product_image_url",
        ]

    def _health(self, obj):
        cache = getattr(obj, "_health_cache", None)
        if cache is None:
            cache = calculate_health(obj)
            obj._health_cache = cache
        return cache

    @extend_schema_field(serializers.FloatField())
    def get_health_score(self, obj):
        return self._health(obj)["score"]

    @extend_schema_field(serializers.DictField(child=serializers.FloatField()))
    def get_health_components(self, obj):
        return self._health(obj)["components"]

    def get_product_image_url(self, obj):
        cache = getattr(self, "_product_image_cache", None)
        if cache is None:
            cache = self._product_image_cache = {}
        key = (obj.shop, obj.product_id)
        if key not in cache:
            urls = list(ProductCatalog.objects.filter(
                shop=obj.shop, product_id=obj.product_id,
            ).exclude(product_image_url="").order_by("-updated_at").values_list("product_image_url", flat=True)[:2])
            cache[key] = urls[0] if urls else ""
        return cache[key]


class ProductCatalogSerializer(serializers.ModelSerializer):
    """商品档案序列化器，补充按本地日期计算的生命周期信息。"""

    product_age_days = serializers.SerializerMethodField()
    lifecycle = serializers.SerializerMethodField()
    lifecycle_label = serializers.SerializerMethodField()

    class Meta:
        model = ProductCatalog
        fields = [
            "id", "organization", "platform", "shop_id", "shop", "product_id", "product_name",
            "product_code", "product_created_at", "product_age_days", "lifecycle", "lifecycle_label",
            "product_image_url", "last_seen_month", "source",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def _age_days(obj):
        created_at = getattr(obj, "product_created_at", None)
        if not created_at:
            return None
        # 商品创建日即第 1 天；未来日期按 0 天处理，避免出现负数。
        created_date = timezone.localdate(created_at)
        return max(0, (timezone.localdate() - created_date).days + 1)

    def get_product_age_days(self, obj):
        return self._age_days(obj)

    def get_lifecycle(self, obj):
        age_days = self._age_days(obj)
        if age_days is None or age_days == 0:
            return "unknown"
        return "new" if age_days <= 35 else "mature"

    def get_lifecycle_label(self, obj):
        return {
            "new": "新品",
            "mature": "老品",
            "unknown": "未知",
        }[self.get_lifecycle(obj)]


class AbnormalRecordSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    level_label = serializers.CharField(source="get_level_display", read_only=True)
    product_name = serializers.SerializerMethodField()
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = AbnormalRecord
        fields = "__all__"

    def get_product_name(self, obj):
        return ProductCatalog.objects.filter(shop=obj.shop, product_id=obj.product_id).values_list("product_name", flat=True).first() or obj.product_id

    def get_product_image_url(self, obj):
        return ProductCatalog.objects.filter(shop=obj.shop, product_id=obj.product_id).exclude(product_image_url="").values_list("product_image_url", flat=True).first() or ""


class AIAnalysisRunSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.username", read_only=True)

    class Meta:
        model = AIAnalysisRun
        fields = "__all__"
        read_only_fields = ["requester", "input_context", "output", "provider", "model", "prompt_tokens", "completion_tokens", "cost"]


class AIAnalysisRequestSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", required=False, allow_blank=True, default="")
    shop = serializers.CharField(required=False, allow_blank=True, default="")
    product_id = serializers.CharField(required=False, allow_blank=True, default="")
    question = serializers.CharField(required=False, allow_blank=True, default="")


class OperationTaskSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    abnormal_description = serializers.CharField(source="abnormal_record.description", read_only=True)
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = OperationTask
        fields = "__all__"
        read_only_fields = ["completed_at", "reviewed_at"]

    def get_product_image_url(self, obj):
        if not obj.product_id:
            return ""
        # Tasks do not currently carry a shop scope. Only return an image when
        # the product ID resolves to exactly one image across the tenant.
        urls = set(ProductCatalog.objects.filter(product_id=obj.product_id).exclude(product_image_url="").values_list("product_image_url", flat=True))
        return next(iter(urls)) if len(urls) == 1 else ""


class TaskTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OperationTask.Status.choices)
    result = serializers.CharField(required=False, allow_blank=True)
    review_result = serializers.CharField(required=False, allow_blank=True)


class StrategyRuleSerializer(serializers.ModelSerializer):
    metric_label = serializers.CharField(source="get_metric_display", read_only=True)
    operator_label = serializers.CharField(source="get_operator_display", read_only=True)
    level_label = serializers.CharField(source="get_level_display", read_only=True)

    class Meta:
        model = StrategyRule
        exclude = ["strategy"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        operator = attrs.get("operator", getattr(self.instance, "operator", ""))
        threshold_max = attrs.get("threshold_max", getattr(self.instance, "threshold_max", None))
        if operator == StrategyRule.Operator.BETWEEN and threshold_max is None:
            raise serializers.ValidationError({"threshold_max": "介于规则必须填写上限"})
        return attrs


class OperationStrategySerializer(serializers.ModelSerializer):
    rules = StrategyRuleSerializer(many=True)
    strategy_type_label = serializers.CharField(source="get_strategy_type_display", read_only=True)
    strategy_code_label = serializers.CharField(source="get_strategy_code_display", read_only=True)
    report_mode_label = serializers.CharField(source="get_report_mode_display", read_only=True)
    agent_provider_name = serializers.CharField(source="agent_provider.name", read_only=True, default="")
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default="")

    class Meta:
        model = OperationStrategy
        fields = "__all__"
        read_only_fields = ["created_by", "version", "last_run_at", "last_run_summary"]

    def validate_schedule_hour(self, value):
        if value > 23:
            raise serializers.ValidationError("执行小时必须在 0-23 之间")
        return value

    def validate(self, attrs):
        mode = attrs.get("report_mode", getattr(self.instance, "report_mode", OperationStrategy.ReportMode.SYSTEM))
        provider = attrs.get("agent_provider", getattr(self.instance, "agent_provider", None))
        if mode == OperationStrategy.ReportMode.AGENT and not provider:
            raise serializers.ValidationError({"agent_provider": "选择智能体播报时必须指定一个已配置模型"})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        rules = validated_data.pop("rules", [])
        if not rules:
            raise serializers.ValidationError({"rules": "至少配置一条预警规则"})
        strategy = OperationStrategy.objects.create(**validated_data)
        StrategyRule.objects.bulk_create([StrategyRule(strategy=strategy, **item) for item in rules])
        return strategy

    @transaction.atomic
    def update(self, instance, validated_data):
        rules = validated_data.pop("rules", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if rules is not None:
            if not rules:
                raise serializers.ValidationError({"rules": "至少配置一条预警规则"})
            instance.rules.all().delete()
            StrategyRule.objects.bulk_create([StrategyRule(strategy=instance, **item) for item in rules])
            instance.version += 1
        instance.save()
        return instance


class StrategyAlertSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    metric_label = serializers.CharField(source="rule.get_metric_display", read_only=True)
    level_label = serializers.CharField(source="get_level_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = StrategyAlert
        fields = "__all__"
        read_only_fields = [
            "strategy", "rule", "product_fact", "month", "organization", "platform", "shop",
            "product_id", "product_name", "product_url", "operator_name", "metric", "observed_value",
            "threshold_snapshot", "level", "title", "description", "suggestion", "agent_report",
            "reporter_name", "first_triggered_at", "last_triggered_at",
        ]

    def get_product_image_url(self, obj):
        if obj.product_catalog_id and obj.product_catalog:
            return obj.product_catalog.product_image_url or ""
        if obj.product_fact_id and obj.product_fact:
            return obj.product_fact.product_image_url or ""
        return ""


class OperationPlanSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source="strategy.name", read_only=True, default="")
    owner_name = serializers.CharField(source="owner.username", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    product_image_url = serializers.SerializerMethodField()

    class Meta:
        model = OperationPlan
        fields = "__all__"
        read_only_fields = ["created_by", "completed_at", "reviewed_at"]

    def get_product_image_url(self, obj):
        alert = getattr(obj, "alert", None)
        if alert:
            catalog = getattr(alert, "product_catalog", None)
            fact = getattr(alert, "product_fact", None)
            if catalog and catalog.product_image_url:
                return catalog.product_image_url
            if fact and fact.product_image_url:
                return fact.product_image_url
        return ""


class FeishuImportSerializer(serializers.Serializer):
    url = serializers.URLField(required=False, allow_blank=True, default="")
    data_type = serializers.ChoiceField(choices=["product", "paid", "shop"])
    shop = serializers.CharField(required=False, allow_blank=False, default="默认店铺")
    run_detection = serializers.BooleanField(required=False, default=True)

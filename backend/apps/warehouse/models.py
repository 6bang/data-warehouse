from django.contrib.auth.models import User
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AccessRole(TimestampedModel):
    class RoleType(models.TextChoices):
        SYSTEM = "system", "系统角色"
        CUSTOM = "custom", "自定义角色"

    class DataScope(models.TextChoices):
        ALL = "all", "全部店铺"
        ASSIGNED = "assigned", "指定店铺"

    name = models.CharField(max_length=50)
    code = models.SlugField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    role_type = models.CharField(max_length=16, choices=RoleType.choices, default=RoleType.CUSTOM)
    data_scope = models.CharField(max_length=16, choices=DataScope.choices, default=DataScope.ASSIGNED)
    permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        db_table = "access_role"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class AccountProfile(TimestampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        OPERATOR = "operator", "运营人员"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "待审批"
        APPROVED = "approved", "已批准"
        REJECTED = "rejected", "已拒绝"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.OPERATOR)
    access_role = models.ForeignKey(
        AccessRole,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    department = models.CharField(max_length=100, blank=True)
    registration_reason = models.CharField(max_length=500, blank=True)
    requested_role_code = models.CharField(max_length=50, blank=True, default="viewer")
    allowed_shops = models.JSONField(default=list, blank=True)
    approval_status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED)
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_accounts",
    )
    # Feishu OAuth identity.  open_id is scoped to the Feishu app and is the
    # stable identifier used for login; email/mobile are deliberately not used
    # as authentication identifiers.
    feishu_open_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    feishu_union_id = models.CharField(max_length=100, blank=True)
    feishu_user_id = models.CharField(max_length=100, blank=True)
    feishu_tenant_key = models.CharField(max_length=100, blank=True)
    feishu_last_login_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}:{self.role}"


class ConnectionStatus(models.TextChoices):
    UNTESTED = "untested", "未测试"
    CONNECTED = "connected", "已连接"
    ERROR = "error", "连接失败"


class FeishuIntegration(TimestampedModel):
    name = models.CharField(max_length=100, default="飞书经营数据")
    app_id = models.CharField(max_length=100, blank=True)
    app_secret_encrypted = models.TextField(blank=True)
    allowed_tenant_keys = models.CharField(max_length=500, blank=True)
    default_base_url = models.URLField(max_length=1000, blank=True)
    enabled = models.BooleanField(default=False)
    connection_status = models.CharField(max_length=16, choices=ConnectionStatus.choices, default=ConnectionStatus.UNTESTED)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_feishu_integrations")

    class Meta:
        db_table = "feishu_integration"


class AIProviderConfig(TimestampedModel):
    class Provider(models.TextChoices):
        DEEPSEEK = "deepseek", "DeepSeek"
        OPENAI = "openai", "OpenAI"
        CUSTOM = "custom", "OpenAI 兼容服务"

    name = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.DEEPSEEK)
    api_base_url = models.URLField(max_length=500)
    model = models.CharField(max_length=100)
    api_key_encrypted = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    connection_status = models.CharField(max_length=16, choices=ConnectionStatus.choices, default=ConnectionStatus.UNTESTED)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_ai_providers")

    class Meta:
        db_table = "ai_provider_config"
        ordering = ["-is_default", "name"]


class MCPServerConfig(TimestampedModel):
    class AuthType(models.TextChoices):
        NONE = "none", "无认证"
        BEARER = "bearer", "Bearer Token"

    name = models.CharField(max_length=100, unique=True)
    endpoint_url = models.URLField(max_length=1000)
    auth_type = models.CharField(max_length=16, choices=AuthType.choices, default=AuthType.NONE)
    auth_token_encrypted = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    agent_query_enabled = models.BooleanField(default=False)
    data_sync_enabled = models.BooleanField(default=False)
    organization_name = models.CharField(max_length=150, blank=True)
    schedule_enabled = models.BooleanField(default=False)
    schedule_interval_minutes = models.PositiveSmallIntegerField(default=120)
    allow_private_network = models.BooleanField(default=False)
    allowed_tools = models.JSONField(default=list, blank=True)
    discovered_tools = models.JSONField(default=list, blank=True)
    protocol_version = models.CharField(max_length=20, default="2025-06-18")
    connection_status = models.CharField(max_length=16, choices=ConnectionStatus.choices, default=ConnectionStatus.UNTESTED)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_attempted_at = models.DateTimeField(null=True, blank=True)
    consecutive_sync_failures = models.PositiveSmallIntegerField(default=0)
    sync_in_progress = models.BooleanField(default=False)
    sync_started_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="updated_mcp_servers")

    class Meta:
        db_table = "mcp_server_config"
        ordering = ["name"]


class MCPAccessToken(TimestampedModel):
    """A revocable, least-privilege token for an external Agent MCP client."""

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "待审核"
        APPROVED = "approved", "已通过"
        REJECTED = "rejected", "已驳回"

    name = models.CharField(max_length=100)
    agent_name = models.CharField(max_length=120, blank=True)
    agent_platform = models.CharField(max_length=30, default="feishu")
    agent_id = models.CharField(max_length=160, blank=True)
    token_prefix = models.CharField(max_length=20)
    token_hash = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="mcp_access_tokens")
    allowed_tools = models.JSONField(default=list, blank=True)
    permission_codes = models.JSONField(default=list, blank=True)
    allowed_shops = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    approval_status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED)
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_mcp_access_tokens")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_mcp_access_tokens")

    class Meta:
        db_table = "mcp_access_token"
        ordering = ["-created_at", "id"]


class IntegrationEventLog(models.Model):
    integration_type = models.CharField(max_length=20)
    integration_id = models.PositiveBigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=50)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="integration_events")
    ai_analysis_run = models.ForeignKey("AIAnalysisRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="integration_events")
    success = models.BooleanField(default=True)
    duration_ms = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integration_event_log"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["integration_type", "created_at"], name="integration_integra_fb411b_idx")]


class ImportBatch(TimestampedModel):
    class Source(models.TextChoices):
        EXCEL = "excel", "Excel/CSV"
        FEISHU = "feishu", "飞书多维表格"
        API = "api", "API"

    class Status(models.TextChoices):
        PENDING = "pending", "等待中"
        PROCESSING = "processing", "处理中"
        SUCCEEDED = "succeeded", "成功"
        PARTIAL = "partial", "部分成功"
        FAILED = "failed", "失败"

    source = models.CharField(max_length=16, choices=Source.choices)
    data_type = models.CharField(max_length=16, default="product")
    source_name = models.CharField(max_length=500, blank=True)
    shop = models.CharField(max_length=100, default="默认店铺")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=list, blank=True)
    operator = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_batches")

    class Meta:
        db_table = "import_batch"
        ordering = ["-created_at"]


class ProductData(TimestampedModel):
    class RecordType(models.TextChoices):
        PRODUCT = "product", "商品"
        SHOP_SUMMARY = "shop_summary", "店铺汇总"

    id = models.BigAutoField(primary_key=True)
    date = models.DateField(db_index=True)
    shop = models.CharField(max_length=100, default="默认店铺")
    product_id = models.CharField(max_length=100)
    product_name = models.CharField(max_length=255, blank=True)
    record_type = models.CharField(max_length=16, choices=RecordType.choices, default=RecordType.PRODUCT)
    sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sales_volume = models.PositiveIntegerField(default=0)
    orders = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)
    page_views = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    click_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    conversion_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    ad_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ad_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    roi = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True)
    source = models.CharField(max_length=20, default="excel")
    import_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="product_rows")
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "product_data"
        constraints = [models.UniqueConstraint(fields=["date", "shop", "product_id"], name="uniq_product_day_shop")]
        indexes = [models.Index(fields=["shop", "date"]), models.Index(fields=["product_id", "date"])]
        ordering = ["-date", "-sales"]

    def __str__(self):
        return f"{self.date} {self.shop} {self.product_id}"


class MonthlyProductFact(TimestampedModel):
    """平台官方导出/API 形成的商品月度事实，和日粒度 ProductData 严格隔离。"""

    id = models.BigAutoField(primary_key=True)
    organization = models.CharField(max_length=150, db_index=True)
    month = models.CharField(max_length=7, db_index=True)
    platform = models.CharField(max_length=50, blank=True, default="未识别平台")
    shop_id = models.CharField(max_length=100, blank=True)
    shop = models.CharField(max_length=150, blank=True, default="未识别店铺")
    category_path = models.CharField(max_length=500, blank=True, default="未分类")
    product_id = models.CharField(max_length=150)
    product_name = models.CharField(max_length=500, blank=True)
    product_code = models.CharField(max_length=150, blank=True)
    product_image_url = models.URLField(max_length=1000, blank=True)
    product_created_at = models.DateTimeField(null=True, blank=True)
    operator_id = models.CharField(max_length=100, blank=True)
    operator_name = models.CharField(max_length=100, blank=True, default="未分配运营")
    product_cost = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    gross_sales = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    sales = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    sales_volume = models.PositiveIntegerField(default=0)
    net_sales = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    orders = models.PositiveIntegerField(default=0)
    visitors = models.PositiveIntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    ad_cost = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    ad_revenue = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    gross_profit = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    net_profit = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=50, default="excel_export")
    source_name = models.CharField(max_length=500, blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "monthly_product_fact"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "month", "platform", "shop", "product_id"],
                name="uniq_monthly_product_scope",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "month"], name="month_fact_org_month_idx"),
            models.Index(fields=["platform", "shop"], name="month_fact_platform_shop_idx"),
            models.Index(fields=["category_path"], name="month_fact_category_idx"),
            models.Index(fields=["operator_name"], name="month_fact_operator_idx"),
        ]
        ordering = ["-month", "-sales"]

    def __str__(self):
        return f"{self.organization} {self.month} {self.platform}/{self.shop} {self.product_id}"


class ProductCatalog(TimestampedModel):
    """商品主档案：与按月经营事实分离，保存商品身份和创建信息。"""

    id = models.BigAutoField(primary_key=True)
    organization = models.CharField(max_length=150, db_index=True)
    platform = models.CharField(max_length=50, blank=True, default="未识别平台")
    shop_id = models.CharField(max_length=100, blank=True)
    shop = models.CharField(max_length=150, blank=True, default="未识别店铺")
    product_id = models.CharField(max_length=150)
    product_name = models.CharField(max_length=500, blank=True)
    product_code = models.CharField(max_length=150, blank=True)
    product_created_at = models.DateTimeField(null=True, blank=True)
    product_image_url = models.URLField(max_length=1000, blank=True)
    last_seen_month = models.CharField(max_length=7, blank=True)
    source = models.CharField(max_length=50, default="monthly_product_fact")
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "product_catalog"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "shop", "product_id"],
                name="uniq_product_catalog_scope",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "product_name"], name="product_catalog_org_name_idx"),
            models.Index(fields=["product_created_at"], name="product_catalog_created_idx"),
            models.Index(fields=["shop", "product_id"], name="prod_catalog_shop_prod_idx"),
        ]
        ordering = ["-product_created_at", "product_name", "product_id"]

    def __str__(self):
        return f"{self.product_name or self.product_id} ({self.product_code})"


class DataSyncJob(TimestampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing", "处理中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"

    organization = models.CharField(max_length=150, db_index=True)
    source_system = models.CharField(max_length=50)
    data_scope = models.CharField(max_length=50, default="monthly_product")
    period = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROCESSING)
    source_name = models.CharField(max_length=500, blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=1000, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "data_sync_job"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "period"], name="sync_job_org_period_idx")]


class AbnormalRecord(TimestampedModel):
    class Type(models.TextChoices):
        SALES = "sales", "销售下降"
        TRAFFIC = "traffic", "流量下降"
        CONVERSION = "conversion", "转化下降"
        AD = "ad", "广告异常"
        STOCK = "stock", "库存风险"

    class Level(models.TextChoices):
        INFO = "info", "提示"
        WARNING = "warning", "警告"
        CRITICAL = "critical", "严重"

    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        ACKNOWLEDGED = "acknowledged", "已确认"
        RESOLVED = "resolved", "已解决"

    date = models.DateField(db_index=True)
    product_data = models.ForeignKey(ProductData, null=True, blank=True, on_delete=models.SET_NULL, related_name="abnormal_records")
    shop = models.CharField(max_length=100, default="默认店铺")
    product_id = models.CharField(max_length=100, blank=True)
    type = models.CharField(max_length=16, choices=Type.choices)
    metric = models.CharField(max_length=50)
    description = models.CharField(max_length=500)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.WARNING)
    current_value = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    baseline_value = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    change_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    ai_analysis = models.TextField(blank=True)
    suggestion = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    class Meta:
        db_table = "abnormal_record"
        constraints = [models.UniqueConstraint(fields=["date", "shop", "product_id", "type", "metric"], name="uniq_abnormal_metric")]
        ordering = ["-date", "level"]


class AIAnalysisRun(TimestampedModel):
    requester = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_analysis_runs")
    date = models.DateField(null=True, blank=True)
    month = models.CharField(max_length=7, blank=True)
    shop = models.CharField(max_length=100, blank=True)
    product_id = models.CharField(max_length=100, blank=True)
    question = models.TextField(blank=True)
    input_context = models.JSONField(default=dict)
    output = models.JSONField(default=dict)
    provider = models.CharField(max_length=32, default="rules")
    model = models.CharField(max_length=100, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    accepted = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = "ai_analysis_run"
        ordering = ["-created_at"]


class OperationTask(TimestampedModel):
    class Source(models.TextChoices):
        AI = "ai", "AI 分析"
        ABNORMAL = "abnormal", "异常分析"
        MANUAL = "manual", "人工创建"

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        IN_PROGRESS = "in_progress", "执行中"
        COMPLETED = "completed", "已完成"
        REVIEWED = "reviewed", "已复盘"

    task_name = models.CharField(max_length=200)
    product_id = models.CharField(max_length=100, blank=True)
    problem = models.TextField(blank=True)
    ai_suggestion = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    abnormal_record = models.ForeignKey(AbnormalRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    ai_analysis_run = models.ForeignKey(AIAnalysisRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="operation_tasks")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    deadline = models.DateTimeField(null=True, blank=True)
    result = models.TextField(blank=True)
    review_result = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "task"
        ordering = ["status", "deadline", "-created_at"]


class OperationStrategy(TimestampedModel):
    class StrategyType(models.TextChoices):
        NEW_PRODUCT = "new_product", "新品策略"
        MATURE_PRODUCT = "mature_product", "老品策略"
        ALL_PRODUCT = "all_product", "全量商品策略"

    class ReportMode(models.TextChoices):
        SYSTEM = "system", "系统规则播报"
        AGENT = "agent", "智能体播报"

    class StrategyCode(models.TextChoices):
        STANDARD = "standard", "通用规则"
        NEW_PRODUCT_35D = "new_product_35d", "新品 35 天分级策略"
        MATURE_PRODUCT_30D = "mature_product_30d", "老品近 30 天分级策略"

    name = models.CharField(max_length=200)
    strategy_type = models.CharField(max_length=24, choices=StrategyType.choices, default=StrategyType.NEW_PRODUCT)
    strategy_code = models.CharField(max_length=32, choices=StrategyCode.choices, default=StrategyCode.STANDARD)
    description = models.TextField(blank=True)
    organization = models.CharField(max_length=150, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    shop = models.CharField(max_length=150, blank=True)
    category_path = models.CharField(max_length=500, blank=True)
    new_product_days = models.PositiveSmallIntegerField(default=30)
    report_mode = models.CharField(max_length=16, choices=ReportMode.choices, default=ReportMode.SYSTEM)
    agent_provider = models.ForeignKey(
        AIProviderConfig, null=True, blank=True, on_delete=models.SET_NULL, related_name="operation_strategies"
    )
    enabled = models.BooleanField(default=True)
    schedule_enabled = models.BooleanField(default=True)
    schedule_hour = models.PositiveSmallIntegerField(default=7)
    version = models.PositiveIntegerField(default=1)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_operation_strategies")

    class Meta:
        db_table = "operation_strategy"
        ordering = ["-enabled", "strategy_type", "name"]


class StrategyRule(TimestampedModel):
    class Metric(models.TextChoices):
        SALES = "sales", "成交金额"
        ORDERS = "orders", "订单数"
        REFUND_AMOUNT = "refund_amount", "退款金额"
        REFUND_RATE = "refund_rate", "退款率"
        AD_COST = "ad_cost", "广告花费"
        ROI = "roi", "广告 ROI"
        GROSS_PROFIT = "gross_profit", "毛利润"
        GROSS_MARGIN = "gross_margin", "毛利率"
        NET_PROFIT = "net_profit", "净利润"
        NET_MARGIN = "net_margin", "净利率"
        PRODUCT_AGE_DAYS = "product_age_days", "商品上架天数"
        CONVERSION_RATE = "conversion_rate", "转化率"
        CUMULATIVE_35D_SALES = "cumulative_35d_sales", "新品 35 天累计销量"
        DAILY_SALES_VOLUME = "daily_sales_volume", "日销量"
        WEEKLY_SALES_VOLUME = "weekly_sales_volume", "周销量"
        RECENT_30D_SALES = "recent_30d_sales", "近 30 天销量"

    class Operator(models.TextChoices):
        LT = "lt", "小于"
        LTE = "lte", "小于等于"
        GT = "gt", "大于"
        GTE = "gte", "大于等于"
        EQ = "eq", "等于"
        BETWEEN = "between", "介于"

    class Level(models.TextChoices):
        INFO = "info", "提示"
        WARNING = "warning", "警告"
        CRITICAL = "critical", "严重"

    strategy = models.ForeignKey(OperationStrategy, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=200)
    metric = models.CharField(max_length=32, choices=Metric.choices)
    operator = models.CharField(max_length=16, choices=Operator.choices, default=Operator.LT)
    threshold = models.DecimalField(max_digits=18, decimal_places=4)
    threshold_max = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    weekly_threshold = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    stage = models.CharField(max_length=16, blank=True, default="")
    product_grade = models.CharField(max_length=2, blank=True, default="")
    conversion_band = models.CharField(max_length=16, blank=True, default="")
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.WARNING)
    message_template = models.CharField(max_length=500, blank=True)
    suggestion = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "strategy_rule"
        ordering = ["strategy_id", "id"]


class StrategyAlert(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        ACKNOWLEDGED = "acknowledged", "已确认"
        CONVERTED = "converted", "已转计划"
        RESOLVED = "resolved", "已解除"

    strategy = models.ForeignKey(OperationStrategy, on_delete=models.CASCADE, related_name="alerts")
    rule = models.ForeignKey(StrategyRule, on_delete=models.CASCADE, related_name="alerts")
    product_fact = models.ForeignKey(MonthlyProductFact, null=True, blank=True, on_delete=models.CASCADE, related_name="strategy_alerts")
    product_catalog = models.ForeignKey(ProductCatalog, null=True, blank=True, on_delete=models.CASCADE, related_name="strategy_alerts")
    evaluation_date = models.DateField(null=True, blank=True, db_index=True)
    month = models.CharField(max_length=7, db_index=True)
    organization = models.CharField(max_length=150)
    platform = models.CharField(max_length=50, blank=True)
    shop = models.CharField(max_length=150, blank=True)
    product_id = models.CharField(max_length=150)
    product_name = models.CharField(max_length=500, blank=True)
    product_url = models.URLField(max_length=1000, blank=True)
    operator_name = models.CharField(max_length=100, blank=True)
    metric = models.CharField(max_length=32)
    observed_value = models.DecimalField(max_digits=18, decimal_places=4)
    threshold_snapshot = models.JSONField(default=dict)
    level = models.CharField(max_length=16, choices=StrategyRule.Level.choices, default=StrategyRule.Level.WARNING)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    suggestion = models.TextField(blank=True)
    agent_report = models.TextField(blank=True)
    reporter_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    first_triggered_at = models.DateTimeField(auto_now_add=True)
    last_triggered_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "strategy_alert"
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "rule", "product_fact", "month"], name="uniq_strategy_alert_fact"
            ),
            models.UniqueConstraint(
                fields=["strategy", "rule", "product_catalog", "evaluation_date"], name="uniq_strategy_alert_catalog_day"
            ),
        ]
        indexes = [models.Index(fields=["month", "status", "level"], name="strategy_alert_month_idx")]
        ordering = ["status", "-level", "-last_triggered_at"]


class OperationPlan(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待执行"
        IN_PROGRESS = "in_progress", "执行中"
        COMPLETED = "completed", "已完成"
        REVIEWED = "reviewed", "已复盘"

    plan_name = models.CharField(max_length=200)
    strategy = models.ForeignKey(OperationStrategy, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans")
    alert = models.OneToOneField(StrategyAlert, null=True, blank=True, on_delete=models.SET_NULL, related_name="plan")
    organization = models.CharField(max_length=150, blank=True)
    shop = models.CharField(max_length=150, blank=True)
    product_id = models.CharField(max_length=150, blank=True)
    product_name = models.CharField(max_length=500, blank=True)
    product_url = models.URLField(max_length=1000, blank=True)
    objective = models.TextField(blank=True)
    actions = models.TextField(blank=True)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="operation_plans")
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    result = models.TextField(blank=True)
    review_result = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_operation_plans")
    completed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "operation_plan"
        ordering = ["status", "deadline", "-created_at"]

from django.contrib import admin

from apps.warehouse.models import (
    AccessRole,
    AbnormalRecord,
    AccountProfile,
    AIAnalysisRun,
    AIProviderConfig,
    FeishuIntegration,
    ImportBatch,
    IntegrationEventLog,
    MCPServerConfig,
    MonthlyProductFact,
    DataSyncJob,
    OperationTask,
    OperationPlan,
    OperationStrategy,
    ProductData,
    StrategyAlert,
    StrategyRule,
)


@admin.register(AccessRole)
class AccessRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "role_type", "data_scope", "is_active", "sort_order")
    list_filter = ("role_type", "data_scope", "is_active")
    search_fields = ("name", "code")


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "access_role", "role", "department", "approval_status", "reviewed_by", "reviewed_at", "created_at")
    list_filter = ("access_role", "role", "approval_status")
    search_fields = ("user__username", "user__first_name", "user__email")


@admin.register(ProductData)
class ProductDataAdmin(admin.ModelAdmin):
    list_display = ("date", "shop", "product_id", "product_name", "sales", "visitors", "ad_cost", "roi")
    list_filter = ("date", "shop", "source")
    search_fields = ("product_id", "product_name")


admin.site.register(ImportBatch)
admin.site.register(AbnormalRecord)
admin.site.register(AIAnalysisRun)
admin.site.register(OperationTask)
admin.site.register(FeishuIntegration)
admin.site.register(AIProviderConfig)
admin.site.register(MCPServerConfig)
admin.site.register(IntegrationEventLog)
admin.site.register(OperationStrategy)
admin.site.register(StrategyRule)
admin.site.register(StrategyAlert)
admin.site.register(OperationPlan)


@admin.register(MonthlyProductFact)
class MonthlyProductFactAdmin(admin.ModelAdmin):
    list_display = ("month", "organization", "platform", "shop", "product_id", "sales", "orders", "gross_profit")
    list_filter = ("month", "organization", "platform", "shop", "operator_name")
    search_fields = ("product_id", "product_name", "category_path")


@admin.register(DataSyncJob)
class DataSyncJobAdmin(admin.ModelAdmin):
    list_display = ("created_at", "organization", "source_system", "period", "status", "success_rows", "failed_rows")
    list_filter = ("status", "source_system", "organization", "period")

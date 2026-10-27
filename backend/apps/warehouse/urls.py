from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.warehouse.views import (
    AbnormalRecordViewSet,
    AccessRoleViewSet,
    AccountViewSet,
    AIProviderConfigViewSet,
    AIAnalysisViewSet,
    BusinessDimensionsView,
    BusinessMCPView,
    DashboardView,
    ConfigurationSummaryView,
    FeishuIntegrationViewSet,
    ImportBatchViewSet,
    IntegrationEventLogViewSet,
    MCPServerConfigViewSet,
    MCPAccessTokenViewSet,
    MCPDataSyncView,
    MeView,
    FeishuLoginCallbackView,
    FeishuLoginExchangeView,
    FeishuLoginStartView,
    OperationTaskViewSet,
    ProductCatalogViewSet,
    ProductDataViewSet,
    RegistrationView,
    RealtimeDashboardView,
    ShopMonthlyView,
    MonthlyBusinessView,
    OperationPlanViewSet,
    OperationStrategyViewSet,
    StrategyAlertViewSet,
    StrategyOptionsView,
)

router = DefaultRouter()
router.register("products", ProductDataViewSet, basename="product")
router.register("product-catalog", ProductCatalogViewSet, basename="product-catalog")
router.register("abnormal-records", AbnormalRecordViewSet, basename="abnormal-record")
router.register("imports", ImportBatchViewSet, basename="import")
router.register("ai-analysis", AIAnalysisViewSet, basename="ai-analysis")
router.register("tasks", OperationTaskViewSet, basename="task")
router.register("operation-strategies", OperationStrategyViewSet, basename="operation-strategy")
router.register("strategy-alerts", StrategyAlertViewSet, basename="strategy-alert")
router.register("operation-plans", OperationPlanViewSet, basename="operation-plan")
router.register("accounts", AccountViewSet, basename="account")
router.register("access-roles", AccessRoleViewSet, basename="access-role")
router.register("configuration/feishu", FeishuIntegrationViewSet, basename="configuration-feishu")
router.register("configuration/ai-providers", AIProviderConfigViewSet, basename="configuration-ai-provider")
router.register("configuration/mcp-servers", MCPServerConfigViewSet, basename="configuration-mcp-server")
router.register("configuration/mcp-tokens", MCPAccessTokenViewSet, basename="configuration-mcp-token")
router.register("configuration/events", IntegrationEventLogViewSet, basename="configuration-event")

urlpatterns = [
    path("auth/register/", RegistrationView.as_view(), name="register"),
    path("auth/feishu/start/", FeishuLoginStartView.as_view(), name="feishu-login-start"),
    path("auth/feishu/callback/", FeishuLoginCallbackView.as_view(), name="feishu-login-callback"),
    path("auth/feishu/exchange/", FeishuLoginExchangeView.as_view(), name="feishu-login-exchange"),
    path("users/me/", MeView.as_view(), name="me"),
    path("configuration/summary/", ConfigurationSummaryView.as_view(), name="configuration-summary"),
    path("data-sync/mcp/", MCPDataSyncView.as_view(), name="mcp-data-sync"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/realtime/", RealtimeDashboardView.as_view(), name="realtime-dashboard"),
    path("shops/monthly/", ShopMonthlyView.as_view(), name="shops-monthly"),
    path("business/dimensions/", BusinessDimensionsView.as_view(), name="business-dimensions"),
    path("business/monthly/", MonthlyBusinessView.as_view(), name="business-monthly"),
    path("strategy-options/", StrategyOptionsView.as_view(), name="strategy-options"),
    path("mcp/business/", BusinessMCPView.as_view(), name="business-mcp"),
] + router.urls

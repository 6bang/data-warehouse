export interface Metric { value: number | null; change_rate: number | null }
export interface DashboardData {
  month: string | null
  previous_month: string | null
  comparison_label?: string
  is_partial?: boolean
  data_through?: string | null
  available_months: string[]
  metrics: Record<string, Metric>
  monthly_trend: Array<{ month: string; sales: number; ad_cost: number; profit: number | null; roi: number }>
  daily_trend: Array<{ date: string; sales: number; visitors: number; ad_cost: number; roi: number }>
  abnormal: AbnormalRecord[]
  abnormal_count: number
  task_summary: Record<string, number>
}
export interface RealtimeMetric {
  label: string
  format: 'money' | 'percent' | 'int' | 'decimal'
  current: number | null
  compare: number | null
  change_rate: number | null
}
export interface RealtimeStoreOption { store_id: string; store_name: string; platform_type: string; platform_name: string }
export interface RealtimeDashboardData {
  date: string
  compare_date: string
  data_through: string
  source: { name: string; status: 'live' | 'limited'; warning: string }
  available_shops: RealtimeStoreOption[]
  metrics: Record<string, RealtimeMetric>
  hourly_trend: {
    available: boolean
    hours: number[]
    previous: number[]
    current: Array<{ store_id: string; store_name: string; values: number[] }>
    warning: string
  }
  trend_granularity: 'hour'
  rankings: {
    shop: Array<Record<string, string | number | null>>
    item: Array<Record<string, string | number | null>>
    platform_type: Array<Record<string, string | number | null>>
    sku_code: Array<Record<string, string | number | null>>
    op_manager: Array<Record<string, string | number | null>>
  }
}
export interface AbnormalRecord { id: number; date?: string; type: string; level: string; product_id: string; product_name?: string; product_image_url?: string; description: string; suggestion: string }
export interface ProductData {
  id: number | string; date?: string; month?: string; shop: string; product_id: string; product_name: string
  product_image_url?: string
  sales: string; sales_volume: number; orders: number; visitors: number; click_rate: string
  conversion_rate: string; ad_cost: string; roi: string; profit: string | null; stock: number | null
  health_score: number; health_components: Record<string, number>
}
export interface ProductCatalog {
  id: number; organization: string; platform: string; shop_id: string; shop: string
  product_id: string; product_name: string; product_code: string; product_created_at: string | null
  product_age_days?: number | null; lifecycle?: 'new' | 'mature' | 'unknown'; lifecycle_label?: string
  product_image_url?: string; last_seen_month: string; source: string; created_at: string; updated_at: string
}
export interface ShopData {
  id: string; month: string; shop: string; sales: number; sales_volume: number; orders: number
  visitors: number; conversion_rate: number; ad_cost: number; ad_revenue: number; roi: number
  profit: number | null; profit_rate: number | null; sales_change_rate: number | null
  visitors_change_rate: number | null
}
export interface Task {
  id: number; task_name: string; product_id: string; problem: string; ai_suggestion: string
  product_image_url?: string
  source: string; owner: number | null; owner_name: string; status: string; status_label: string
  deadline: string | null; result: string; review_result: string
}
export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] }
export interface Account {
  id: number; username: string; first_name: string; email: string; role: string; role_name: string
  access_role_id: number | null; permission_codes: string[]; data_scope: 'all' | 'assigned'; allowed_shops: string[]
  department: string; registration_reason: string; requested_role_code: string
  is_active: boolean; approval_status: 'pending' | 'approved' | 'rejected'; approval_status_label: string
  reviewed_by_name: string; reviewed_at: string | null; review_note: string; registered_at: string
}
export interface AccessRole {
  id: number; name: string; code: string; description: string; role_type: 'system' | 'custom'; role_type_label: string
  data_scope: 'all' | 'assigned'; data_scope_label: string; permissions: string[]; permission_count: number
  member_count: number; is_active: boolean; sort_order: number
}
export interface PermissionAction { code: string; name: string; permission: string }
export interface PermissionModule { code: string; name: string; actions: PermissionAction[] }
export interface PermissionGroup { code: string; name: string; modules: PermissionModule[] }
export interface FeishuConfig {
  id?: number; name: string; app_id: string; app_secret?: string; has_app_secret: boolean
  allowed_tenant_keys: string
  default_base_url: string; enabled: boolean; connection_status: string; connection_status_label: string
  last_tested_at: string | null; last_error: string
}
export interface AIProviderConfig {
  id?: number; name: string; provider: 'deepseek' | 'openai' | 'custom'; provider_label?: string
  api_base_url: string; model: string; api_key?: string; has_api_key: boolean; enabled: boolean; is_default: boolean
  connection_status: string; connection_status_label?: string; last_tested_at: string | null; last_error: string
}
export interface MCPTool { name: string; description: string; inputSchema: Record<string, unknown> }
export interface MCPServerConfig {
  id?: number; name: string; endpoint_url: string; auth_type: 'none' | 'bearer'; auth_token?: string
  has_auth_token: boolean; enabled: boolean; agent_query_enabled: boolean; allow_private_network: boolean
  data_sync_enabled: boolean; organization_name: string; last_synced_at: string | null
  schedule_enabled: boolean; schedule_interval_minutes: number; next_scheduled_at: string | null
  last_sync_attempted_at: string | null; consecutive_sync_failures: number; sync_in_progress: boolean; sync_started_at: string | null
  allowed_tools: string[]; discovered_tools: MCPTool[]; protocol_version: string
  connection_status: string; connection_status_label?: string; last_tested_at: string | null; last_error: string
}
export interface MCPAccessToken {
  id?: number; name: string; agent_name: string; agent_platform: string; agent_id: string
  token_prefix: string; token?: string; owner?: number; owner_name?: string
  allowed_tools: string[]; permission_codes: string[]; allowed_shops: string[]; enabled: boolean
  approval_status: 'pending' | 'approved' | 'rejected'; approval_status_label?: string; review_note: string
  reviewed_by_name?: string; reviewed_at: string | null; expires_at: string | null
  last_used_at: string | null; created_at: string
}
export interface IntegrationEvent {
  id: number; integration_type: string; action: string; actor_name: string; success: boolean
  duration_ms: number; detail: Record<string, unknown>; error: string; created_at: string
}
export interface BusinessDimensions {
  organizations: string[]; months: string[]; platforms: string[]; shops: string[]; categories: string[]; operators: string[]
  selected: { organization: string; month: string }
  coverage: { available: string[]; unavailable: string[]; source: string }
  latest_sync: { status: string; rows: number; finished_at: string; source_name: string } | null
}
export interface BusinessMetricRow {
  platform?: string; shop?: string; category_path?: string; product_id?: string; product_name?: string
  product_image_url?: string; operator_name?: string; products: number; sales: number; gross_sales: number | null
  net_sales: number | null; sales_volume?: number; orders: number; visitors?: number; stock?: number | null; refund_amount: number | null; ad_cost: number | null
  ad_revenue: number | null; gross_profit: number | null; net_profit: number | null
  roi: number | null; refund_rate: number | null; gross_margin: number | null; net_margin: number | null
}
export interface BusinessMetrics {
  group_by: 'platform' | 'shop' | 'category' | 'product' | 'operator'; count: number
  summary: BusinessMetricRow; results: BusinessMetricRow[]
}
export interface StrategyRule {
  id?: number; name: string; metric: string; metric_label?: string; operator: string; operator_label?: string
  threshold: string | number; threshold_max?: string | number | null; weekly_threshold?: string | number | null
  stage?: string; product_grade?: string; conversion_band?: string
  level: string; level_label?: string; message_template: string; suggestion: string; enabled: boolean
}
export interface StrategyRunSummary {
  month?: string; date?: string; scanned_products?: number; rules?: number; alerts?: number
  reporter?: string; strategy_code?: string; evaluated_stage?: string; grade_counts?: Record<string, number>
  skipped?: number; note?: string
  [key: string]: unknown
}
export interface OperationStrategy {
  id?: number; name: string; strategy_type: 'new_product' | 'mature_product' | 'all_product'; strategy_type_label?: string
  strategy_code?: 'standard' | 'new_product_35d' | 'mature_product_30d' | string; strategy_code_label?: string
  description: string; organization: string; platform: string; shop: string; category_path: string
  new_product_days: number; report_mode: 'system' | 'agent'; report_mode_label?: string
  agent_provider: number | null; agent_provider_name?: string; enabled: boolean; schedule_enabled: boolean
  schedule_hour: number; version?: number; last_run_at?: string | null
  last_run_summary?: StrategyRunSummary
  rules: StrategyRule[]
}
export interface StrategyAlert {
  id: number; strategy: number; strategy_name: string; rule: number; rule_name: string; month: string
  organization: string; platform: string; shop: string; product_id: string; product_name: string; product_url: string; product_image_url?: string
  operator_name: string; metric: string; metric_label: string; observed_value: string; threshold_snapshot: Record<string, string | null>
  level: 'info' | 'warning' | 'critical'; level_label: string; title: string; description: string
  suggestion: string; agent_report: string; reporter_name: string
  status: 'open' | 'acknowledged' | 'converted' | 'resolved'; status_label: string; last_triggered_at: string
}
export interface OperationPlan {
  id: number; plan_name: string; strategy: number | null; strategy_name: string; alert: number | null
  organization: string; shop: string; product_id: string; product_name: string; product_url: string; product_image_url?: string
  objective: string; actions: string; owner: number | null; owner_name: string; start_date: string | null; deadline: string | null
  status: 'pending' | 'in_progress' | 'completed' | 'reviewed'; status_label: string
  result: string; review_result: string; created_at: string
}
export interface StrategyOptions {
  dimensions: BusinessDimensions
  agents: Array<{ id: number; name: string; provider: string; model: string }>
  users: Array<{ id: number; username: string; first_name: string }>
}

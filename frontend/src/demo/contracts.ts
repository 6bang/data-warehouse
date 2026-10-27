import type { DemoProduct } from './data'

export interface DemoRequest {
  method: string
  path: string
  params: Record<string, unknown>
  body: Record<string, unknown>
}
export interface DemoContext { products: DemoProduct[]; date: string }

export const DEMO_PAGE_PATHS = [
  '/realtime', '/dashboard', '/business', '/shops', '/products', '/product-catalog',
  '/strategy-alerts', '/strategies', '/operation-plans', '/tasks', '/ai-analysis', '/users', '/configuration',
]
export function isDemoPath(path: string): boolean { return path === '/demo' || path.startsWith('/demo/') }
export const DEMO_PERMISSIONS = [
  'dashboard.view', 'business.view', 'shops.view', 'products.view', 'strategy_alerts.view',
  'strategies.view', 'operation_plans.view', 'tasks.view', 'ai_analysis.view', 'accounts.view',
  'configuration.view', 'data_sync.manage', 'data_import.manage',
]

import { DEMO_PERMISSIONS, type DemoContext, type DemoRequest } from './contracts'
import { DEMO_SHOPS } from './data'

type Row = Record<string, any>
const organization = '示例企业'
let nextId = 100
let tables: Record<string, Row[]> | undefined
const clone = <T>(value: T): T => structuredClone(value)
const paginate = (rows: Row[], params: Record<string, unknown>) => {
  const size = Math.max(1, Math.min(100, Number(params.page_size) || 20))
  const page = Math.max(1, Number(params.page) || 1)
  return { count: rows.length, next: rows.length > page * size ? 'demo-next-page' : null, previous: page > 1 ? 'demo-previous-page' : null, results: clone(rows.slice((page - 1) * size, page * size)) }
}

function init(ctx: DemoContext) {
  if (tables) return tables
  const at = `${ctx.date}T08:00:00+08:00`
  const connection = { enabled: true, connection_status: 'untested', connection_status_label: '演示配置 · 未真实连接', last_tested_at: null, last_error: '' }
  const role = (id: number, name: string, code: string, type: string) => ({ id, name, code, description: '模拟角色，修改不影响真实账户', role_type: type, role_type_label: type === 'system' ? '系统角色' : '自定义角色', data_scope: 'all', data_scope_label: '全部店铺', permissions: [...DEMO_PERMISSIONS], permission_count: DEMO_PERMISSIONS.length, member_count: 1, is_active: true, sort_order: id })
  tables = {
    feishu: [{ id: 1, name: '演示企业应用', app_id: 'cli_demo_not_valid', has_app_secret: false, allowed_tenant_keys: 'demo_tenant', default_base_url: 'https://example.invalid/base/example', ...connection }],
    'ai-providers': [{ id: 1, name: '演示分析模型', provider: 'custom', provider_label: '模拟模型', api_base_url: 'https://example.invalid/v1', model: 'demo-model', has_api_key: false, is_default: true, ...connection }],
    'mcp-servers': [{ id: 1, name: '演示数据服务', endpoint_url: 'https://example.invalid/mcp', auth_type: 'none', has_auth_token: false, agent_query_enabled: false, data_sync_enabled: false, allow_private_network: false, organization_name: organization, last_synced_at: null, schedule_enabled: false, schedule_interval_minutes: 5, next_scheduled_at: null, last_sync_attempted_at: null, consecutive_sync_failures: 0, sync_in_progress: false, sync_started_at: null, allowed_tools: ['query_realtime_metrics'], discovered_tools: [{ name: 'query_realtime_metrics', description: '模拟实时数据查询', inputSchema: { type: 'object', properties: {} } }], protocol_version: '2025-06-18', ...connection }],
    'mcp-tokens': [{ id: 1, name: '演示经营智能体', agent_name: '演示经营智能体', agent_platform: 'demo', agent_id: 'demo-agent', token_prefix: 'DEMO_INVALID', owner_name: '演示管理员', allowed_tools: ['query_realtime_metrics'], permission_codes: ['realtime.view'], allowed_shops: [], enabled: false, approval_status: 'pending', approval_status_label: '待审核', review_note: '', reviewed_by_name: '', reviewed_at: null, expires_at: null, last_used_at: null, created_at: at }],
    events: [{ id: 1, integration_type: 'demo', action: '演示初始化', actor_name: '演示管理员', success: true, duration_ms: 0, detail: { simulated: true }, error: '', created_at: at }],
    roles: [role(1, '所有者', 'owner', 'system'), role(2, '管理员', 'admin', 'system'), role(3, '编辑者', 'operator', 'system'), role(4, '阅读者', 'viewer', 'system'), role(5, '演示运营', 'demo_operator', 'custom')],
    accounts: Array.from({ length: 3 }, (_, i) => ({ id: i + 1, username: `demo_operator_${i + 1}`, first_name: `演示运营 ${String.fromCharCode(65 + i)}`, email: '', role: 'operator', role_name: '编辑者', access_role_id: 3, permission_codes: [...DEMO_PERMISSIONS], data_scope: 'all', allowed_shops: [], department: '演示运营部', registration_reason: '申请体验经营看板（模拟申请）', requested_role_code: 'operator', is_active: i > 0, approval_status: i === 0 ? 'pending' : 'approved', approval_status_label: i === 0 ? '待审批' : '已批准', reviewed_by_name: i ? '演示管理员' : '', reviewed_at: i ? at : null, review_note: '', registered_at: at })),
  }
  return tables
}

// No submitted secrets, uploaded files, or credentials are retained, even in memory.
function safeFields(body: Row) {
  return Object.fromEntries(Object.entries(body).filter(([key]) => !['api_key', 'app_secret', 'password', 'auth_token', 'token', 'file'].includes(key)))
}

export function handleAdminDemo(req: DemoRequest, ctx: DemoContext): unknown | undefined {
  const db = init(ctx)
  const { method, path, params } = req
  const body = safeFields(req.body)
  if (path === '/users/me/' && method === 'GET') return { id: 0, username: '演示管理员', role: 'admin', role_name: '模拟账户', permission_codes: [...DEMO_PERMISSIONS] }
  if (path === '/configuration/summary/' && method === 'GET') return { feishu: db.feishu[0], mcp: { agent_enabled: 0, data_sync_enabled: false } }
  if (path === '/data-sync/mcp/') {
    if (method === 'GET') return { sources: [{ id: 1, name: '演示数据源（不会真实同步）', organization_name: organization, connection_status: 'demo', last_synced_at: null, last_error: '' }] }
    if (method === 'POST' && body.action === 'stores') return { stores: DEMO_SHOPS.map(s => ({ store_id: s.id, store_name: s.name, platform_type: 'demo', platform_name: s.platform })) }
    if (method === 'POST') return { message: '模拟同步完成，未访问数据源', summary: { products: ctx.products.length, shops: 5 } }
  }
  if (path.startsWith('/imports/')) throw new Error('演示模式只展示导入交互，不读取或上传文件，不连接外部数据源')
  if (path === '/access-roles/catalog/' && method === 'GET') return {
    shops: DEMO_SHOPS.map(s => s.name),
    permission_groups: [{ code: 'demo', name: '经营功能权限（模拟）', modules: DEMO_PERMISSIONS.map(permission => ({ code: permission.split('.')[0], name: ({ dashboard: '经营驾驶舱', business: '综合经营 BI', shops: '店铺经营 BI', products: '商品经营 BI', strategy_alerts: '运营策略预警', strategies: '运营策略', operation_plans: '运营计划', tasks: '运营任务', ai_analysis: 'AI 分析', accounts: '用户与权限', configuration: '配置中心', data_sync: '数据同步', data_import: '数据导入' } as Row)[permission.split('.')[0]], actions: [{ code: permission.split('.')[1], name: '查看 / 使用', permission }] })) }],
  }
  const match = path.match(/^\/(?:configuration\/(feishu|ai-providers|mcp-servers|mcp-tokens|events)|(access-roles|accounts))\/(?:(\d+)\/)?(?:(test|discover|set_default|review|approve|reject|update_access)\/)?$/)
  if (!match) return undefined
  const key = match[1] || (match[2] === 'access-roles' ? 'roles' : 'accounts')
  const rows = db[key]
  const id = Number(match[3])
  const action = match[4]
  const row = rows.find(item => item.id === id)
  if (id && !row) throw new Error('演示记录不存在')
  if (action && method === 'POST' && row) {
    if (['test', 'discover'].includes(action)) return { message: '演示连接流程完成；未连接任何外部服务', tools: row.discovered_tools || [] }
    if (action === 'set_default') rows.forEach(item => { item.is_default = item.id === id })
    if (['review', 'approve', 'reject'].includes(action)) {
      row.approval_status = action === 'review' ? body.approval_status : action === 'approve' ? 'approved' : 'rejected'
      row.approval_status_label = ({ approved: '已批准', rejected: '已拒绝', pending: '待审核' } as Row)[row.approval_status]
      row.enabled = row.approval_status === 'approved'
      row.is_active = row.enabled
      row.reviewed_by_name = '演示管理员'
      row.reviewed_at = `${ctx.date}T12:00:00+08:00`
    }
    if (['approve', 'update_access'].includes(action)) {
      row.access_role_id = body.access_role
      row.allowed_shops = body.allowed_shops || []
      row.role_name = db.roles.find(role => role.id === body.access_role)?.name || '演示角色'
    }
    return clone(row)
  }
  if (method === 'GET') {
    if (id) return clone(row)
    let result = rows
    if (params.approval_status) result = result.filter(item => item.approval_status === params.approval_status)
    if (params.search) result = result.filter(item => `${item.name || ''} ${item.username || ''} ${item.first_name || ''}`.toLowerCase().includes(String(params.search).toLowerCase()))
    return paginate(result, params)
  }
  if (method === 'DELETE' && row) { db[key] = rows.filter(item => item.id !== id); return {} }
  if (['PATCH', 'PUT'].includes(method) && row) {
    Object.assign(row, body, { id })
    if (key === 'roles') row.permission_count = row.permissions.length
    return clone(row)
  }
  if (method === 'POST' && !id) {
    const template = rows[0] || {}
    const created: Row = { ...clone(template), ...body, id: nextId++, created_at: `${ctx.date}T12:00:00+08:00` }
    if (key === 'roles') Object.assign(created, { role_type: 'custom', role_type_label: '自定义角色', permission_count: (body.permissions || []).length, member_count: 0 })
    if (key === 'mcp-tokens') Object.assign(created, { token_prefix: 'DEMO_INVALID', enabled: false, approval_status: 'pending', approval_status_label: '待审核' })
    rows.push(created)
    return key === 'mcp-tokens' ? { ...clone(created), token: `DEMO_ONLY_NOT_A_VALID_KEY_${created.id}` } : clone(created)
  }
  throw new Error('此管理操作不支持演示')
}

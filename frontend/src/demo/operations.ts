import type { OperationPlan, OperationStrategy, StrategyAlert, StrategyOptions, StrategyRule, Task } from '../api/types'
import type { DemoRequest, DemoContext } from './contracts'
import { buildDemoSnapshot, DEMO_SHOPS } from './data'

// Deliberately process-local: navigation retains edits; a reload resets everything.
// This module has no network, browser-storage, scheduler, or real AI integration.
const NOTICE = '模拟演示：仅使用示例数据和当前页面内存，未调用真实模型、采集数据或执行运营动作；刷新后重置。'
const ORGANIZATION = '示例企业'
const USERS = ['A', 'B', 'C'].map((letter, index) => ({ id: index + 1, username: `demo-operator-${letter.toLowerCase()}`, first_name: `演示运营 ${letter}` }))
const PLAN_STATUS = { pending: '待执行', in_progress: '执行中', completed: '已完成', reviewed: '已复盘' }
const ALERT_STATUS = { open: '待处理', acknowledged: '已确认', converted: '已转计划', resolved: '已解除' }
const LEVELS = { info: '提示', warning: '警告', critical: '严重' }
const METRICS: Record<string, string> = { sales: '成交金额', orders: '订单数', refund_amount: '退款金额', refund_rate: '退款率', ad_cost: '广告花费', roi: '广告 ROI', gross_profit: '毛利润', gross_margin: '毛利率', net_profit: '净利润', net_margin: '净利率', product_age_days: '商品上架天数', conversion_rate: '转化率', cumulative_35d_sales: '新品35天累计销量', daily_sales_volume: '日销量', weekly_sales_volume: '周销量', recent_30d_sales: '近30天销量' }
const OPERATORS: Record<string, string> = { lt: '小于', lte: '小于等于', gt: '大于', gte: '大于等于', eq: '等于', between: '介于' }
type DemoTask = Task & { created_at: string; month: string }
interface Memory { strategies: OperationStrategy[]; alerts: StrategyAlert[]; plans: OperationPlan[]; tasks: DemoTask[]; sequence: number }
let memory: Memory | undefined

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const string = (value: unknown, fallback = '') => typeof value === 'string' ? value : fallback
const nullableString = (value: unknown) => string(value) || null
const timestamp = (context: DemoContext) => `${context.date}T09:00:00+08:00`
function month(value: unknown, context: DemoContext): string {
  const result = string(value) || context.date.slice(0, 7)
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(result)) throw new Error('请选择有效的演示月份。')
  return result
}
function required(value: unknown, label: string): string {
  const result = string(value).trim()
  if (!result) throw new Error(`请填写${label}。`)
  return result
}
function owner(value: unknown): number | null {
  if (value === undefined || value === null || value === '') return null
  const id = Number(value)
  if (!USERS.some(user => user.id === id)) throw new Error('请选择演示负责人。')
  return id
}
const ownerName = (id: number | null) => USERS.find(user => user.id === id)?.first_name || ''
function record<T extends { id?: number }>(rows: T[], id: string): T {
  const found = rows.find(row => row.id === Number(id))
  if (!found) throw new Error('该演示记录不存在，刷新页面后演示数据会重置。')
  return found
}
function options(context: DemoContext): StrategyOptions {
  const [year, current] = context.date.split('-').map(Number)
  const months = Array.from({ length: 6 }, (_, index) => new Date(Date.UTC(year!, current! - 1 - index, 1)).toISOString().slice(0, 7))
  return {
    dimensions: {
      organizations: [ORGANIZATION], months, platforms: [...new Set(DEMO_SHOPS.map(shop => shop.platform))], shops: DEMO_SHOPS.map(shop => shop.name),
      categories: ['演示分类->家居生活', '演示分类->品质日用', '演示分类->精选好物'], operators: USERS.map(user => user.first_name),
      selected: { organization: ORGANIZATION, month: months[0]! },
      coverage: { available: ['示例经营指标'], unavailable: ['真实采集', '真实模型', '真实运营执行'], source: NOTICE }, latest_sync: null,
    },
    agents: [{ id: 1, name: '演示分析助手（模拟）', provider: 'simulation', model: 'local-demo-template' }], users: copy(USERS),
  }
}
function page<T extends object>(rows: T[], request: DemoRequest) {
  const aliases: Record<string, string> = { strategy_id: 'strategy', owner_id: 'owner' }
  let result = rows.filter(row => Object.entries(request.params).every(([key, value]) => {
    if (value === '' || value == null || ['page', 'page_size', 'ordering'].includes(key)) return true
    const fields = row as Record<string, unknown>
    if (key === 'search') return Object.values(fields).some(field => typeof field === 'string' && field.toLowerCase().includes(String(value).toLowerCase()))
    if (key === 'month') return String(fields.month || fields.created_at || '').startsWith(String(value))
    const field = aliases[key] || key
    return !(field in fields) || String(fields[field]) === String(value)
  }))
  const ordering = string(request.params.ordering)
  if (ordering) {
    const descending = ordering.startsWith('-'); const key = descending ? ordering.slice(1) : ordering
    result = [...result].sort((a, b) => String((a as Record<string, unknown>)[key] ?? '').localeCompare(String((b as Record<string, unknown>)[key] ?? ''), 'zh-CN', { numeric: true }) * (descending ? -1 : 1))
  }
  const number = (value: unknown, fallback: number) => Number.isFinite(Number(value)) && Number(value) > 0 ? Math.floor(Number(value)) : fallback
  const size = Math.min(100, number(request.params.page_size, 10)); const index = number(request.params.page, 1)
  const link = (target: number) => `${request.path}?page=${target}&page_size=${size}`
  return { count: result.length, next: index * size < result.length ? link(index + 1) : null, previous: index > 1 ? link(index - 1) : null, results: result.slice((index - 1) * size, index * size) }
}
function makeStrategy(body: Record<string, unknown>, state: Memory, previous?: OperationStrategy): OperationStrategy {
  const merged = { ...previous, ...body }
  const strategyType = string(merged.strategy_type, 'all_product') as OperationStrategy['strategy_type']
  if (!['new_product', 'mature_product', 'all_product'].includes(strategyType)) throw new Error('不支持的商品阶段。')
  const rulesInput = merged.rules
  if (!Array.isArray(rulesInput) || !rulesInput.length) throw new Error('请至少添加一条演示规则。')
  const rules = rulesInput.map((input: unknown): StrategyRule => {
    if (!input || typeof input !== 'object') throw new Error('演示规则格式不正确。')
    const rule = input as Record<string, unknown>; const metric = string(rule.metric, 'sales'); const operator = string(rule.operator, 'lt')
    const level = string(rule.level, 'warning') as keyof typeof LEVELS
    if (!OPERATORS[operator] || !METRICS[metric] || !LEVELS[level] || !Number.isFinite(Number(rule.threshold))) throw new Error('请检查规则指标、比较方式和阈值。')
    return { id: ++state.sequence, name: required(rule.name, '规则名称'), metric, metric_label: METRICS[metric], operator, operator_label: OPERATORS[operator], threshold: Number(rule.threshold), threshold_max: rule.threshold_max == null ? null : Number(rule.threshold_max), weekly_threshold: rule.weekly_threshold == null ? null : Number(rule.weekly_threshold), stage: string(rule.stage), product_grade: string(rule.product_grade), conversion_band: string(rule.conversion_band), level, level_label: LEVELS[level], message_template: string(rule.message_template), suggestion: string(rule.suggestion), enabled: rule.enabled !== false }
  })
  const reportMode = merged.report_mode === 'agent' ? 'agent' : 'system'
  return {
    id: previous?.id ?? ++state.sequence, name: required(merged.name, '策略名称'), strategy_type: strategyType,
    strategy_type_label: { new_product: '新品策略', mature_product: '老品策略', all_product: '全量商品策略' }[strategyType], strategy_code: string(merged.strategy_code, 'standard'),
    description: string(merged.description), organization: string(merged.organization), platform: string(merged.platform), shop: string(merged.shop), category_path: string(merged.category_path),
    new_product_days: Number(merged.new_product_days) || 35, report_mode: reportMode, report_mode_label: reportMode === 'agent' ? '演示助手（模拟）' : '规则演示（模拟）',
    agent_provider: reportMode === 'agent' ? 1 : null, agent_provider_name: reportMode === 'agent' ? '演示分析助手（模拟）' : '', enabled: merged.enabled !== false,
    schedule_enabled: merged.schedule_enabled !== false, schedule_hour: Number(merged.schedule_hour) || 7, version: (previous?.version || 0) + 1,
    last_run_at: previous?.last_run_at || null, last_run_summary: previous?.last_run_summary, rules,
  }
}
function makePlan(body: Record<string, unknown>, state: Memory, context: DemoContext, previous?: OperationPlan): OperationPlan {
  const merged = { ...previous, ...body }; const productId = string(merged.product_id)
  const product = context.products.find(item => item.id === productId); const ownerId = owner(merged.owner)
  const strategyId = merged.strategy == null || String(merged.strategy) === '' ? null : Number(merged.strategy)
  const strategy = strategyId === null ? undefined : record(state.strategies, String(strategyId))
  return {
    id: previous?.id ?? ++state.sequence, plan_name: required(merged.plan_name, '计划名称'), strategy: strategyId, strategy_name: strategy?.name || '',
    alert: previous?.alert ?? null, organization: string(merged.organization, ORGANIZATION), shop: string(merged.shop), product_id: productId, product_name: string(merged.product_name) || product?.name || '',
    product_url: '', product_image_url: product?.imageUrl || '', objective: string(merged.objective), actions: string(merged.actions), owner: ownerId, owner_name: ownerName(ownerId),
    start_date: nullableString(merged.start_date), deadline: nullableString(merged.deadline), status: previous?.status || 'pending', status_label: previous?.status_label || PLAN_STATUS.pending,
    result: previous?.result || '', review_result: previous?.review_result || '', created_at: previous?.created_at || timestamp(context),
  }
}
function makeTask(body: Record<string, unknown>, state: Memory, context: DemoContext, previous?: DemoTask): DemoTask {
  const merged = { ...previous, ...body }; const ownerId = owner(merged.owner); const productId = string(merged.product_id)
  return {
    id: previous?.id ?? ++state.sequence, task_name: required(merged.task_name, '任务名称'), product_id: productId,
    product_image_url: context.products.find(item => item.id === productId)?.imageUrl || '', problem: string(merged.problem), ai_suggestion: string(merged.ai_suggestion),
    source: ['manual', 'ai', 'abnormal'].includes(string(merged.source)) ? string(merged.source) : 'manual', owner: ownerId, owner_name: ownerName(ownerId),
    deadline: nullableString(merged.deadline), status: previous?.status || 'pending', status_label: previous?.status_label || '待处理', result: previous?.result || '', review_result: previous?.review_result || '',
    created_at: previous?.created_at || timestamp(context), month: previous?.month || context.date.slice(0, 7),
  }
}
function transition(row: OperationPlan | DemoTask, body: Record<string, unknown>) {
  const next: Record<string, string> = { pending: 'in_progress', in_progress: 'completed', completed: 'reviewed' }
  const status = string(body.status) as OperationPlan['status']
  if (next[row.status] !== status) throw new Error('请按待处理、执行中、已完成、已复盘的顺序进行模拟流转。')
  row.status = status; row.status_label = PLAN_STATUS[status]
  if (body.result !== undefined) row.result = string(body.result)
  if (body.review_result !== undefined) row.review_result = string(body.review_result)
  return row
}
function makeAlert(strategy: OperationStrategy, context: DemoContext, state: Memory, index: number, selectedMonth: string): StrategyAlert | undefined {
  const product = context.products[index % context.products.length]; const rule = strategy.rules.find(item => item.enabled)
  if (!product || !rule) return undefined
  const shop = DEMO_SHOPS.find(item => item.name === strategy.shop) || DEMO_SHOPS[index % DEMO_SHOPS.length]!
  const level = (rule.level in LEVELS ? rule.level : 'warning') as StrategyAlert['level']
  return {
    id: ++state.sequence, strategy: strategy.id!, strategy_name: strategy.name, rule: rule.id!, rule_name: rule.name, month: selectedMonth,
    organization: ORGANIZATION, platform: shop.platform, shop: shop.name, product_id: product.id, product_name: product.name, product_url: '', product_image_url: product.imageUrl,
    operator_name: USERS[index % USERS.length]!.first_name, metric: rule.metric, metric_label: rule.metric_label || rule.metric,
    observed_value: String(Math.max(0, Number(rule.threshold) * 0.8)), threshold_snapshot: { operator: rule.operator, operator_label: rule.operator_label || rule.operator, threshold: String(rule.threshold), threshold_max: rule.threshold_max == null ? null : String(rule.threshold_max) },
    level, level_label: LEVELS[level], title: `模拟预警：${rule.name}`, description: `示例商品「${product.name}」的预警处理流程演示；此记录不代表真实规则计算结果。`,
    suggestion: rule.suggestion || '演示动作：核对主图与详情页，拟定调整清单并进行人工复核。', agent_report: NOTICE,
    reporter_name: '演示分析助手（模拟）', status: 'open', status_label: ALERT_STATUS.open, last_triggered_at: timestamp(context),
  }
}
function initialState(context: DemoContext): Memory {
  const state: Memory = { strategies: [], alerts: [], plans: [], tasks: [], sequence: 100 }
  ;[
    { name: '新品成长巡检（演示）', strategy_type: 'new_product', metric: 'daily_sales_volume', rule: '新品日销量观察', threshold: 10, level: 'warning' },
    { name: '成熟商品投放观察（演示）', strategy_type: 'mature_product', metric: 'roi', rule: '投放效率观察', threshold: 3, level: 'critical' },
  ].forEach((seed, index) => {
    const strategy = makeStrategy({ name: seed.name, strategy_type: seed.strategy_type, strategy_code: 'standard', organization: ORGANIZATION, description: NOTICE, schedule_enabled: false, rules: [{ name: seed.rule, metric: seed.metric, operator: 'lt', threshold: seed.threshold, level: seed.level, enabled: true, suggestion: '模拟建议：先核对经营指标，再制定主图、详情和投放优化计划。' }] }, state)
    state.strategies.push(strategy)
    const alert = makeAlert(strategy, context, state, index, context.date.slice(0, 7))
    if (alert) state.alerts.push(alert)
  })
  ;(['pending', 'in_progress', 'completed', 'reviewed'] as const).forEach((status, index) => {
    const product = context.products[index % context.products.length]
    const plan = makePlan({ plan_name: `${['商品优化', '投放复核', '内容更新', '周度复盘'][index]}计划（演示）`, product_id: product?.id || '', organization: ORGANIZATION, shop: DEMO_SHOPS[index % DEMO_SHOPS.length]!.name, objective: '演示目标：验证运营闭环流程，不代表真实经营承诺。', actions: '模拟操作：整理问题、明确责任、记录执行结果和复盘结论。', owner: index % USERS.length + 1, start_date: context.date, deadline: context.date }, state, context)
    plan.status = status; plan.status_label = PLAN_STATUS[status]; state.plans.push(plan)
    const task = makeTask({ task_name: `${['检查主图点击表现', '复核广告预算', '更新详情页内容', '完成运营周复盘'][index]}（演示）`, product_id: product?.id || '', problem: '示例经营问题，仅用于体验任务流转。', ai_suggestion: NOTICE, owner: index % USERS.length + 1, deadline: `${context.date}T18:00:00+08:00`, source: index === 0 ? 'ai' : 'manual' }, state, context)
    task.status = status; task.status_label = status === 'pending' ? '待处理' : PLAN_STATUS[status]; state.tasks.push(task)
  })
  return state
}
function simulateRun(strategy: OperationStrategy, state: Memory, context: DemoContext, selectedMonth: string) {
  const index = Math.max(0, state.strategies.indexOf(strategy)); const example = makeAlert(strategy, context, state, index, selectedMonth)
  if (example) {
    const existing = state.alerts.find(alert => alert.strategy === strategy.id && alert.month === selectedMonth && alert.product_id === example.product_id)
    if (existing) Object.assign(existing, example, { id: existing.id, status: existing.status, status_label: existing.status_label })
    else state.alerts.unshift(example)
  }
  const summary = { month: selectedMonth, date: context.date, scanned_products: context.products.length, rules: strategy.rules.filter(rule => rule.enabled).length, alerts: example ? 1 : 0, reporter: '模拟演示', simulation: true, note: `${NOTICE} 此按钮仅生成/刷新一条流程示例，不实际评估策略规则。` }
  strategy.last_run_at = timestamp(context); strategy.last_run_summary = summary
  return summary
}
function analyze(body: Record<string, unknown>, state: Memory, context: DemoContext) {
  const selectedMonth = month(body.month, context)
  const date = selectedMonth === context.date.slice(0, 7) ? context.date : `${selectedMonth}-${new Date(Number(selectedMonth.slice(0, 4)), Number(selectedMonth.slice(5)), 0).getDate()}`
  const shop = string(body.shop); const shopId = !shop ? '' : DEMO_SHOPS.find(item => item.name === shop || item.id === shop)?.id || 'no-matching-demo-shop'
  const products = context.products.filter(item => !body.product_id || item.id === body.product_id)
  const snapshot = buildDemoSnapshot(products, { date, shopId, period: 'month', scenario: 'steady' })
  const keys = { sales: 'sales', sales_volume: 'units', orders: 'orders', visitors: 'visitors', ad_cost: 'adCost', roi: 'roi', profit: 'profit', conversion_rate: 'conversionRate' } as const
  const metrics = Object.fromEntries(Object.entries(keys).map(([key, field]) => {
    const current = snapshot.totals[field]; const previous = snapshot.previous[field]
    return [key, { value: field === 'conversionRate' ? current / 100 : current, change_rate: previous ? (current - previous) / previous : null }]
  }))
  const product = products[0]; const available = !!product && snapshot.totals.orders > 0
  return {
    id: ++state.sequence, provider: 'simulation', model: 'local-demo-template', month: selectedMonth, date: context.date, simulation: true,
    input_context: { dashboard: { metrics }, question: string(body.question), shop, product_id: string(body.product_id) },
    output: {
      provider_notice: `${NOTICE} 以下为固定示例分析，不是对补充问题的真实模型回答。`,
      problems: available ? [`${selectedMonth} 示例经营盘面可用于演示从指标到任务的处理流程。`, '示例关注项：商品内容完善与投放节奏复核。'] : ['当前筛选范围没有匹配的演示商品或店铺。'],
      reasons: available ? ['这是预设分析模板，不对真实经营因果作判断。', '示例数据按商品、店铺和日期生成，不能替代真实经营记录。'] : ['请使用演示店铺名称与商品目录中的商品 ID。'],
      suggestions: available ? ['先核对指标口径，再由人工确认是否创建行动任务。', '在任务中心体验待处理、执行中、完成和复盘的完整流程。'] : ['调整筛选后重新体验示例分析。'],
      actions: available ? [{ task_name: `内容与投放复核（演示）：${product.name}`, product_id: product.id, product_image_url: product.imageUrl, problem: '固定示例问题：需要核对商品内容与投放表现。', suggestion: '模拟建议：整理主图、详情页与预算核对清单；实际执行需人工确认。' }] : [],
    },
  }
}

/** Only the owned operations API surface is handled; callers fail closed otherwise. */
export function handleOperationsDemo(request: DemoRequest, context: DemoContext): unknown | undefined {
  if (!/^\/(strategy-options|operation-strategies|strategy-alerts|operation-plans|tasks|ai-analysis)\//.test(request.path)) return undefined
  const state = memory ||= initialState(context)
  const { method, path, body } = request
  if (path === '/strategy-options/' && method === 'GET') return copy(options(context))
  if (path === '/ai-analysis/' && method === 'POST') return copy(analyze(body, state, context))
  if (path === '/operation-strategies/run_all/' && method === 'POST') {
    const selectedMonth = month(body.month, context); const results = state.strategies.filter(strategy => strategy.enabled).map(strategy => simulateRun(strategy, state, context, selectedMonth))
    return copy({ month: selectedMonth, strategies: results.length, results, simulation: true, note: NOTICE })
  }
  if (path === '/tasks/from_abnormal/' && method === 'POST') {
    const products = [...new Map(context.products.map(product => [product.id, product])).values()]
    const index = Number(body.abnormal_record_id) - 1; const product = Number.isInteger(index) && index >= 0 ? products[index] : undefined
    if (!product) throw new Error('未找到对应的演示异常商品。')
    const task = makeTask({ ...body, task_name: string(body.task_name) || `处理示例异常：${product.name}`, product_id: product.id, owner: body.owner_id ?? null, problem: `模拟复盘提示：${product.name}可进行转化与投放复盘`, ai_suggestion: '仅演示异常转任务流程，请检查主图和投放计划；不是对真实商品的风险判断。', source: 'abnormal' }, state, context)
    state.tasks.unshift(task); return copy(task)
  }
  const match = path.match(/^\/(operation-strategies|strategy-alerts|operation-plans|tasks)\/(?:(\d+)\/(?:(run|set_status|convert_plan|transition)\/)?)?$/)
  if (!match) return undefined
  const [, resource, id, action] = match
  if (resource === 'operation-strategies') {
    if (!id && method === 'GET') return copy(page(state.strategies, request))
    if (!id && method === 'POST') { const strategy = makeStrategy(body, state); state.strategies.unshift(strategy); return copy(strategy) }
    if (id) {
      const strategy = record(state.strategies, id)
      if (action === 'run' && method === 'POST') return copy(simulateRun(strategy, state, context, month(body.month, context)))
      if (!action && method === 'GET') return copy(strategy)
      if (!action && ['PUT', 'PATCH'].includes(method)) { const updated = makeStrategy(body, state, strategy); Object.assign(strategy, updated); return copy(strategy) }
      if (!action && method === 'DELETE') {
        state.strategies = state.strategies.filter(item => item !== strategy); state.alerts = state.alerts.filter(alert => alert.strategy !== strategy.id)
        state.plans.forEach(plan => { if (plan.strategy === strategy.id) { plan.strategy = null; plan.strategy_name = ''; plan.alert = null } })
        return { simulation: true, detail: '演示策略已从当前内存删除。' }
      }
    }
  }
  if (resource === 'strategy-alerts') {
    if (!id && method === 'GET') return copy(page(state.alerts, request))
    if (id) {
      const alert = record(state.alerts, id)
      if (!action && method === 'GET') return copy(alert)
      if (action === 'set_status' && method === 'POST') {
        const status = string(body.status)
        if (!['open', 'acknowledged', 'resolved'].includes(status)) throw new Error('请选择有效的演示预警状态。')
        alert.status = status as StrategyAlert['status']; alert.status_label = ALERT_STATUS[alert.status]; return copy(alert)
      }
      if (action === 'convert_plan' && method === 'POST') {
        const existing = state.plans.find(plan => plan.alert === alert.id)
        if (existing) return copy(existing)
        const plan = makePlan({ ...body, plan_name: string(body.plan_name) || `处理：${alert.title}`, strategy: alert.strategy, organization: alert.organization, shop: alert.shop, product_id: alert.product_id, product_name: alert.product_name, objective: string(body.objective) || alert.description, actions: string(body.actions) || alert.suggestion, owner: body.owner_id ?? null, start_date: string(body.start_date) || context.date }, state, context)
        plan.alert = alert.id; state.plans.unshift(plan); alert.status = 'converted'; alert.status_label = ALERT_STATUS.converted; return copy(plan)
      }
    }
  }
  if (resource === 'operation-plans') {
    if (!id && method === 'GET') return copy(page(state.plans, request))
    if (!id && method === 'POST') { const plan = makePlan(body, state, context); state.plans.unshift(plan); return copy(plan) }
    if (id) {
      const plan = record(state.plans, id)
      if (!action && method === 'GET') return copy(plan)
      if (action === 'transition' && method === 'POST') return copy(transition(plan, body))
      if (!action && ['PUT', 'PATCH'].includes(method)) { Object.assign(plan, makePlan(body, state, context, plan)); return copy(plan) }
      if (!action && method === 'DELETE') { state.plans = state.plans.filter(item => item !== plan); return { simulation: true, detail: '演示计划已从当前内存删除。' } }
    }
  }
  if (resource === 'tasks') {
    if (!id && method === 'GET') return copy(page(state.tasks, request))
    if (!id && method === 'POST') { const task = makeTask(body, state, context); state.tasks.unshift(task); return copy(task) }
    if (id) {
      const task = record(state.tasks, id)
      if (!action && method === 'GET') return copy(task)
      if (action === 'transition' && method === 'POST') return copy(transition(task, body))
      if (!action && ['PUT', 'PATCH'].includes(method)) { Object.assign(task, makeTask(body, state, context, task)); return copy(task) }
      if (!action && method === 'DELETE') { state.tasks = state.tasks.filter(item => item !== task); return { simulation: true, detail: '演示任务已从当前内存删除。' } }
    }
  }
  return undefined
}

import type { BusinessDimensions, BusinessMetricRow, BusinessMetrics, DashboardData, ProductCatalog, ProductData, RealtimeDashboardData, RealtimeMetric, ShopData } from '../api/types'
import type { DemoRequest, DemoContext } from './contracts'
import { buildDemoSnapshot, DEMO_SHOPS, type DemoMetrics, type DemoProduct, type DemoShop, type DemoSnapshot } from './data'

// Display metadata comes exclusively from the public catalog. All other fields
// below (including product ages, categories and responsibility) are fictional.
const ORGANIZATION = '示例企业'
const CATEGORIES = ['演示分类->家居生活', '演示分类->品质日用', '演示分类->精选好物']
const OPERATORS = ['演示运营 A', '演示运营 B', '演示运营 C']
const DAY = 86_400_000
type Params = Record<string, unknown>
type CatalogItem = { product: DemoProduct; index: number; category: string; operator: string; age: number | null; created: string | null; lifecycle: 'new' | 'mature' | 'unknown' }
type Cell = { item: CatalogItem; shop: DemoShop; metrics: DemoMetrics }
type Bundle = { shop: DemoShop; items: CatalogItem[]; snapshot: DemoSnapshot }
const round = (value: number) => Math.round((value + Number.EPSILON) * 100) / 100
const ratio = (value: number, base: number) => base ? value / base : 0
const change = (value: number, previous: number) => previous ? (value - previous) / Math.abs(previous) : null
const str = (params: Params, name: string) => String(params[name] ?? '').trim()
const dateString = (value: Date) => value.toISOString().slice(0, 10)
const shiftDay = (date: string, days: number) => dateString(new Date(new Date(`${date}T00:00:00Z`).getTime() + days * DAY))
function validDate(date: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(`${date}T00:00:00Z`)) && dateString(new Date(`${date}T00:00:00Z`)) === date
}
function monthOffset(date: string, offset: number): string {
  const value = new Date(`${date.slice(0, 7)}-01T00:00:00Z`)
  value.setUTCMonth(value.getUTCMonth() + offset)
  return value.toISOString().slice(0, 7)
}
function months(context: DemoContext): string[] { return Array.from({ length: 6 }, (_, index) => monthOffset(context.date, -index)) }
function selectedDate(params: Params, context: DemoContext, daily = false): string | null {
  const requestedDate = str(params, 'date')
  if (requestedDate) return validDate(requestedDate) && (!str(params, 'month') || requestedDate.startsWith(str(params, 'month') + '-')) ? requestedDate : null
  if (daily) return context.date
  const month = str(params, 'month') || context.date.slice(0, 7)
  if (!months(context).includes(month)) return null
  return month === context.date.slice(0, 7) ? context.date : shiftDay(`${monthOffset(`${month}-01`, 1)}-01`, -1)
}
function catalog(context: DemoContext): CatalogItem[] {
  const unique = [...new Map(context.products.map(product => [product.id, product])).values()]
  return unique.map((product, index) => {
    const age = index % 7 === 6 ? null : index % 3 === 0 ? 5 + index % 26 : 60 + index * 7
    return { product, index, category: CATEGORIES[index % CATEGORIES.length]!, operator: OPERATORS[index % OPERATORS.length]!, age,
      created: age === null ? null : `${shiftDay(context.date, 1 - age)}T00:00:00+08:00`,
      lifecycle: age === null ? 'unknown' : age <= 35 ? 'new' : 'mature' }
  })
}
function contains(value: string, query: string): boolean { return value.toLocaleLowerCase().includes(query.toLocaleLowerCase()) }
function matches(item: CatalogItem, shop: DemoShop, params: Params, searchMode = 'all'): boolean {
  const exact: Array<[string, string[]]> = [
    ['organization', [ORGANIZATION]], ['platform', [shop.platform]], ['platform_type', [shop.platform]],
    ['shop', [shop.id, shop.name]], ['shop_id', [shop.id]], ['store_id', [shop.id]],
    ['category_path', [item.category]], ['category', [item.category]], ['operator_name', [item.operator]],
    ['operator', [item.operator]], ['op_manager', [item.operator]], ['product_id', [item.product.id]], ['lifecycle', [item.lifecycle]],
  ]
  if (exact.some(([key, values]) => str(params, key) && !values.includes(str(params, key)))) return false
  const query = str(params, 'search')
  const text = searchMode === 'shop' ? `${shop.name} ${shop.platform}` : `${item.product.id} ${item.product.name} ${item.product.code} ${shop.name} ${shop.platform} ${item.category} ${item.operator}`
  return !query || contains(text, query)
}
function bundles(context: DemoContext, params: Params, date: string | null, period: 'today' | 'month', searchMode = 'all'): Bundle[] {
  if (!date) return []
  const items = catalog(context)
  return DEMO_SHOPS.flatMap(shop => {
    const selected = items.filter(item => matches(item, shop, params, searchMode))
    return selected.length ? [{ shop, items: selected, snapshot: buildDemoSnapshot(selected.map(item => item.product), { date, shopId: shop.id, period, scenario: 'steady' }) }] : []
  })
}
function cells(values: Bundle[]): Cell[] {
  return values.flatMap(bundle => bundle.snapshot.products.map((metrics, index) => ({ item: bundle.items[index]!, shop: bundle.shop, metrics })))
}
function sum(values: DemoMetrics[]): DemoMetrics {
  const result = { sales: 0, units: 0, orders: 0, visitors: 0, adCost: 0, profit: 0, conversionRate: 0, roi: 0 }
  for (const value of values) {
    result.sales += Math.round(value.sales * 100); result.adCost += Math.round(value.adCost * 100); result.profit += Math.round(value.profit * 100)
    result.units += value.units; result.orders += value.orders; result.visitors += value.visitors
  }
  result.sales /= 100; result.adCost /= 100; result.profit /= 100
  result.conversionRate = ratio(result.orders, result.visitors) * 100; result.roi = ratio(result.sales, result.adCost)
  return result
}
function order<T extends object>(rows: T[], params: Params, defaultKey = '-sales'): T[] {
  const keys = (str(params, 'ordering') || defaultKey).split(',')
  return [...rows].sort((a, b) => {
    for (const entry of keys) {
      const descending = entry.startsWith('-'); const key = (descending ? entry.slice(1) : entry) as keyof T
      const left = a[key]; const right = b[key]
      if (left == null || right == null) { if (left !== right) return left == null ? 1 : -1; continue }
      const numeric = typeof left === 'number' || typeof right === 'number' || (/^-?\d+(\.\d+)?$/.test(String(left)) && /^-?\d+(\.\d+)?$/.test(String(right)))
      const compared = numeric ? Number(left) - Number(right) : String(left).localeCompare(String(right), 'zh-CN')
      if (compared) return descending ? -compared : compared
    }
    return 0
  })
}
function positiveInt(value: unknown, fallback: number, max = 1000): number {
  const parsed = Number(value); return Number.isFinite(parsed) && parsed > 0 ? Math.min(max, Math.floor(parsed)) : fallback
}
function paginate<T>(rows: T[], request: DemoRequest) {
  const page = positiveInt(request.params.page, 1, Number.MAX_SAFE_INTEGER); const size = positiveInt(request.params.page_size, 20)
  const link = (target: number) => {
    const query = new URLSearchParams(Object.entries(request.params).map(([key, value]) => [key, String(value)]))
    query.set('page', String(target)); query.set('page_size', String(size)); return `${request.path}?${query}`
  }
  return { count: rows.length, next: page * size < rows.length ? link(page + 1) : null, previous: page > 1 ? link(page - 1) : null, results: rows.slice((page - 1) * size, page * size) }
}
function financial(metrics: DemoMetrics) {
  const refund = round(metrics.sales * 0.03); const custom = round(metrics.sales * 0.02)
  const net = round(metrics.sales - refund); const grossProfit = metrics.profit
  const netProfit = round(metrics.profit - metrics.adCost - custom)
  return { refund, custom, net, grossProfit, netProfit }
}
function businessRow(rows: Cell[]): BusinessMetricRow {
  const total = sum(rows.map(row => row.metrics)); const finance = rows.map(row => financial(row.metrics))
  const refund = round(finance.reduce((value, row) => value + row.refund, 0))
  const gross = round(finance.reduce((value, row) => value + row.grossProfit, 0)); const net = round(total.sales - refund)
  const netProfit = round(finance.reduce((value, row) => value + row.netProfit, 0))
  return { products: new Set(rows.map(row => `${row.shop.id}:${row.item.product.id}`)).size, sales: total.sales, gross_sales: total.sales, net_sales: net,
    sales_volume: total.units, orders: total.orders, visitors: total.visitors, stock: rows.reduce((value, row) => value + stock(row), 0),
    refund_amount: refund, ad_cost: total.adCost, ad_revenue: total.sales, gross_profit: gross, net_profit: netProfit,
    // All pages use transaction sales as the margin denominator.
    roi: total.roi, refund_rate: ratio(refund, total.sales), gross_margin: ratio(gross, total.sales), net_margin: ratio(netProfit, total.sales) }
}
function stock(row: Cell) { return 80 + row.item.index * 17 + DEMO_SHOPS.findIndex(shop => shop.id === row.shop.id) * 23 }
function grouped(rows: Cell[], key: (row: Cell) => string): Cell[][] {
  const groups = new Map<string, Cell[]>()
  for (const row of rows) { const name = key(row); const group = groups.get(name) || []; group.push(row); groups.set(name, group) }
  return [...groups.values()]
}
function dimensions(params: Params, context: DemoContext): BusinessDimensions {
  const date = selectedDate(params, context); const all = date ? catalog(context) : []
  const scoped = DEMO_SHOPS.flatMap(shop => all.filter(item => matches(item, shop, params)).map(item => ({ shop, item })))
  return { organizations: [ORGANIZATION], months: months(context), platforms: [...new Set(scoped.map(row => row.shop.platform))], shops: [...new Set(scoped.map(row => row.shop.name))],
    categories: [...new Set(scoped.map(row => row.item.category))], operators: [...new Set(scoped.map(row => row.item.operator))],
    selected: { organization: str(params, 'organization') || ORGANIZATION, month: str(params, 'month') || context.date.slice(0, 7) },
    coverage: { available: ['sales', 'sales_volume', 'orders', 'visitors', 'stock', 'refund_amount', 'ad_cost', 'gross_profit', 'net_profit'], unavailable: [], source: '本地五店模拟数据 · 非真实经营记录' },
    latest_sync: { status: 'success', rows: scoped.length, finished_at: `${context.date}T23:59:59+08:00`, source_name: '本地演示生成器' } }
}
function business(params: Params, context: DemoContext): BusinessMetrics {
  const rows = cells(bundles(context, params, selectedDate(params, context), 'month'))
  const requested = str(params, 'group_by'); const group = (['platform', 'shop', 'category', 'product', 'operator'].includes(requested) ? requested : 'platform') as BusinessMetrics['group_by']
  const results = grouped(rows, row => ({ platform: row.shop.platform, shop: row.shop.id, category: row.item.category, product: `${row.shop.id}:${row.item.product.id}`, operator: row.item.operator })[group]).map(values => {
    const first = values[0]!; const result = businessRow(values)
    if (group === 'platform') result.platform = first.shop.platform
    if (group === 'shop') { result.shop = first.shop.name; result.platform = first.shop.platform }
    if (group === 'category') result.category_path = first.item.category
    if (group === 'operator') result.operator_name = first.item.operator
    if (group === 'product') Object.assign(result, { product_id: first.item.product.id, product_name: first.item.product.name, product_image_url: first.item.product.imageUrl, shop: first.shop.name, platform: first.shop.platform, category_path: first.item.category, operator_name: first.item.operator })
    return result
  })
  return { group_by: group, count: results.length, summary: businessRow(rows), results: order(results, params).slice(0, positiveInt(params.limit, 300)) }
}
function shopRows(params: Params, context: DemoContext): ShopData[] {
  const date = selectedDate(params, context)
  return order(bundles(context, params, date, 'month', 'shop').map(({ shop, snapshot }) => ({ id: shop.id, month: date!.slice(0, 7), shop: shop.name,
    sales: snapshot.totals.sales, sales_volume: snapshot.totals.units, orders: snapshot.totals.orders, visitors: snapshot.totals.visitors,
    conversion_rate: snapshot.totals.conversionRate / 100, ad_cost: snapshot.totals.adCost, ad_revenue: snapshot.totals.sales, roi: snapshot.totals.roi,
    profit: snapshot.totals.profit, profit_rate: ratio(snapshot.totals.profit, snapshot.totals.sales), sales_change_rate: change(snapshot.totals.sales, snapshot.previous.sales), visitors_change_rate: change(snapshot.totals.visitors, snapshot.previous.visitors) })), params)
}
function productRows(params: Params, context: DemoContext): ProductData[] {
  const date = selectedDate(params, context)
  return order(cells(bundles(context, params, date, 'month')).map(row => {
    const value = row.metrics; const score = 61 + row.item.index % 34
    return { id: `${row.shop.id}:${row.item.product.id}`, month: date!.slice(0, 7), shop: row.shop.name, product_id: row.item.product.id, product_name: row.item.product.name, product_image_url: row.item.product.imageUrl,
      sales: value.sales.toFixed(2), sales_volume: value.units, orders: value.orders, visitors: value.visitors, click_rate: (0.02 + row.item.index % 5 / 1000).toFixed(4), conversion_rate: String(value.conversionRate / 100), ad_cost: value.adCost.toFixed(2), roi: String(value.roi), profit: value.profit.toFixed(2), stock: stock(row),
      health_score: score, health_components: { sales_growth: score, traffic_growth: Math.min(100, score + 3), conversion_stability: Math.max(0, score - 4), profit_health: score + 1 } }
  }), params)
}
function catalogRows(params: Params, context: DemoContext): ProductCatalog[] {
  if (!selectedDate(params, context)) return []
  return order(DEMO_SHOPS.flatMap((shop, shopIndex) => catalog(context).filter(item => matches(item, shop, params)).map(item => ({
    id: shopIndex * 10000 + item.index + 1, organization: ORGANIZATION, platform: shop.platform, shop_id: shop.id, shop: shop.name,
    product_id: item.product.id, product_name: item.product.name, product_code: item.product.code, product_created_at: item.created,
    product_age_days: item.age, lifecycle: item.lifecycle, lifecycle_label: item.lifecycle === 'new' ? '新品' : item.lifecycle === 'mature' ? '老品' : '未知',
    product_image_url: item.product.imageUrl, last_seen_month: context.date.slice(0, 7), source: '演示档案（创建日期、生命周期均为模拟）', created_at: `${context.date}T00:00:00+08:00`, updated_at: `${context.date}T23:59:59+08:00`,
  }))), params, '-product_created_at')
}
function realtimeRow(rows: Cell[]): Record<string, string | number | null> {
  const total = sum(rows.map(row => row.metrics)); const business = businessRow(rows)
  const refund = business.refund_amount || 0; const pre = round(refund * 0.7)
  return { paid_amount: total.sales, paid_units: total.units, trade_count: total.orders, buyer_count: total.orders, gross_sales: total.sales,
    net_sales: business.net_sales, gross_profit: business.gross_profit, net_profit: business.net_profit, net_profit_margin: business.net_margin, gross_profit_margin: business.gross_margin,
    total_refund_amt: refund, total_success_refund_amt: refund, pre_ship_refund_amt: pre, post_ship_refund_amt: round(refund - pre),
    ad_cost: total.adCost, ad_click: Math.round(total.visitors * 0.35), ad_pv: Math.round(total.visitors * 14), ad_roi: total.roi,
    total_custom_cost: round(rows.reduce((value, row) => value + financial(row.metrics).custom, 0)) }
}
function realtime(params: Params, context: DemoContext): RealtimeDashboardData {
  const date = selectedDate(params, context, true); const values = bundles(context, params, date, 'today'); const rows = cells(values)
  const previousDate = date ? shiftDay(date, -1) : shiftDay(context.date, -1)
  const previousRows = cells(bundles(context, params, date ? previousDate : null, 'today'))
  const current = realtimeRow(rows); const previous = realtimeRow(previousRows)
  const definitions: Array<[string, string, RealtimeMetric['format']]> = [
    ['paid_amount', '成交金额', 'money'], ['gross_sales', '毛销售额', 'money'], ['net_sales', '净销售额', 'money'], ['gross_profit', '毛利润', 'money'],
    ['net_profit', '净利润', 'money'], ['net_profit_margin', '净利率', 'percent'], ['ad_cost', '广告花费', 'money'], ['total_custom_cost', '自定义成本', 'money'],
    ['gross_profit_margin', '毛利率', 'percent'], ['buyer_count', '买家数', 'int'], ['paid_units', '成交件数', 'int'], ['total_success_refund_amt', '成功退款', 'money'],
  ]
  const metrics = Object.fromEntries(definitions.map(([key, label, format]) => [key, { label, format, current: Number(current[key]), compare: Number(previous[key]), change_rate: change(Number(current[key]), Number(previous[key])) }]))
  const rank = (key: (row: Cell) => string, identity: (row: Cell) => Record<string, string>) => order(grouped(rows, key).map(group => ({ ...realtimeRow(group), ...identity(group[0]!) })), { ...params, ordering: str(params, 'ordering') || '-paid_amount' })
  return { date: date || str(params, 'date') || context.date, compare_date: previousDate, data_through: `${date || context.date} 23:59（完整日模拟）`, source: { name: '五店本地演示数据', status: 'limited', warning: '全部经营数字、时间和人员均为模拟；不是实时数据，不代表真实业务。ROI 为成交额 / 广告花费；利润率均以成交额为分母。' },
    available_shops: DEMO_SHOPS.map(shop => ({ store_id: shop.id, store_name: shop.name, platform_type: shop.platform, platform_name: shop.platform })), metrics,
    hourly_trend: { available: rows.length > 0, hours: Array.from({ length: 24 }, (_, index) => index), previous: Array.from({ length: 24 }, (_, hour) => round(values.reduce((value, row) => value + row.snapshot.hourly[hour]!.previous, 0))),
      current: values.map(row => ({ store_id: row.shop.id, store_name: row.shop.name, values: row.snapshot.hourly.map(hour => hour.current) })), warning: '按完整模拟日展示；小时金额之和与上方成交金额一致。' }, trend_granularity: 'hour',
    rankings: { shop: rank(row => row.shop.id, row => ({ store_id: row.shop.id, store_name: row.shop.name })),
      item: rank(row => row.item.product.id, row => ({ item_id: row.item.product.id, title: row.item.product.name, product_image_url: row.item.product.imageUrl })),
      platform_type: rank(row => row.shop.platform, row => ({ platform_type: row.shop.platform })),
      sku_code: rank(row => row.item.product.code || row.item.product.id, row => ({ sku_code: row.item.product.code, latest_sku_name: row.item.product.name })),
      op_manager: rank(row => row.item.operator, row => ({ op_manager: row.item.operator, op_manager_name: row.item.operator })) } }
}
function dashboard(params: Params, context: DemoContext): DashboardData {
  const date = selectedDate(params, context); const values = bundles(context, params, date, 'month')
  const total = sum(values.map(row => row.snapshot.totals)); const previous = sum(values.map(row => row.snapshot.previous))
  const keys: Array<[string, keyof DemoMetrics]> = [['sales', 'sales'], ['sales_volume', 'units'], ['orders', 'orders'], ['visitors', 'visitors'], ['conversion_rate', 'conversionRate'], ['ad_cost', 'adCost'], ['roi', 'roi'], ['profit', 'profit']]
  const metrics = Object.fromEntries(keys.map(([key, source]) => [key, { value: source === 'conversionRate' ? total[source] / 100 : total[source], change_rate: change(total[source], previous[source]) }]))
  const daily = date && values.length ? Array.from({ length: Number(date.slice(8)) }, (_, index) => {
    const day = `${date.slice(0, 7)}-${String(index + 1).padStart(2, '0')}`
    const value = sum(bundles(context, params, day, 'today').map(row => row.snapshot.totals))
    return { date: day, sales: value.sales, visitors: value.visitors, ad_cost: value.adCost, roi: value.roi }
  }) : []
  const abnormal = [...new Map(cells(values).map(row => [row.item.product.id, row.item])).values()].slice(0, 3).map(item => ({
    id: item.index + 1, date: date!, type: 'demo_review', level: 'info', product_id: item.product.id, product_name: item.product.name,
    product_image_url: item.product.imageUrl, description: `模拟复盘提示：${item.product.name}可进行转化与投放复盘`,
    suggestion: '仅演示异常转任务流程，请检查主图和投放计划；不是对真实商品的风险判断。',
  }))
  return { month: str(params, 'month') || date?.slice(0, 7) || null, previous_month: date ? monthOffset(date, -1) : null,
    comparison_label: '上月同期（模拟）', is_partial: !!date && date === context.date, data_through: date, available_months: months(context), metrics,
    monthly_trend: date ? Array.from({ length: 6 }, (_, index) => monthOffset(date, index - 5)).map(month => {
      const scoped = { ...params, month, date: '' }
      const end = month === date.slice(0, 7) ? date : shiftDay(`${monthOffset(`${month}-01`, 1)}-01`, -1)
      const value = sum(bundles(context, scoped, end, 'month').map(row => row.snapshot.totals))
      return { month, sales: value.sales, ad_cost: value.adCost, profit: value.profit, roi: value.roi }
    }) : [], daily_trend: daily, abnormal, abnormal_count: abnormal.length, task_summary: { pending: 0, in_progress: 0, completed: 0 } }
}

/** Read-only API-compatible demo responses. Unknown routes remain unhandled. */
export function handleBusinessDemo(request: DemoRequest, context: DemoContext): unknown | undefined {
  if (request.method !== 'GET') return undefined
  const { params, path } = request
  if (path === '/dashboard/realtime/') return realtime(params, context)
  if (path === '/dashboard/') return dashboard(params, context)
  if (path === '/business/dimensions/') return dimensions(params, context)
  if (path === '/business/monthly/') return business(params, context)
  if (path === '/shops/monthly/') { const results = shopRows(params, context); return { count: results.length, results } }
  if (path === '/products/monthly/') return paginate(productRows(params, context), request)
  if (path === '/product-catalog/') return paginate(catalogRows(params, context), request)
  return undefined
}

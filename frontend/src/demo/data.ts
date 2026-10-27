/** Local-only simulation. Catalog fields are display metadata, never business inputs. */
export interface DemoProduct {
  id: string
  name: string
  code: string
  imageUrl: string
  createdAt: string | null
}

export interface DemoShop { id: string; name: string; platform: string; color: string }
export type DemoScenario = 'steady' | 'growth' | 'pressure'
export type DemoPeriod = 'today' | 'month'
export interface DemoMetrics {
  sales: number
  units: number
  orders: number
  visitors: number
  adCost: number
  profit: number
  /** Percentage points: 3.5 means 3.5%, not 350%. */
  conversionRate: number
  /** Simulated total sales / advertising cost, not attributed advertising revenue. */
  roi: number
}

export const DEMO_SHOPS: DemoShop[] = [
  { id: 'demo-flagship', name: '演示旗舰店', platform: '综合电商', color: '#2474ff' },
  { id: 'demo-specialty', name: '演示专营店', platform: '综合电商', color: '#18a999' },
  { id: 'demo-lifestyle', name: '演示生活店', platform: '内容电商', color: '#8b5cf6' },
  { id: 'demo-selected', name: '演示优选店', platform: '内容电商', color: '#f59e0b' },
  { id: 'demo-outlet', name: '演示特惠店', platform: '特卖电商', color: '#ed648a' },
]

export interface DemoSnapshot {
  totals: DemoMetrics
  previous: DemoMetrics
  shops: (DemoShop & DemoMetrics)[]
  products: (DemoProduct & DemoMetrics)[]
  hourly: { hour: number; current: number; previous: number }[]
  trend: { date: string; sales: number; adCost: number; profit: number }[]
}

// Money stays in integer cents until the public API boundary.
interface Ledger {
  sales: number
  units: number
  orders: number
  visitors: number
  adCost: number
  profit: number
}

const DAY_MS = 86_400_000
const ANCHOR = Date.UTC(2026, 0, 1)
const HOURLY_WEIGHTS = [2, 1, 1, 1, 1, 2, 4, 6, 9, 12, 13, 15, 16, 13, 12, 13, 15, 18, 22, 26, 29, 25, 17, 9]

function emptyLedger(): Ledger {
  return { sales: 0, units: 0, orders: 0, visitors: 0, adCost: 0, profit: 0 }
}

function add(target: Ledger, source: Ledger): void {
  target.sales += source.sales
  target.units += source.units
  target.orders += source.orders
  target.visitors += source.visitors
  target.adCost += source.adCost
  target.profit += source.profit
}

function metrics(value: Ledger): DemoMetrics {
  return {
    sales: value.sales / 100,
    units: value.units,
    orders: value.orders,
    visitors: value.visitors,
    adCost: value.adCost / 100,
    profit: value.profit / 100,
    conversionRate: value.visitors ? value.orders / value.visitors * 100 : 0,
    roi: value.adCost ? value.sales / value.adCost : 0,
  }
}

function hash(value: string): number {
  let seed = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    seed = Math.imul(seed ^ value.charCodeAt(index), 16777619)
  }
  return seed >>> 0
}

function utcDate(year: number, month: number, day: number): Date {
  // setUTCFullYear avoids Date.UTC's special interpretation of years 0–99.
  const value = new Date(0)
  value.setUTCFullYear(year, month, day)
  value.setUTCHours(0, 0, 0, 0)
  return value
}

function dateKey(value: Date): string {
  return `${String(value.getUTCFullYear()).padStart(4, '0')}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-${String(value.getUTCDate()).padStart(2, '0')}`
}

function parseDate(value: string): Date {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error('演示日期必须使用 YYYY-MM-DD 格式。')
  }
  const [year, month, day] = value.split('-').map(Number) as [number, number, number]
  const parsed = utcDate(year, month - 1, day)
  if (year < 1 || dateKey(parsed) !== value) {
    throw new Error(`无效的演示日期：${value}。`)
  }
  return parsed
}

/** Today's Beijing calendar date, independent of the browser's local timezone. */
export function demoDate(): string {
  return dateKey(new Date(Date.now() + 8 * 60 * 60 * 1000))
}

function dailyLedger(productId: string, shopId: string, date: Date, scenario: DemoScenario): Ledger {
  // Length-safe tuples prevent collisions caused by IDs containing separators.
  const identity = JSON.stringify([productId, shopId])
  const productSeed = hash(productId)
  const seed = hash(identity)
  const daySeed = hash(JSON.stringify([productId, shopId, dateKey(date)]))
  const shopScale = 0.72 + hash(shopId) % 70 / 100
  const noise = 0.96 + daySeed % 9 / 100
  const weekend = date.getUTCDay() === 0 || date.getUTCDay() === 6 ? 1.12 : 1
  // A fixed calendar anchor, never the currently selected date: changing a filter
  // cannot rewrite historical rows. Bound the exponent for ancient/future dates.
  const elapsedDays = (date.getTime() - ANCHOR) / DAY_MS
  const growth = 1.3 * Math.exp(Math.max(-2, Math.min(2, elapsedDays * 0.0013)))
  const scenarioScale = scenario === 'growth' ? growth : scenario === 'pressure' ? 0.86 : 1
  const orders = Math.max(1, Math.round((3 + seed % 14) * shopScale * noise * weekend * scenarioScale))
  const units = orders + Math.floor(orders * (0.08 + seed % 28 / 100))
  const unitPriceCents = 3900 + productSeed % 26000
  const sales = units * unitPriceCents
  const targetConversion = (240 + seed % 240) / 10000 * (scenario === 'pressure' ? 0.58 : scenario === 'growth' ? 1.14 : 1)
  const visitors = Math.ceil(orders / targetConversion)
  const advertisingBasisPoints = scenario === 'pressure' ? 3500 + seed % 1900 : scenario === 'growth' ? 1050 + seed % 650 : 1300 + seed % 900
  const adCost = Math.round(sales * advertisingBasisPoints / 10000)
  const grossMarginBasisPoints = 3900 + productSeed % 1200
  const profit = Math.round(sales * grossMarginBasisPoints / 10000) - adCost - units * (260 + seed % 300)
  return { sales, units, orders, visitors, adCost, profit }
}

/** Largest-remainder allocation preserves every cent and uses stable tie breaks. */
function hourlyCents(sales: number, productId: string, shopId: string, date: Date): number[] {
  const seed = hash(JSON.stringify([productId, shopId, dateKey(date), 'hours']))
  const weights = HOURLY_WEIGHTS.map((weight, hour) => weight * (90 + (seed >>> (hour % 24)) % 21))
  const totalWeight = weights.reduce((total, value) => total + value, 0)
  const values = weights.map(weight => Math.floor(sales * weight / totalWeight))
  const remaining = sales - values.reduce((total, value) => total + value, 0)
  const priorities = weights.map((weight, hour) => ({ hour, remainder: sales * weight % totalWeight }))
    .sort((a, b) => b.remainder - a.remainder || a.hour - b.hour)
  for (let index = 0; index < remaining; index += 1) {
    values[priorities[index]!.hour]! += 1
  }
  return values
}

/**
 * Full simulated days, not a live feed. Monetary outputs are yuan.
 * today: selected day vs yesterday. month: month-to-date vs the previous
 * month's matching day count, clamped at its last day (e.g. Mar 31 vs Feb 28).
 * hourly always describes the selected day/yesterday; trend always describes
 * the selected month through its selected day, irrespective of summary period.
 * Products are keyed by ID; duplicate IDs retain their first display metadata.
 */
export function buildDemoSnapshot(
  products: DemoProduct[],
  options: { date: string; shopId: string; period: DemoPeriod; scenario: DemoScenario },
): DemoSnapshot {
  const selectedDate = parseDate(options.date)
  if (options.period !== 'today' && options.period !== 'month') throw new Error('不支持的演示统计周期。')
  if (!['steady', 'growth', 'pressure'].includes(options.scenario)) throw new Error('不支持的演示场景。')
  const productsById = new Map<string, DemoProduct>()
  for (const product of products) {
    if (!productsById.has(product.id)) productsById.set(product.id, product)
  }
  const catalog = [...productsById.values()]
  const shops = options.shopId === '' ? DEMO_SHOPS : DEMO_SHOPS.filter(shop => shop.id === options.shopId)
  const totals = emptyLedger()
  const previous = emptyLedger()
  const shopTotals = new Map(shops.map(shop => [shop.id, emptyLedger()]))
  const productTotals = new Map(catalog.map(product => [product.id, emptyLedger()]))
  const currentHours = Array<number>(24).fill(0)
  const previousHours = Array<number>(24).fill(0)
  const trend: DemoSnapshot['trend'] = []
  const yesterday = new Date(selectedDate.getTime() - DAY_MS)
  const year = selectedDate.getUTCFullYear()
  const month = selectedDate.getUTCMonth()
  const day = selectedDate.getUTCDate()

  for (let dayNumber = 1; dayNumber <= day; dayNumber += 1) {
    const date = utcDate(year, month, dayNumber)
    const dailyTotal = emptyLedger()
    const included = options.period === 'month' || dayNumber === day
    for (const shop of shops) {
      for (const product of catalog) {
        const ledger = dailyLedger(product.id, shop.id, date, options.scenario)
        add(dailyTotal, ledger)
        if (included) {
          add(totals, ledger)
          add(shopTotals.get(shop.id)!, ledger)
          add(productTotals.get(product.id)!, ledger)
        }
        if (dayNumber === day) {
          hourlyCents(ledger.sales, product.id, shop.id, date).forEach((value, hour) => { currentHours[hour]! += value })
        }
      }
    }
    trend.push({ date: dateKey(date), sales: dailyTotal.sales / 100, adCost: dailyTotal.adCost / 100, profit: dailyTotal.profit / 100 })
  }

  const previousMonthEnd = utcDate(year, month, 0)
  const previousDayCount = Math.min(day, previousMonthEnd.getUTCDate())
  const previousDates = options.period === 'today'
    ? [yesterday]
    : Array.from({ length: previousDayCount }, (_, index) => utcDate(year, month - 1, index + 1))
  for (const date of previousDates) {
    for (const shop of shops) {
      for (const product of catalog) add(previous, dailyLedger(product.id, shop.id, date, options.scenario))
    }
  }
  for (const shop of shops) {
    for (const product of catalog) {
      const ledger = dailyLedger(product.id, shop.id, yesterday, options.scenario)
      hourlyCents(ledger.sales, product.id, shop.id, yesterday).forEach((value, hour) => { previousHours[hour]! += value })
    }
  }

  return {
    totals: metrics(totals),
    previous: metrics(previous),
    shops: shops.map(shop => ({ ...shop, ...metrics(shopTotals.get(shop.id)!) })),
    products: catalog.map(product => ({ ...product, ...metrics(productTotals.get(product.id)!) })),
    hourly: currentHours.map((value, hour) => ({ hour, current: value / 100, previous: previousHours[hour]! / 100 })),
    trend,
  }
}

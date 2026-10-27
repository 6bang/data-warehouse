import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { Buffer } from 'node:buffer'
import test from 'node:test'
import ts from 'typescript'

// Run the pure production TypeScript module, without adding a test framework or
// reaching the API. Fixtures deliberately contain no customer data.
const source = await readFile(new URL('../src/demo/data.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
})
const { buildDemoSnapshot, DEMO_SHOPS, demoDate } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

const fixtures = [
  { id: 'fixture-a', name: '测试商品甲', code: 'TEST-A', imageUrl: 'https://example.invalid/a.jpg', createdAt: '2024-01-01' },
  { id: 'fixture-b', name: '测试商品乙', code: 'TEST-B', imageUrl: '', createdAt: null },
  { id: 'fixture-c', name: '测试商品丙', code: 'TEST-C', imageUrl: 'https://example.invalid/c.jpg', createdAt: '2026-01-01T00:00:00Z' },
]
const amounts = ['sales', 'adCost', 'profit']
const counts = ['units', 'orders', 'visitors']
const metrics = [...amounts, ...counts, 'conversionRate', 'roi']
const options = { date: '2026-10-26', shopId: '', period: 'today', scenario: 'steady' }
const snap = (changes = {}, products = fixtures) => buildDemoSnapshot(products, { ...options, ...changes })
const cents = (number) => Math.round(number * 100)

function assertTotals(actual, rows, label) {
  for (const key of amounts) {
    assert.equal(cents(actual[key]), rows.reduce((total, row) => total + cents(row[key]), 0), `${label}: ${key} reconciles to cents`)
  }
  for (const key of counts) {
    assert.equal(actual[key], rows.reduce((total, row) => total + row[key], 0), `${label}: ${key} reconciles exactly`)
  }
}

function assertRates(row) {
  const conversion = row.visitors === 0 ? 0 : row.orders / row.visitors * 100
  const roi = row.adCost === 0 ? 0 : row.sales / row.adCost
  assert.ok(Math.abs(row.conversionRate - conversion) <= 0.005001, 'conversion rate uses aggregate orders/visitors, in percent')
  assert.ok(Math.abs(row.roi - roi) <= 0.005001, 'ROI uses aggregate sales/adCost')
}

function assertFinite(value) {
  if (typeof value === 'number') assert.ok(Number.isFinite(value), 'no NaN or Infinity anywhere in a snapshot')
  else if (Array.isArray(value)) value.forEach(assertFinite)
  else if (value && typeof value === 'object') Object.values(value).forEach(assertFinite)
}

test('five unique virtual shops and a valid demo date', () => {
  assert.equal(DEMO_SHOPS.length, 5)
  assert.equal(new Set(DEMO_SHOPS.map((shop) => shop.id)).size, 5)
  for (const shop of DEMO_SHOPS) for (const key of ['id', 'name', 'platform', 'color']) assert.ok(typeof shop[key] === 'string' && shop[key].length > 0)
  assert.match(demoDate(), /^\d{4}-\d{2}-\d{2}$/)
})

test('deterministic generation does not mutate frozen input or options', () => {
  const frozen = Object.freeze(fixtures.map((product) => Object.freeze({ ...product })))
  const frozenOptions = Object.freeze({ ...options })
  const before = JSON.stringify(frozen)
  assert.deepEqual(buildDemoSnapshot(frozen, frozenOptions), buildDemoSnapshot(frozen, frozenOptions))
  assert.equal(JSON.stringify(frozen), before)
  assert.deepEqual(frozenOptions, options)
})

test('empty catalog has zero metrics and never invents products', () => {
  for (const period of ['today', 'month']) {
    const result = snap({ period }, [])
    assert.equal(result.products.length, 0)
    for (const row of [result.totals, result.previous, ...result.shops]) for (const key of metrics) assert.equal(row[key], 0)
    for (const point of result.hourly) assert.equal(point.current + point.previous, 0)
    for (const point of result.trend) assert.equal(point.sales + point.adCost + point.profit, 0)
    assertFinite(result)
  }
})

test('unknown shop never silently exposes all-shop simulated results', () => {
  const result = snap({ shopId: 'shop-that-does-not-exist' })
  for (const key of metrics) assert.equal(result.totals[key], 0)
  assert.equal(result.shops.length, 0)
  assertFinite(result)
})

test('all shops, each filtered shop and product totals reconcile across scenarios and periods', () => {
  for (const scenario of ['steady', 'growth', 'pressure']) for (const period of ['today', 'month']) {
    const result = snap({ scenario, period })
    assert.equal(result.shops.length, 5)
    assertTotals(result.totals, result.shops, `${scenario}/${period}/shops`)
    assertTotals(result.totals, result.products, `${scenario}/${period}/products`)
    const singles = DEMO_SHOPS.map((shop) => snap({ scenario, period, shopId: shop.id }))
    assertTotals(result.totals, singles.map((single) => single.totals), 'filtered shops')
    assertTotals(result.previous, singles.map((single) => single.previous), 'filtered previous shops')
    for (const [index, single] of singles.entries()) {
      assert.equal(single.shops.length, 1)
      assert.equal(single.shops[0].id, DEMO_SHOPS[index].id)
      assertTotals(single.totals, single.products, 'single-shop products')
    }
    for (const row of [result.totals, result.previous, ...result.shops, ...result.products]) {
      assertRates(row)
      for (const key of counts) assert.ok(Number.isInteger(row[key]) && row[key] >= 0, `${key} is a nonnegative integer`)
    }
    assertFinite(result)
  }
})

test('only provided product identity, name, code and image are shown', () => {
  const result = snap()
  assert.equal(result.products.length, fixtures.length)
  for (const row of result.products) {
    const original = fixtures.find((product) => product.id === row.id)
    assert.ok(original, 'product identity must originate in the authorized catalog')
    for (const key of ['name', 'code', 'imageUrl', 'createdAt']) assert.equal(row[key], original[key])
  }
})

test('daily hourly chart is always 24 hours and reconciles both days', () => {
  for (const shopId of ['', DEMO_SHOPS[0].id]) {
    const daily = snap({ shopId })
    assert.equal(daily.hourly.length, 24)
    assert.equal(new Set(daily.hourly.map((point) => point.hour)).size, 24)
    assert.equal(cents(daily.totals.sales), daily.hourly.reduce((sum, point) => sum + cents(point.current), 0))
    assert.equal(cents(daily.previous.sales), daily.hourly.reduce((sum, point) => sum + cents(point.previous), 0))
    assert.deepEqual(snap({ shopId, period: 'month' }).hourly, daily.hourly)
  }
})

test('monthly daily trend matches independent daily snapshots and month totals', () => {
  for (const date of ['2024-02-29', '2025-02-28', '2026-04-30', '2026-12-31', '2027-01-01']) {
    const monthly = snap({ date, period: 'month' })
    const dayCount = Number(date.slice(-2))
    assert.equal(monthly.trend.length, dayCount)
    assert.equal(monthly.trend[0].date, `${date.slice(0, 8)}01`)
    assert.equal(monthly.trend.at(-1).date, date)
    const days = monthly.trend.map((point) => {
      const daily = snap({ date: point.date })
      for (const key of amounts) assert.equal(cents(point[key]), cents(daily.totals[key]), `${point.date}: trend ${key}`)
      return daily.totals
    })
    assertTotals(monthly.totals, days, `${date}/month`)
    assert.deepEqual(monthly.trend, snap({ date }).trend)
    assertFinite(monthly)
  }
})

test('previous day handles leap day and calendar/year boundaries', () => {
  for (const [current, previous] of [['2024-03-01', '2024-02-29'], ['2025-03-01', '2025-02-28'], ['2027-01-01', '2026-12-31']]) {
    assert.deepEqual(snap({ date: current }).previous, snap({ date: previous }).totals)
  }
})

test('previous month is same progress, clipped at the prior month end', () => {
  for (const [current, previous] of [['2024-03-31', '2024-02-29'], ['2025-03-31', '2025-02-28'], ['2026-05-31', '2026-04-30'], ['2027-01-15', '2026-12-15']]) {
    assert.deepEqual(snap({ date: current, period: 'month' }).previous, snap({ date: previous, period: 'month' }).totals)
  }
})

test('scenario switching changes simulation, but never product identities', () => {
  const steady = snap()
  for (const scenario of ['growth', 'pressure']) {
    const changed = snap({ scenario })
    assert.notDeepEqual(changed.totals, steady.totals)
    assert.deepEqual(changed.products.map((row) => row.id).sort(), steady.products.map((row) => row.id).sort())
    assertFinite(changed)
  }
})

test('metadata and input ordering never alter simulated business totals', () => {
  const changedMetadata = fixtures.map((product) => ({ ...product, name: '改名', code: '', imageUrl: '', createdAt: null }))
  assert.deepEqual(snap({}, changedMetadata).totals, snap().totals)
  assert.deepEqual(snap({}, [...fixtures].reverse()).totals, snap().totals)
})

test('invalid calendar dates and unsupported filters are explicitly rejected', () => {
  for (const date of ['2025-02-29', '2026-04-31', '2026-13-01', '2026-00-01', '2026-01-00', '2026-1-01', 'not-a-date']) {
    assert.throws(() => snap({ date }), `reject ${date} instead of silently rolling the calendar`)
  }
  assert.throws(() => snap({ period: 'year' }))
  assert.throws(() => snap({ scenario: 'unknown' }))
})

test('public catalog and deterministic generator have no business API or authentication dependencies', async () => {
  const catalog = await readFile(new URL('../src/demo/catalog.ts', import.meta.url), 'utf8')
  assert.match(catalog, /fetch\s*\(\s*['"]\/demo-products\.json['"]/)
  assert.doesNotMatch(catalog, /@\/api|axios|Authorization|access_token|refresh_token/)
  assert.doesNotMatch(catalog, /\.(?:post|put|patch|delete|request)\s*(?:<[^>]*>)?\s*\(/i)
  for (const text of [catalog, source]) {
    assert.doesNotMatch(text, /['"]\/(?:api|product-catalog|users\/me|imports|sync|data-import|operation-plans|tasks|strategies|dashboard|business)\//)
    assert.doesNotMatch(text, /localStorage\.setItem|sessionStorage\.setItem|indexedDB/)
  }
  assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|axios)\b/)
})

// Bind browser primitives around the production module. No live requests, token,
// backend process or global mutations are needed for the public catalog tests.
const catalogSource = await readFile(new URL('../src/demo/catalog.ts', import.meta.url), 'utf8')
const catalogJs = ts.transpileModule(catalogSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
assert.doesNotMatch(catalogJs, /^import /m, 'public catalog must have no runtime API/auth imports')
const catalogFactory = `export function bindCatalog(fetch, setTimeout = globalThis.setTimeout, clearTimeout = globalThis.clearTimeout) {\n${catalogJs.replace(/export /g, '')}\nreturn loadDemoCatalog;\n}`
const { bindCatalog } = await import(`data:text/javascript;base64,${Buffer.from(catalogFactory).toString('base64')}`)
const row = (id, extra = {}) => ({ id, name: `测试商品${id}`, code: `CODE-${id}`, imageUrl: '', createdAt: null, ...extra })
const response = (products, extra = {}) => ({ ok: true, status: 200, json: async () => ({ version: 1, products }), ...extra })

test('public catalog requests one static JSON without credentials and caps at 60 unique products', async () => {
  const calls = []
  const controller = new AbortController()
  const load = bindCatalog(async (...args) => {
    calls.push(args)
    return response(Array.from({ length: 70 }, (_, index) => row(String(index), { organization: 'SOURCE-ONLY', shop: 'SOURCE-ONLY', sales: 999, profit: 888, createdAt: '2026-01-01' })))
  })
  const result = await load(controller.signal)
  assert.equal(result.length, 60)
  assert.equal(new Set(result.map((product) => product.id)).size, 60)
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], '/demo-products.json')
  assert.equal(calls[0][1].credentials, 'omit')
  assert.equal(calls[0][1].method || 'GET', 'GET')
  assert.ok(calls[0][1].signal instanceof AbortSignal)
  assert.doesNotMatch(JSON.stringify(calls), /Authorization|Bearer|token/i)
  for (const product of result) {
    assert.deepEqual(Object.keys(product).sort(), ['id', 'name', 'code', 'imageUrl', 'createdAt'].sort())
    assert.doesNotMatch(JSON.stringify(product), /SOURCE-ONLY/)
    assert.equal(product.createdAt, null, 'public samples must not retain archive dates')
  }
})

test('public catalog deduplicates identity, skips invalid rows and ignores external next URLs', async () => {
  const calls = []
  const load = bindCatalog(async (url, config) => {
    calls.push({ url, config })
    return response([row('same'), row('same'), row('other'), row('', { name: '' }), null, {}, row('nameless', { name: ' ' })], {
      json: async () => ({ version: 1, products: [row('same'), row('same'), row('other'), row('', { name: '' }), null, {}, row('nameless', { name: ' ' })], next: 'https://example.invalid/unsafe-next' }),
    })
  })
  const result = await load()
  assert.equal(result.length, 2)
  assert.equal(calls.length, 1, 'public snapshot is a single bounded request')
  assert.equal(calls[0].url, '/demo-products.json')
})

test('empty, malformed and failed catalog reads cannot fabricate fallback products', async () => {
  assert.deepEqual(await bindCatalog(async () => response([]))(), [])
  for (const invalid of [null, {}, { version: 1, products: null }, { version: 2, products: [] }]) {
    await assert.rejects(bindCatalog(async () => response([], { json: async () => invalid }))())
  }
  await assert.rejects(bindCatalog(async () => response([], { ok: false, status: 503 }))())
  await assert.rejects(bindCatalog(async () => response([], { json: async () => { throw new SyntaxError('invalid JSON') } }))())
  await assert.rejects(bindCatalog(async () => { throw new Error('fixture network failure') })(), /fixture network failure/)
})

test('catalog accepts only exact shipped local image filenames and neutralizes hostile URLs', async () => {
  const accepted = ['/demo-assets/product-001.svg', '/demo-assets/product-060.svg']
  const rejected = [
    'https://example.invalid/image.svg', 'http://example.invalid/image.svg', '//example.invalid/image.svg',
    'data:image/svg+xml,<svg/>', 'javascript:alert(1)', '/demo-assets/../private.svg',
    '/demo-assets/%2e%2e/private.svg', '/demo-assets/product-001.svg?token=fixture',
    '/demo-assets/product-001.svg#fragment', '/demo-assets/product-001.svg/',
    '/demo-assets/product-000.svg', '/demo-assets/product-061.svg', '/demo-assets/product-1.svg',
    '/demo-assets/product-001.SVG', '/demo-assets/product-001.png', '/demo-assets/nested/product-001.svg',
    ' /demo-assets/product-001.svg', '/demo-assets/product-001.svg ',
    '/demo-assets/product-001.svg\n', '/demo-assets/product-001.svg\u0000',
    '/demo-assets\\product-001.svg', '/demo-assets/%70roduct-001.svg',
  ]
  const input = [...accepted, ...rejected]
  const products = await bindCatalog(async () => response(input.map((imageUrl, index) => row(String(index), { imageUrl }))))()
  assert.equal(products.length, input.length, 'unsafe image must not drop otherwise valid product')
  assert.deepEqual(products.slice(0, accepted.length).map(product => product.imageUrl), accepted)
  assert.ok(products.slice(accepted.length).every(product => product.imageUrl === ''))
})

test('catalog propagates caller cancellation and enforces a 15-second timeout', async () => {
  for (const mode of ['cancel', 'timeout']) {
    const controller = new AbortController()
    let timer
    let cleared = false
    let requestedSignal
    const load = bindCatalog(async (_url, config) => {
      requestedSignal = config.signal
      return new Promise((_resolve, reject) => {
        if (config.signal.aborted) reject(config.signal.reason)
        else config.signal.addEventListener('abort', () => reject(config.signal.reason), { once: true })
      })
    }, (callback, milliseconds) => {
      assert.equal(milliseconds, 15000)
      timer = callback
      return 42
    }, () => { cleared = true })
    const pending = load(controller.signal)
    const rejection = assert.rejects(pending)
    if (mode === 'cancel') controller.abort()
    else timer()
    await rejection
    assert.equal(requestedSignal.aborted, true)
    assert.equal(cleared, true)
  }
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(bindCatalog(async (_url, config) => {
    assert.equal(config.signal.aborted, true)
    throw config.signal.reason
  })(controller.signal))
})

test('shipped public snapshot contains only display metadata, no real business or account fields', async () => {
  const snapshot = JSON.parse(await readFile(new URL('../public/demo-products.json', import.meta.url), 'utf8'))
  assert.deepEqual(Object.keys(snapshot).sort(), ['products', 'version'])
  assert.equal(snapshot.version, 1)
  assert.equal(snapshot.products.length, 60)
  assert.equal(new Set(snapshot.products.map(product => product.id)).size, snapshot.products.length)
  for (const [index, product] of snapshot.products.entries()) {
    assert.deepEqual(Object.keys(product).sort(), ['code', 'createdAt', 'id', 'imageUrl', 'name'])
    assert.equal(product.createdAt, null)
    for (const key of ['id', 'name', 'code', 'imageUrl']) assert.equal(typeof product[key], 'string')
    assert.ok(product.id.trim() && product.name.trim())
    const serial = String(index + 1).padStart(3, '0')
    assert.equal(product.id, `synthetic-item-${serial}`)
    assert.equal(product.code, `DEMO-GEO-${serial}`)
    assert.match(product.name, /^虚构样品 · /)
    assert.equal(product.imageUrl, `/demo-assets/product-${serial}.svg`)
    const svg = await readFile(new URL(`../public${product.imageUrl}`, import.meta.url), 'utf8')
    assert.match(svg, /<svg\s/)
    assert.doesNotMatch(svg, /<\s*(?:script|foreignObject|image)\b|\b(?:href|onload|onclick)\s*=|url\s*\(/i)
    assert.doesNotMatch(JSON.stringify(product), /access_token|refresh_token|password|organization_id|shop_id|user_id/i)
  }
})

test('demo reuses all original routes and MainLayout, with public metadata and private business guards', async () => {
  const router = await readFile(new URL('../src/router/index.ts', import.meta.url), 'utf8')
  const layout = await readFile(new URL('../src/layouts/MainLayout.vue', import.meta.url), 'utf8')
  const login = await readFile(new URL('../src/views/LoginView.vue', import.meta.url), 'utf8')
  assert.match(login, /\/demo/)
  assert.match(login, /免登录/)
  const routerJs = ts.transpileModule(router, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  const contracts = await readFile(new URL('../src/demo/contracts.ts', import.meta.url), 'utf8')
  const contractsJs = ts.transpileModule(contracts, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
  const factory = `export function makeRouter(token) {\n${contractsJs.replace(/export /g, '')}\nconst MainLayout = 'REAL_LAYOUT'; const localStorage = { getItem: () => token }; const createWebHistory = () => ({}); const createRouter = config => ({ ...config, options: config, addRoute(route) { this.routes.push(route) }, beforeEach(fn) { this.guard = fn } });\n${routerJs.replace(/^import .*;\s*$/gm, '').replace('export default router;', 'return router;')}\n}`
  const { makeRouter } = await import(`data:text/javascript;base64,${Buffer.from(factory).toString('base64')}`)
  for (const token of [null, 'existing-token']) {
    const instance = makeRouter(token)
    const normal = instance.routes.find(route => route.path === '/')
    const demo = instance.routes.find(route => route.path === '/demo')
    assert.equal(demo.component, normal.component)
    assert.equal(demo.redirect, '/demo/realtime')
    assert.equal(demo.children.length, 13)
    for (const [index, route] of demo.children.entries()) {
      assert.equal(route.component, normal.children[index].component, 'same lazy page factory, not a copied view')
      assert.equal(route.path, normal.children[index].path)
      assert.equal(route.meta.demo, true)
      assert.equal(instance.guard({ path: `/demo/${route.path}`, meta: route.meta }, { meta: {} }), true)
      if (!token) assert.equal(instance.guard({ path: `/${route.path}`, meta: {} }, { meta: {} }), '/login')
      assert.equal(instance.guard({ path: `/${route.path}`, fullPath: `/${route.path}?sample=1`, meta: {} }, { meta: { demo: true } }), `/demo/${route.path}?sample=1`)
    }
    for (const path of ['/demo', '/demo/']) assert.equal(instance.guard({ path, meta: demo.meta }, { meta: {} }), true)
    assert.equal(instance.guard({ path: '/demo-not-public', meta: {} }, { meta: {} }), token ? undefined : '/login')
  }
  assert.match(layout, /<router-view v-if="pageAllowed"/)
  assert.match(layout, /暂无页面访问权限/)
  assert.doesNotMatch(layout, /router\.replace\([^\n]+\|\| '\/login'\)/, 'zero permissions must not bounce between login and a forbidden route')
})

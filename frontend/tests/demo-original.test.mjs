import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

// Execute the production transport and handlers. Only browser primitives and
// toast presentation are bound; no backend, actual credential, or network exists.
const require = createRequire(import.meta.url)
const root = fileURLToPath(new URL('../src/', import.meta.url))
const fixture = Array.from({ length: 9 }, (_, i) => ({ id: `public-${i}`, name: `公开商品 ${i}`, code: `CODE-${i}`, imageUrl: '', createdAt: null }))
function sandbox(pathname = '/demo/realtime') {
  const cache = new Map(), fetches = [], notices = [], storageWrites = [], network = []
  const storage = new Map([['access_token', 'TEST_ONLY_NOT_A_REAL_TOKEN'], ['refresh_token', 'TEST_ONLY_NOT_A_REFRESH_TOKEN']])
  const window = { location: { pathname, href: '' } }
  const localStorage = { getItem: key => storage.get(key), setItem: (key, value) => { storageWrites.push(key); storage.set(key, value) }, removeItem: key => { storageWrites.push(key); storage.delete(key) } }
  const fetch = async (url, options) => { fetches.push({ url, options }); assert.equal(url, '/demo-products.json'); return { ok: true, json: async () => ({ version: 1, products: fixture }) } }
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename).exports
    const module = { exports: {} }; cache.set(filename, module)
    const source = readFileSync(filename, 'utf8').replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
    const javascript = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText
    const dependency = name => {
      if (name === 'element-plus') return { ElMessage: { info: item => notices.push(item) } }
      if (name.startsWith('@/')) return load(resolve(root, `${name.slice(2)}.ts`))
      if (name.startsWith('.')) return load(resolve(dirname(filename), `${name}.ts`))
      return require(name)
    }
    new Function('require', 'module', 'exports', 'window', 'localStorage', 'fetch', javascript)(dependency, module, module.exports, window, localStorage, fetch)
    return module.exports
  }
  const http = load(resolve(root, 'api/http.ts')).default
  http.defaults.adapter = async config => { network.push(config); throw new Error('NETWORK_IS_FORBIDDEN_IN_TEST') }
  return { http, window, storage, storageWrites, fetches, notices, network, load }
}
const cents = value => Math.round(Number(value) * 100)

test('production http overrides caller transports and strips credentials even with stored tokens', async () => {
  const env = sandbox()
  let suppliedAdapterCalls = 0
  const response = await env.http.get('/users/me/', { headers: { Authorization: 'Bearer TEST_ONLY', Cookie: 'session=TEST_ONLY' }, withCredentials: true, adapter: async () => { suppliedAdapterCalls++; throw new Error('must not run') } })
  assert.equal(response.data.username, '演示管理员')
  assert.equal(response.config.headers.get('Authorization'), undefined)
  assert.equal(response.config.headers.get('Cookie'), undefined)
  assert.equal(response.config.withCredentials, false)
  assert.equal(suppliedAdapterCalls, 0)
  assert.equal(env.fetches.length, 1)
  assert.equal(env.fetches[0].options.credentials, 'omit')
  assert.deepEqual(env.network, [])
  assert.deepEqual(env.storageWrites, [])
  assert.equal(env.storage.get('access_token'), 'TEST_ONLY_NOT_A_REAL_TOKEN')
})

test('unknown, external, import and malformed requests fail closed without refresh or network', async () => {
  const env = sandbox()
  for (const [index, request] of [
    () => env.http.get('/not-supported/'),
    () => env.http.get('https://example.invalid/api/v1/users/me/'),
    () => env.http.get('https://other.example.invalid/api/v1/users/me/'),
    () => env.http.get('//example.invalid/api/v1/users/me/'),
    () => env.http.get('https://example.invalid:443/api/v1/users/me/'),
    () => env.http.post('/imports/file/', new FormData()),
    () => env.http.post('/dashboard/', {}),
    () => env.http.post('/tasks/', '{bad JSON', { headers: { 'Content-Type': 'application/json' }, transformRequest: value => value }),
  ].entries()) await assert.rejects(request(), error => error.code === 'ERR_DEMO_REQUEST' && error.response.status === 400, `request ${index} must fail closed`)
  assert.deepEqual(env.network, [])
  assert.deepEqual(env.storageWrites, [])
  assert.equal(env.window.location.href, '')
})

test('non-demo requests retain the normal authentication transport boundary', async () => {
  const env = sandbox('/demo-not-public')
  await assert.rejects(env.http.get('/users/me/'), /NETWORK_IS_FORBIDDEN_IN_TEST/)
  assert.equal(env.network.length, 1)
  assert.equal(env.network[0].headers.get('Authorization'), 'Bearer TEST_ONLY_NOT_A_REAL_TOKEN')
  assert.equal(env.fetches.length, 0)
})

test('original dashboard, shop, BI and product responses reconcile over all five shops', async () => {
  const { http } = sandbox()
  const get = async (path, params = {}) => (await http.get(path, { params })).data
  const realtime = await get('/dashboard/realtime/')
  assert.equal(realtime.available_shops.length, 5)
  assert.equal(realtime.rankings.shop.length, 5)
  assert.equal(cents(realtime.metrics.paid_amount.current), realtime.rankings.shop.reduce((sum, row) => sum + cents(row.paid_amount), 0))
  assert.equal(cents(realtime.metrics.paid_amount.current), realtime.hourly_trend.current.flatMap(row => row.values).reduce((sum, value) => sum + cents(value), 0))
  for (const shop of realtime.available_shops) {
    const one = await get('/dashboard/realtime/', { shop: shop.store_name })
    assert.equal(one.rankings.shop.length, 1)
    assert.equal(one.rankings.shop[0].store_id, shop.store_id)
  }
  assert.equal((await get('/dashboard/realtime/', { shop: 'no-such-shop' })).metrics.paid_amount.current, 0)
  const dashboard = await get('/dashboard/')
  const shops = await get('/shops/monthly/')
  const products = await get('/products/monthly/', { page_size: 1000 })
  const bi = await get('/business/monthly/', { group_by: 'shop' })
  assert.equal(shops.count, 5)
  assert.equal(products.count, fixture.length * 5)
  assert.equal(cents(dashboard.metrics.sales.value), shops.results.reduce((sum, row) => sum + cents(row.sales), 0))
  assert.equal(cents(dashboard.metrics.sales.value), products.results.reduce((sum, row) => sum + cents(row.sales), 0))
  assert.equal(cents(dashboard.metrics.sales.value), cents(bi.summary.sales))
  assert.equal(cents(dashboard.metrics.sales.value), dashboard.daily_trend.reduce((sum, row) => sum + cents(row.sales), 0))
  const previousMonth = dashboard.available_months[1]
  assert.notEqual((await get('/dashboard/', { month: previousMonth })).metrics.sales.value, dashboard.metrics.sales.value)
})

test('catalog search, lifecycle, pagination and public identity are honored by the original API shape', async () => {
  const { http } = sandbox()
  const list = async params => (await http.get('/product-catalog/', { params })).data
  const all = await list({ page_size: 100 })
  assert.equal(all.count, 45)
  for (const row of all.results) {
    const original = fixture.find(product => product.id === row.product_id)
    assert.ok(original)
    assert.equal(row.product_name, original.name)
    assert.equal(row.product_code, original.code)
    assert.match(row.source, /模拟/)
  }
  assert.equal((await list({ search: 'CODE-0' })).count, 5)
  assert.equal((await list({ search: 'NO_SUCH_PRODUCT' })).count, 0)
  for (const lifecycle of ['new', 'mature', 'unknown']) {
    const result = await list({ lifecycle, page_size: 100 })
    assert.ok(result.count > 0)
    assert.ok(result.results.every(row => row.lifecycle === lifecycle))
  }
  const one = await list({ page_size: 2, page: 1 }), two = await list({ page_size: 2, page: 2 })
  assert.equal(one.results.length, 2)
  assert.notDeepEqual(one.results, two.results)
})

test('in-memory plan CRUD, task transitions, alert conversion and simulated AI do not persist', async () => {
  const env = sandbox(), { http } = env
  const plan = (await http.post('/operation-plans/', { plan_name: '测试内存计划', product_id: fixture[0].id, owner: 1 })).data
  assert.equal(plan.product_name, fixture[0].name)
  await http.patch(`/operation-plans/${plan.id}/`, { plan_name: '改名计划' })
  assert.equal((await http.get(`/operation-plans/${plan.id}/`)).data.plan_name, '改名计划')
  await http.delete(`/operation-plans/${plan.id}/`)
  await assert.rejects(http.get(`/operation-plans/${plan.id}/`))
  const task = (await http.post('/tasks/', { task_name: '测试内存任务', product_id: fixture[0].id })).data
  await assert.rejects(http.post(`/tasks/${task.id}/transition/`, { status: 'reviewed' }))
  for (const status of ['in_progress', 'completed', 'reviewed']) assert.equal((await http.post(`/tasks/${task.id}/transition/`, { status, result: '模拟完成', review_result: '模拟复盘' })).data.status, status)
  const alert = (await http.get('/strategy-alerts/')).data.results[0]
  const converted = (await http.post(`/strategy-alerts/${alert.id}/convert_plan/`, {})).data
  assert.equal(converted.alert, alert.id)
  assert.equal((await http.post(`/strategy-alerts/${alert.id}/convert_plan/`, {})).data.id, converted.id)
  const ai = (await http.post('/ai-analysis/', { question: '测试问题' })).data
  assert.equal(ai.simulation, true)
  assert.match(ai.output.provider_notice, /固定示例/)
  assert.deepEqual(env.storageWrites, [])
  assert.deepEqual(env.network, [])
  assert.equal((await sandbox().http.get('/tasks/', { params: { search: '测试内存任务' } })).data.count, 0, 'new page runtime resets mutations')
})

test('admin CRUD discards secrets, uses invalid demo keys, and only simulates integration actions', async () => {
  const env = sandbox(), { http } = env
  const created = (await http.post('/configuration/ai-providers/', { name: '测试模型', api_key: 'FAKE_SECRET_SENTINEL', password: 'FAKE_PASSWORD_SENTINEL' })).data
  const read = (await http.get(`/configuration/ai-providers/${created.id}/`)).data
  assert.doesNotMatch(JSON.stringify(read), /FAKE_SECRET_SENTINEL|FAKE_PASSWORD_SENTINEL/)
  await http.patch(`/configuration/ai-providers/${created.id}/`, { name: '修改演示模型', api_key: 'SECOND_FAKE_SECRET' })
  const patched = (await http.get(`/configuration/ai-providers/${created.id}/`)).data
  assert.equal(patched.name, '修改演示模型')
  assert.doesNotMatch(JSON.stringify(patched), /SECOND_FAKE_SECRET/)
  assert.match((await http.post(`/configuration/ai-providers/${created.id}/test/`, {})).data.message, /未连接/)
  const key = (await http.post('/configuration/mcp-tokens/', { name: '测试接入包' })).data
  assert.match(key.token, /^DEMO_ONLY_NOT_A_VALID_KEY_/)
  assert.equal(key.enabled, false)
  assert.match((await http.get('/configuration/mcp-servers/')).data.results[0].endpoint_url, /^https:\/\/example\.invalid\//)
  assert.match((await http.post('/data-sync/mcp/', { action: 'sync' })).data.message, /模拟/)
  await http.delete(`/configuration/ai-providers/${created.id}/`)
  await assert.rejects(http.get(`/configuration/ai-providers/${created.id}/`))
  assert.deepEqual(env.network, [])
  assert.deepEqual(env.storageWrites, [])
})

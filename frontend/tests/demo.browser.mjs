// Anonymous original-page regression. Actual API traffic is recorded and aborted.
import assert from 'node:assert/strict'
import process from 'node:process'
import { Buffer } from 'node:buffer'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const origin = process.env.DEMO_ORIGIN || 'http://127.0.0.1:5173'
const modulePath = process.env.PLAYWRIGHT_MODULE
const { chromium } = await import(modulePath ? pathToFileURL(resolve(modulePath)).href : 'playwright')
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}) })
const output = await mkdtemp(join(tmpdir(), 'warehouse-original-demo-'))
const apiRequests = [], errors = [], catalogRequests = [], externalRequests = []
const pages = [
  ['realtime', '实时数据'], ['dashboard', '经营总览'], ['business', '综合经营 BI'], ['shops', '店铺经营 BI'],
  ['products', '商品经营 BI'], ['product-catalog', '商品档案'], ['strategy-alerts', '运营策略预警'], ['strategies', '运营策略'],
  ['operation-plans', '运营计划'], ['tasks', '运营任务中心'], ['ai-analysis', 'AI 分析中心'], ['users', '用户与权限'], ['configuration', '配置中心'],
]
let activePage
async function anonymousContext() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await context.route(url => url.origin !== new URL(origin).origin, async route => {
    externalRequests.push(new URL(route.request().url()).hostname)
    await route.abort()
  })
  await context.route(url => url.pathname.startsWith('/api/'), async route => {
    apiRequests.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`)
    await route.abort()
  })
  context.on('page', page => {
    page.on('pageerror', error => errors.push(`${new URL(page.url()).pathname}: ${error.message}`))
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/demo-products.json') catalogRequests.push(request.allHeaders().then(headers => ({ method: request.method(), headers })))
    })
  })
  return context
}
async function ready(page) {
  await page.locator('.app-main > .page:not([role="status"])').waitFor({ timeout: 30000 })
  await page.locator('.el-loading-mask:visible').waitFor({ state: 'hidden', timeout: 30000 })
  await page.waitForTimeout(100)
}
async function navigate(page, label, path) {
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: label, exact: true }).click()
  await page.waitForURL(`**/demo/${path}`)
  await ready(page)
}
async function select(page, locator, name) {
  await locator.click()
  await page.getByRole('option', { name, exact: true }).click()
  await ready(page)
}
async function snapshot(page, name) {
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: join(output, `${name}.png`), fullPage: true, animations: 'disabled', timeout: 15000 })
}
async function noOverflow(page) { assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `page overflow: ${page.url()}`) }

try {
  const context = await anonymousContext()
  const page = activePage = await context.newPage()
  await page.goto(`${origin}/demo`, { waitUntil: 'domcontentloaded' })
  await page.waitForURL('**/demo/realtime')
  await ready(page)
  assert.equal(await page.evaluate(() => localStorage.getItem('access_token')), null)
  assert.equal(await page.locator('.side-nav nav button').count(), 13)
  assert.equal(await page.getByRole('button', { name: '数据同步', exact: true }).count(), 1)
  assert.equal(await page.getByRole('button', { name: '导入数据', exact: true }).count(), 1)
  assert.equal(await page.locator('.user-avatar').count(), 1)
  assert.match(await page.locator('.header-title small').innerText(), /模拟/)
  await page.locator('canvas').first().waitFor()
  assert.ok(await page.locator('.metric-row b').count() >= 8)
  await snapshot(page, 'realtime-desktop')
  await noOverflow(page)
  const allSales = await page.locator('.metric-row b').first().innerText()
  const shopSelect = page.locator('.hero-actions .el-select')
  await shopSelect.click()
  const shopNames = (await page.getByRole('option').allTextContents()).map(text => text.trim()).filter(text => text !== '全部店铺')
  assert.equal(shopNames.length, 5)
  await page.keyboard.press('Escape')
  for (const name of shopNames) {
    await select(page, shopSelect, name)
    assert.notEqual(await page.locator('.metric-row b').first().innerText(), allSales)
  }
  await select(page, shopSelect, '全部店铺')
  assert.equal(await page.locator('.metric-row b').first().innerText(), allSales)
  await page.getByRole('button', { name: '查看月度总览', exact: true }).click()
  await page.waitForURL('**/demo/dashboard')
  await ready(page)
  const monthSelect = page.locator('.page-toolbar .el-select').first()
  const initialMonth = await monthSelect.innerText()
  await monthSelect.click()
  const months = await page.getByRole('option').allTextContents()
  assert.ok(months.length >= 2)
  await page.getByRole('option', { name: months[1].trim(), exact: true }).click()
  await ready(page)
  assert.notEqual(await monthSelect.innerText(), initialMonth)
  assert.ok(await page.locator('canvas').count() > 0)
  for (const [path, label] of pages) {
    await navigate(page, label, path)
    assert.ok((await page.locator('.app-main').innerText()).trim().length > 10, `${path} must render original content`)
    await snapshot(page, path)
  }
  console.log('PASS original MainLayout, all 13 pages/navigation, five-shop and month filters, charts and internal link containment')

  await navigate(page, '商品档案', 'product-catalog')
  await page.waitForFunction(() => {
    const images = [...document.querySelectorAll('.product-cell img')]
    return images.length > 0 && images.every(image => image.complete && image.naturalWidth > 0)
  })
  for (const url of await page.locator('.product-cell img').evaluateAll(images => images.map(image => image.getAttribute('src')))) {
    assert.match(url, /^\/demo-assets\/product-\d{3}\.svg$/)
  }
  const productName = await page.locator('.product-cell strong').first().innerText()
  const search = page.getByPlaceholder('商品名称 / ID / 货号', { exact: true })
  await search.fill('NO_SUCH_DEMO_PRODUCT_987654')
  await search.press('Enter')
  await ready(page)
  assert.equal(await page.locator('.product-cell').count(), 0)
  await search.fill(productName)
  await search.press('Enter')
  await ready(page)
  assert.ok(await page.locator('.product-cell').count() > 0)
  assert.ok((await page.locator('.product-cell strong').allTextContents()).every(name => name === productName))
  await search.fill('')
  await search.press('Enter')
  await ready(page)
  await select(page, page.locator('.page-toolbar .el-select').first(), '新品（1-35天）')
  assert.ok((await page.locator('.el-table__body .el-tag').allTextContents()).every(text => text.includes('新品')))
  await page.getByRole('button', { name: '新建计划', exact: true }).first().click()
  const planDialog = page.getByRole('dialog', { name: '新建运营计划' })
  await planDialog.waitFor()
  await planDialog.getByLabel('计划名称', { exact: true }).fill('浏览器测试公开商品计划')
  await planDialog.getByRole('button', { name: '创建计划', exact: true }).click()
  await planDialog.waitFor({ state: 'hidden' })
  await navigate(page, '运营计划', 'operation-plans')
  await page.getByText('浏览器测试公开商品计划', { exact: true }).waitFor()
  await navigate(page, '运营任务中心', 'tasks')
  await page.getByRole('button', { name: '新建任务', exact: true }).click()
  const taskDialog = page.getByRole('dialog', { name: '新建运营任务' })
  await taskDialog.getByLabel('任务名称', { exact: true }).fill('浏览器测试内存闭环任务')
  await taskDialog.getByRole('button', { name: '创建', exact: true }).click()
  await taskDialog.waitFor({ state: 'hidden' })
  for (const action of ['开始执行', '标记完成', '完成复盘']) {
    const row = page.locator('.el-table__row').filter({ hasText: '浏览器测试内存闭环任务' })
    await row.getByRole('button', { name: action, exact: true }).click()
    await ready(page)
  }
  assert.match(await page.locator('.el-table__row').filter({ hasText: '浏览器测试内存闭环任务' }).innerText(), /已闭环/)
  await navigate(page, 'AI 分析中心', 'ai-analysis')
  await page.getByRole('button', { name: '开始月度分析', exact: true }).click()
  await page.getByText(/以下为固定示例分析/).waitFor()
  await page.getByRole('button', { name: '创建任务', exact: true }).click()
  await page.getByRole('button', { name: '已创建', exact: true }).waitFor()
  console.log('PASS product search/lifecycle, catalog-to-plan, task transition and simulated AI-to-task workflow')

  await navigate(page, '配置中心', 'configuration')
  const configTabs = await page.getByRole('tab').allTextContents()
  assert.equal(configTabs.length, 5)
  assert.ok(!configTabs.some(label => label.includes('经营数据同步')), 'third-party account/password sync tab must not ship')
  for (const label of configTabs) {
    await page.getByRole('tab', { name: label.trim(), exact: true }).click()
    await snapshot(page, `configuration-${configTabs.indexOf(label)}`)
  }
  await navigate(page, '用户与权限', 'users')
  await page.getByRole('tab', { name: '角色权限', exact: true }).click()
  await page.getByText('演示运营', { exact: true }).waitFor()
  await page.getByRole('button', { name: '数据同步', exact: true }).click()
  const sync = page.getByRole('dialog', { name: '同步经营数据' })
  await sync.waitFor()
  await sync.getByText('演示数据源（不会真实同步）', { exact: true }).waitFor()
  await sync.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '导入数据', exact: true }).click()
  const upload = page.getByRole('dialog', { name: '导入经营数据' })
  await upload.waitFor()
  await upload.locator('input[type=file]').setInputFiles({ name: 'synthetic.csv', mimeType: 'text/csv', buffer: Buffer.from('id,name\nTEST,synthetic\n') })
  await upload.getByRole('button', { name: '开始导入', exact: true }).click()
  await page.getByText(/演示模式只展示导入交互/).waitFor()
  await upload.getByRole('button', { name: '取消', exact: true }).click()
  console.log('PASS five configuration tabs, roles, original sync/import dialogs and fail-closed synthetic import')

  await navigate(page, '实时数据', 'realtime')
  await page.locator('.theme-toggle').click()
  await snapshot(page, 'realtime-theme-toggle')
  await page.locator('.theme-toggle').click()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400) // allow chart ResizeObserver and responsive layout to settle
  await page.waitForFunction(() => document.querySelectorAll('.el-message').length === 0)
  await noOverflow(page)
  await snapshot(page, 'realtime-mobile')
  assert.equal(await page.evaluate(() => document.body.getBoundingClientRect().width), 390)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '退出演示', exact: true }).click()
  await page.waitForURL('**/login')
  await page.getByRole('link', { name: /免登录体验/ }).click()
  await page.waitForURL('**/demo/realtime')
  await ready(page)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await ready(page)
  await page.goto(`${origin}/demo/`, { waitUntil: 'domcontentloaded' })
  await page.waitForURL('**/demo/realtime')
  await ready(page)
  await page.locator('.user-avatar').hover()
  await page.getByText('退出登录', { exact: true }).click()
  await page.waitForURL('**/login')
  for (const [path] of pages) {
    await page.goto(`${origin}/${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForURL('**/login')
  }
  assert.equal(await page.evaluate(() => localStorage.getItem('access_token')), null)
  await context.close()

  const stale = await anonymousContext()
  await stale.addInitScript(expected => {
    if (window.location.origin === expected) {
      localStorage.setItem('access_token', 'TEST_ONLY_NOT_A_REAL_TOKEN')
      localStorage.setItem('refresh_token', 'TEST_ONLY_NOT_A_REFRESH_TOKEN')
    }
  }, new URL(origin).origin)
  const stalePage = activePage = await stale.newPage()
  await stalePage.goto(`${origin}/demo`, { waitUntil: 'domcontentloaded' })
  await ready(stalePage)
  await stalePage.locator('.user-avatar').hover()
  await stalePage.getByText('演示管理员 · 模拟账户', { exact: true }).waitFor()
  await stalePage.keyboard.press('Escape')
  await navigate(stalePage, '配置中心', 'configuration')
  assert.equal(await stalePage.evaluate(() => localStorage.getItem('access_token')), 'TEST_ONLY_NOT_A_REAL_TOKEN')
  await stale.close()
  for (const mode of ['empty', 'error']) {
    const state = await anonymousContext()
    await state.route('**/demo-products.json', route => route.fulfill(mode === 'empty' ? { json: { version: 1, products: [] } } : { status: 503, json: { detail: 'synthetic outage' } }))
    const statePage = activePage = await state.newPage()
    await statePage.goto(`${origin}/demo`, { waitUntil: 'domcontentloaded' })
    if (mode === 'empty') {
      await ready(statePage)
      assert.equal(await statePage.locator('.metric-row b').first().innerText(), '¥0.00')
    } else await statePage.getByText('无法确认访问权限，请检查网络后重试。', { exact: false }).waitFor()
    await snapshot(statePage, `catalog-${mode}`)
    await state.close()
  }
  assert.ok(catalogRequests.length > 0)
  for (const request of await Promise.all(catalogRequests)) {
    assert.equal(request.method, 'GET')
    const headers = request.headers
    assert.equal(headers.authorization, undefined)
    assert.equal(headers.cookie, undefined)
  }
  assert.deepEqual(apiRequests, [])
  assert.deepEqual(externalRequests, [], 'demo must never request remote images, APIs or third-party services')
  assert.deepEqual(errors, [])
  console.log('PASS theme/mobile, login entry/exit, avatar logout, reload, 13 private routes, synthetic token, empty/error catalogs; zero API requests/page errors')
} catch (error) {
  if (activePage && !activePage.isClosed()) {
    await snapshot(activePage, 'failure').catch(() => {})
    console.error(`Failure page: ${activePage.url()}\n${(await activePage.locator('body').innerText()).slice(0, 8000)}`)
  }
  console.error('API requests:', apiRequests, 'Page errors:', errors)
  throw error
} finally {
  console.log(`Screenshots: ${output}`)
  await browser.close()
}

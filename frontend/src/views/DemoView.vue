<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import EChart from '@/components/EChart.vue'
import ProductImage from '@/components/ProductImage.vue'
import { loadDemoCatalog } from '@/demo/catalog'
import { buildDemoSnapshot, DEMO_SHOPS, demoDate, type DemoMetrics, type DemoPeriod, type DemoProduct, type DemoScenario } from '@/demo/data'

type DemoTab = 'realtime' | 'month' | 'shops' | 'products'
const tabs: { id: DemoTab; name: string; caption: string }[] = [
  { id: 'realtime', name: '实时经营', caption: '全天模拟' },
  { id: 'month', name: '月度总览', caption: '按日展开' },
  { id: 'shops', name: '店铺对比', caption: '五店同屏' },
  { id: 'products', name: '商品展示', caption: '虚构样本' },
]
const scenarios: { id: DemoScenario; name: string; description: string }[] = [
  { id: 'steady', name: '稳健经营', description: '模拟日常成交与平稳投放' },
  { id: 'growth', name: '增长场景', description: '模拟流量和成交同步增长' },
  { id: 'pressure', name: '投放压力', description: '模拟广告投入增加、利润承压' },
]
const activeTab = ref<DemoTab>('realtime')
const selectedDate = ref(demoDate())
const shopId = ref('')
const scenario = ref<DemoScenario>('steady')
const comparisonPeriod = ref<DemoPeriod>('today')
const catalog = ref<DemoProduct[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const page = ref(1)
const pageSize = 10
let request: AbortController | undefined
let disposed = false
let requestVersion = 0
const period = computed<DemoPeriod>(() => activeTab.value === 'month' ? 'month' : activeTab.value === 'realtime' ? 'today' : comparisonPeriod.value)
const date = computed(() => /^\d{4}-\d{2}-\d{2}$/.test(selectedDate.value || '') ? selectedDate.value : demoDate())
const snapshot = computed(() => buildDemoSnapshot(catalog.value, { date: date.value, shopId: shopId.value, period: period.value, scenario: scenario.value }))
const allShops = computed(() => buildDemoSnapshot(catalog.value, { date: date.value, shopId: '', period: period.value, scenario: scenario.value }).shops)
const rankedShops = computed(() => [...allShops.value].sort((a, b) => b.sales - a.sales))
const selectedShopName = computed(() => DEMO_SHOPS.find(shop => shop.id === shopId.value)?.name || '全部 5 家虚拟店铺')
const scenarioInfo = computed(() => scenarios.find(item => item.id === scenario.value)!)
const periodLabel = computed(() => period.value === 'today' ? `${date.value} · 全天` : `${date.value.slice(0, 7)}-01 至 ${date.value}`)
const filteredProducts = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return [...snapshot.value.products].filter(item => !query || `${item.name} ${item.code}`.toLocaleLowerCase().includes(query)).sort((a, b) => b.sales - a.sales)
})
const pageProducts = computed(() => filteredProducts.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch([search, shopId, scenario, date, period], () => { page.value = 1 })

const integer = (value: number) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)
const money = (value: number) => new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
const axisMoney = (value: number) => Math.abs(value) >= 10000 ? `${Number((value / 10000).toFixed(1))}万` : integer(value)
const percent = (value: number) => `${value.toFixed(2)}%`
function change(key: keyof DemoMetrics) {
  const previous = snapshot.value.previous[key]
  if (!previous) return '对照期无基数'
  const value = (snapshot.value.totals[key] - previous) / Math.abs(previous) * 100
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}
const metricCards = computed(() => [
  { key: 'sales' as const, label: '模拟成交额', value: money(snapshot.value.totals.sales), unit: '元', note: '成交规模' },
  { key: 'profit' as const, label: '模拟利润', value: money(snapshot.value.totals.profit), unit: '元', note: '演示成本模型' },
  { key: 'orders' as const, label: '模拟订单', value: integer(snapshot.value.totals.orders), unit: '单', note: `销量 ${integer(snapshot.value.totals.units)} 件` },
  { key: 'visitors' as const, label: '模拟访客', value: integer(snapshot.value.totals.visitors), unit: '人次', note: `转化率 ${percent(snapshot.value.totals.conversionRate)}` },
  { key: 'adCost' as const, label: '模拟广告费', value: money(snapshot.value.totals.adCost), unit: '元', note: '广告投入' },
  { key: 'roi' as const, label: '模拟投入产出比', value: snapshot.value.totals.roi.toFixed(2), unit: '倍', note: '成交额 / 广告费，非归因 ROI' },
])

const chartText = ref('#9da1ad')
const chartBorder = ref('#252830')
let themeObserver: MutationObserver | undefined
function updateChartTheme() {
  const style = getComputedStyle(document.documentElement)
  chartText.value = style.getPropertyValue('--app-text-secondary').trim() || '#9da1ad'
  chartBorder.value = style.getPropertyValue('--app-border').trim() || '#252830'
}
const chartBase = computed(() => ({
  animation: false,
  textStyle: { color: chartText.value, fontFamily: 'Inter, PingFang SC, sans-serif' },
  tooltip: { trigger: 'axis', confine: true, valueFormatter: (value: unknown) => `¥${money(Number(value))}（模拟）` },
  legend: { top: 4, textStyle: { color: chartText.value }, itemWidth: 16, itemHeight: 8 },
  grid: { top: 56, left: 12, right: 18, bottom: 14, containLabel: true },
  yAxis: { type: 'value', name: '金额 / 元', nameTextStyle: { color: chartText.value }, axisLabel: { color: chartText.value, formatter: axisMoney }, splitLine: { lineStyle: { color: chartBorder.value } } },
}))
const hourlyChart = computed<EChartsCoreOption>(() => ({
  ...chartBase.value,
  xAxis: { type: 'category', boundaryGap: false, data: snapshot.value.hourly.map(item => `${String(item.hour).padStart(2, '0')}:00`), axisLabel: { color: chartText.value, interval: 2 }, axisLine: { lineStyle: { color: chartBorder.value } } },
  series: [
    { name: '选择日期 · 模拟', type: 'line', data: snapshot.value.hourly.map(item => item.current), smooth: true, showSymbol: false, lineStyle: { width: 3 }, itemStyle: { color: '#2f6df6' }, areaStyle: { color: '#2f6df6', opacity: 0.08 } },
    { name: '前一日 · 模拟', type: 'line', data: snapshot.value.hourly.map(item => item.previous), smooth: true, showSymbol: false, lineStyle: { type: 'dashed', width: 2 }, itemStyle: { color: '#8b98b1' } },
  ],
}))
const monthlyChart = computed<EChartsCoreOption>(() => ({
  ...chartBase.value,
  xAxis: { type: 'category', data: snapshot.value.trend.map(item => item.date.slice(5)), axisLabel: { color: chartText.value }, axisLine: { lineStyle: { color: chartBorder.value } } },
  series: [
    { name: '模拟成交额', type: 'bar', barMaxWidth: 20, data: snapshot.value.trend.map(item => item.sales), itemStyle: { color: '#2f6df6', borderRadius: [3, 3, 0, 0] } },
    { name: '模拟广告费', type: 'line', data: snapshot.value.trend.map(item => item.adCost), showSymbol: false, itemStyle: { color: '#d18b24' } },
    { name: '模拟利润', type: 'line', data: snapshot.value.trend.map(item => item.profit), showSymbol: false, itemStyle: { color: '#18a68a' } },
  ],
}))
const comparisonChart = computed<EChartsCoreOption>(() => ({
  ...chartBase.value, legend: { show: false },
  grid: { top: 30, left: 12, right: 24, bottom: 12, containLabel: true },
  xAxis: { type: 'value', axisLabel: { color: chartText.value, formatter: axisMoney }, splitLine: { lineStyle: { color: chartBorder.value } } },
  yAxis: { type: 'category', inverse: true, data: rankedShops.value.map(shop => shop.name), axisLabel: { color: chartText.value }, axisLine: { show: false }, axisTick: { show: false } },
  series: [{ name: '模拟成交额', type: 'bar', barMaxWidth: 24, data: rankedShops.value.map(shop => ({ value: shop.sales, itemStyle: { color: shop.color, borderRadius: [0, 4, 4, 0] } })) }],
}))
const ruleExample = computed(() => scenario.value === 'pressure'
  ? '当前为投放压力场景：示例规则会先检查广告费与利润的变化，再考虑缩减低效投放。仅演示判断过程，不代表真实商品建议。'
  : scenario.value === 'growth'
    ? '当前为增长场景：示例规则会观察成交额增长是否同时带来利润增长，再考虑逐步增加投入。仅演示判断过程，不执行任何操作。'
    : '当前为稳健经营场景：示例规则会关注成交、转化与利润是否平稳，作为日常复盘入口。仅演示判断过程，不分析真实经营。')

async function reloadCatalog() {
  request?.abort()
  const controller = new AbortController()
  request = controller
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  catalog.value = []
  page.value = 1
  try {
    const products = await loadDemoCatalog(controller.signal)
    if (!disposed && version === requestVersion) catalog.value = products
  } catch {
    if (!disposed && version === requestVersion && !controller.signal.aborted) error.value = '完全虚构商品样本读取失败。请检查网络后重试；无需登录，未生成任何替代商品。'
  } finally {
    if (!disposed && version === requestVersion) loading.value = false
  }
}
onMounted(() => {
  updateChartTheme()
  themeObserver = new MutationObserver(updateChartTheme)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  void reloadCatalog()
})
onBeforeUnmount(() => { disposed = true; request?.abort(); themeObserver?.disconnect() })
</script>

<template>
  <div class="demo-page">
    <div class="demo-banner" role="note">
      <strong><span class="demo-dot"></span>演示模式 · 经营数据均为模拟</strong>
      <span>完全虚构商品样本 · 店铺为虚拟 · 不读取或写入真实业务</span>
    </div>
    <div class="demo-content">
      <header class="demo-heading">
        <div><p class="demo-eyebrow">五店经营演示</p><h1>从一款商品，看见五家店的经营</h1><p>使用完全虚构商品样本，无需登录。切换日期和场景，探索同一套模拟经营数据。</p></div>
        <el-button :loading="loading" @click="reloadCatalog">刷新商品样本</el-button>
      </header>

      <section class="demo-controls" aria-label="演示筛选条件">
        <div class="control-field"><label for="demo-date">演示日期（北京时间）</label><el-date-picker id="demo-date" v-model="selectedDate" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD" :clearable="false" :editable="false" /></div>
        <div class="control-field"><label for="demo-scenario">模拟经营场景</label><el-select id="demo-scenario" v-model="scenario" aria-label="模拟经营场景"><el-option v-for="item in scenarios" :key="item.id" :label="item.name" :value="item.id" /></el-select></div>
        <div class="control-context"><b>{{ scenarioInfo.name }} · {{ date }}</b><span>{{ scenarioInfo.description }}；非真实实时数据</span></div>
      </section>

      <nav class="shop-selector" aria-label="选择虚拟店铺">
        <button :class="{ selected: !shopId }" :aria-pressed="!shopId" @click="shopId = ''"><span class="shop-all-mark">5</span><span>全部虚拟店铺<small>汇总视角</small></span></button>
        <button v-for="shop in DEMO_SHOPS" :key="shop.id" :style="{ '--shop-color': shop.color }" :class="{ selected: shopId === shop.id }" :aria-pressed="shopId === shop.id" @click="shopId = shop.id"><i :style="{ background: shop.color }"></i><span>{{ shop.name }}<small>虚拟店铺</small></span></button>
      </nav>

      <div class="demo-tabs" role="tablist" aria-label="演示视图"><button v-for="tab in tabs" :id="`demo-tab-${tab.id}`" :key="tab.id" role="tab" :aria-selected="activeTab === tab.id" aria-controls="demo-tab-content" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.name }}<small>{{ tab.caption }}</small></button></div>

      <section v-if="loading" class="demo-empty" role="status"><span class="loading-ring" aria-hidden="true"></span><h2>正在读取完全虚构商品样本</h2><p>仅加载公开静态样本，经营指标将在本页模拟生成。</p></section>
      <section v-else-if="error" class="demo-empty" role="alert"><h2>暂时无法展示商品</h2><p>{{ error }}</p><el-button type="primary" @click="reloadCatalog">重新读取商品</el-button></section>
      <section v-else-if="!catalog.length" class="demo-empty"><h2>暂无可用演示商品</h2><p>虚构样本中没有有效商品名称。页面不会编造商品名称、图片或货号，请稍后重试。</p><el-button type="primary" @click="reloadCatalog">重新读取商品</el-button></section>

      <section v-else id="demo-tab-content" role="tabpanel" :aria-labelledby="`demo-tab-${activeTab}`">
        <div class="selection-summary"><div><strong>{{ selectedShopName }}</strong><span>{{ periodLabel }} · {{ scenarioInfo.name }} · 模拟</span></div><el-radio-group v-if="activeTab === 'shops' || activeTab === 'products'" v-model="comparisonPeriod" size="small" aria-label="统计周期"><el-radio-button value="today">选择日期</el-radio-button><el-radio-button value="month">本月累计</el-radio-button></el-radio-group><small>展示 {{ catalog.length }} 款完全虚构商品样本，分布于 5 个虚拟店铺</small></div>

        <div class="demo-kpis"><article v-for="metric in metricCards" :key="metric.key" class="demo-kpi" :class="{ 'primary-kpi': metric.key === 'sales' }"><span>{{ metric.label }}</span><div class="metric-number" :class="{ loss: snapshot.totals[metric.key] < 0 }">{{ metric.value }}<small>{{ metric.unit }}</small></div><div class="metric-comparison"><b>{{ change(metric.key) }}</b><span>{{ period === 'today' ? '较前日模拟' : '较上月同期模拟' }}</span></div><small class="metric-note">{{ metric.note }}</small></article></div>

        <div v-if="activeTab === 'realtime' || activeTab === 'month'" class="overview-grid">
          <article class="demo-panel trend-panel"><div class="panel-top"><div><h2>{{ activeTab === 'realtime' ? '24 小时成交趋势' : '本月每日经营走势' }}</h2><p>{{ activeTab === 'realtime' ? '选择日期与前一日的完整 24 小时模拟，不表示实时采集进度。' : '从当月 1 日至选择日期，成交、广告与利润均为模拟值。' }}</p></div><span class="simulation-tag">模拟趋势</span></div><EChart :option="activeTab === 'realtime' ? hourlyChart : monthlyChart" height="330px" /></article>
          <article class="demo-panel ranking-panel"><div class="panel-top"><div><h2>五店成交排行榜</h2><p>全部虚拟店铺 · {{ period === 'today' ? '选择日期' : '本月累计' }}</p></div></div><button v-for="(shop, index) in rankedShops" :key="shop.id" class="ranking-row" :class="{ chosen: shop.id === shopId }" :aria-label="`查看${shop.name}`" @click="shopId = shop.id"><span class="rank-position">{{ index + 1 }}</span><div class="ranking-main"><div><i :style="{ background: shop.color }"></i><b>{{ shop.name }}</b><span>¥{{ money(shop.sales) }}</span></div><div class="rank-track"><span :style="{ width: `${rankedShops[0]?.sales ? shop.sales / rankedShops[0].sales * 100 : 0}%`, background: shop.color }"></span></div></div></button><p class="rank-note">榜单固定展示五店，可点击切换当前店铺。</p></article>
        </div>

        <template v-if="activeTab === 'shops'">
          <article class="demo-panel comparison-panel"><div class="panel-top"><div><h2>五家虚拟店铺 · 同口径对比</h2><p>下方始终比较全部五店；顶部指标按当前店铺选择显示。所有金额单位为元。</p></div><span class="simulation-tag">模拟对比</span></div><EChart :option="comparisonChart" height="300px" /><div class="table-scroll"><table class="demo-table"><thead><tr><th scope="col">虚拟店铺</th><th scope="col">成交额 / 元</th><th scope="col">订单 / 单</th><th scope="col">访客 / 人次</th><th scope="col">广告费 / 元</th><th scope="col">利润 / 元</th><th scope="col">转化率</th><th scope="col">投入产出比</th></tr></thead><tbody><tr v-for="shop in rankedShops" :key="shop.id" :class="{ 'selected-row': shop.id === shopId }"><th scope="row"><button class="shop-table-button" @click="shopId = shop.id"><i :style="{ background: shop.color }"></i>{{ shop.name }}</button></th><td>{{ money(shop.sales) }}</td><td>{{ integer(shop.orders) }}</td><td>{{ integer(shop.visitors) }}</td><td>{{ money(shop.adCost) }}</td><td :class="{ loss: shop.profit < 0 }">{{ money(shop.profit) }}</td><td>{{ percent(shop.conversionRate) }}</td><td>{{ shop.roi.toFixed(2) }} 倍</td></tr></tbody></table></div></article>
        </template>

        <article v-if="activeTab !== 'shops'" class="demo-panel product-panel"><div class="panel-top"><div><h2>{{ activeTab === 'products' ? '虚构商品样本展示' : '商品经营明细' }}</h2><p>商品名称、货号均为独立虚构，图片为本地几何图形；成交、流量、投放和利润为模拟。</p></div><el-input v-model="search" clearable placeholder="搜索商品名称或货号" aria-label="搜索商品名称或货号" class="product-search" /></div><el-table :data="pageProducts" row-key="id" stripe class="demo-product-table"><el-table-column type="expand"><template #default="{ row }"><dl class="product-details"><dt>商品名称（虚构样本）</dt><dd>{{ row.name }}</dd><dt>货号（虚构样本）</dt><dd>{{ row.code || '暂无货号' }}</dd><dt>样本说明</dt><dd>完全虚构样本，不提供真实档案创建日期。</dd><dt>本行统计范围</dt><dd>{{ selectedShopName }} · {{ periodLabel }} · {{ scenarioInfo.name }}；经营数据均为模拟。</dd></dl></template></el-table-column><el-table-column label="商品 / 虚构样本" min-width="300"><template #default="{ row }"><div class="demo-product-cell"><ProductImage :src="row.imageUrl" :alt="row.name" :size="64" /><div><strong>{{ row.name }}</strong><small>货号：{{ row.code || '暂无' }}</small></div></div></template></el-table-column><el-table-column label="模拟成交额 / 元" min-width="150" align="right"><template #default="{ row }">{{ money(row.sales) }}</template></el-table-column><el-table-column label="模拟销量 / 件" min-width="120" align="right"><template #default="{ row }">{{ integer(row.units) }}</template></el-table-column><el-table-column label="模拟订单 / 单" min-width="120" align="right"><template #default="{ row }">{{ integer(row.orders) }}</template></el-table-column><el-table-column label="模拟访客 / 人次" min-width="130" align="right"><template #default="{ row }">{{ integer(row.visitors) }}</template></el-table-column><el-table-column label="模拟广告费 / 元" min-width="150" align="right"><template #default="{ row }">{{ money(row.adCost) }}</template></el-table-column><el-table-column label="模拟利润 / 元" min-width="145" align="right"><template #default="{ row }"><span :class="{ loss: row.profit < 0 }">{{ money(row.profit) }}</span></template></el-table-column><el-table-column label="模拟转化率" min-width="120" align="right"><template #default="{ row }">{{ percent(row.conversionRate) }}</template></el-table-column><template #empty>未找到匹配的商品，请调整名称或货号关键词。</template></el-table><div class="table-footer"><small>当前匹配 {{ filteredProducts.length }} 款 · 样本上限 60 款，非完整商品库</small><el-pagination v-model:current-page="page" :page-size="pageSize" :total="filteredProducts.length" :pager-count="5" layout="prev, pager, next" /></div></article>

        <aside class="rule-example"><span>规则示例 · 非 AI 分析</span><p>{{ ruleExample }}</p></aside>
        <footer class="demo-footnote">模拟口径：成交额、订单、访客、广告费和利润仅用于功能演示；转化率 = 订单 / 访客，投入产出比 = 成交额 / 广告费（非广告归因 ROI）。切换条件只更新本页，不创建计划、任务或真实经营记录。</footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.demo-page{--demo-blue:#2f6df6;--demo-teal:#18a68a;--demo-amber:#d18b24;--demo-red:#e06565;color:var(--app-text);font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;min-width:0}.demo-banner{position:sticky;top:70px;z-index:12;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:13px 24px;background:var(--app-surface);border-bottom:2px solid var(--demo-blue);box-shadow:0 4px 12px #00000008}.demo-banner strong{display:flex;align-items:center;gap:9px;font-size:14px;color:var(--app-text)}.demo-banner>span{color:var(--app-text-secondary);font-size:12px}.demo-dot{height:8px;width:8px;border-radius:50%;background:var(--demo-blue);box-shadow:0 0 0 4px color-mix(in srgb,var(--demo-blue) 12%,transparent)}.demo-content{max-width:1800px;margin:0 auto;padding:26px 24px 32px}.demo-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:24px}.demo-eyebrow{font-size:12px;font-weight:650;letter-spacing:.12em;color:var(--demo-blue);margin:0 0 8px}.demo-heading h1{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:clamp(20px,2vw,28px);font-weight:650;letter-spacing:-.03em;margin:0;line-height:1.45}.demo-heading p:last-child{font-size:13px;color:var(--app-text-secondary);line-height:1.7;margin:8px 0 0}.demo-controls{display:flex;align-items:flex-end;gap:18px;padding:18px 20px;border:1px solid var(--app-border);background:var(--app-surface);border-radius:12px}.control-field{display:grid;gap:8px;width:205px;flex:0 0 205px}.control-field label{font-size:12px;color:var(--app-text-secondary)}.control-field :deep(.el-date-editor.el-input),.control-field :deep(.el-select){width:100%}.control-context{display:grid;gap:5px;padding:4px 0 5px 18px;border-left:1px solid var(--app-border);line-height:1.6}.control-context b{font-size:13px;font-weight:600}.control-context span{font-size:12px;color:var(--app-text-secondary)}.shop-selector{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:14px 0 25px}.shop-selector button{--shop-color:var(--demo-blue);display:flex;align-items:center;gap:10px;min-width:0;min-height:70px;padding:13px 12px;text-align:left;border:1px solid var(--app-border);border-top:3px solid var(--shop-color);border-radius:8px;background:var(--app-surface);color:var(--app-text);cursor:pointer;font:inherit;font-size:13px}.shop-selector button.selected{border-color:var(--shop-color);background:color-mix(in srgb,var(--shop-color) 8%,var(--app-surface));box-shadow:inset 0 0 0 1px var(--shop-color)}.shop-selector button:hover{background:var(--app-hover)}.shop-selector button>span{min-width:0;line-height:1.5;overflow-wrap:anywhere}.shop-selector small{display:block;color:var(--app-text-secondary);font-size:11px;margin-top:4px}.shop-selector i,.ranking-main i,.shop-table-button i{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0}.shop-selector .shop-all-mark{font:600 24px "SFMono-Regular",Consolas,monospace;color:var(--demo-blue);padding:0 3px}.demo-tabs{display:flex;gap:8px;border-bottom:1px solid var(--app-border);margin-bottom:22px;overflow-x:auto}.demo-tabs button{position:relative;white-space:nowrap;display:flex;align-items:center;gap:8px;padding:14px 18px;border:0;border-bottom:3px solid transparent;background:transparent;color:var(--app-text-secondary);font:inherit;font-size:14px;cursor:pointer}.demo-tabs button.active{color:var(--demo-blue);border-bottom-color:var(--demo-blue);font-weight:650}.demo-tabs small{font-size:10px;font-weight:400;color:var(--app-text-secondary);padding:3px 5px;background:var(--app-hover);border-radius:4px}.selection-summary{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:16px}.selection-summary>div:first-child{display:grid;gap:7px}.selection-summary strong{font-size:15px}.selection-summary span,.selection-summary>small{font-size:12px;color:var(--app-text-secondary)}.demo-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.demo-kpi{padding:20px;background:var(--app-surface);border:1px solid var(--app-border);border-radius:10px;min-width:0}.demo-kpi.primary-kpi{border-top:3px solid var(--demo-blue);padding-top:18px}.demo-kpi>span{font-size:12px;color:var(--app-text-secondary)}.metric-number{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace;font-variant-numeric:tabular-nums;font-size:clamp(22px,2.2vw,32px);font-weight:600;line-height:1.35;margin:12px 0;letter-spacing:-.045em;overflow-wrap:anywhere}.metric-number small{font:400 11px Inter,"PingFang SC",sans-serif;letter-spacing:0;margin-left:7px;color:var(--app-text-secondary)}.metric-comparison{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;font-size:11px}.metric-comparison b{font-family:"SFMono-Regular",Consolas,monospace;color:var(--app-text);font-weight:500}.metric-comparison span{color:var(--app-text-secondary)}.metric-note{font-size:11px;color:var(--app-text-secondary);display:block;margin-top:10px;line-height:1.5}.overview-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(300px,1fr);gap:16px;margin-top:18px}.demo-panel{border:1px solid var(--app-border);border-radius:12px;background:var(--app-surface);padding:20px;min-width:0}.panel-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}.panel-top h2{font-size:15px;font-weight:650;line-height:1.6;margin:0}.panel-top p{font-size:12px;line-height:1.7;color:var(--app-text-secondary);margin:5px 0 0}.simulation-tag{padding:4px 7px;background:color-mix(in srgb,var(--demo-blue) 9%,transparent);color:var(--demo-blue);border:1px solid color-mix(in srgb,var(--demo-blue) 24%,transparent);font-size:10px;border-radius:4px;white-space:nowrap}.ranking-row{display:flex;align-items:center;gap:12px;width:100%;padding:14px 2px;border:0;border-top:1px solid var(--app-border);background:transparent;color:var(--app-text);cursor:pointer;text-align:left}.ranking-row.chosen{background:var(--app-hover)}.rank-position{font-family:"SFMono-Regular",Consolas,monospace;font-size:12px;width:14px;color:var(--app-text-secondary)}.ranking-main{flex:1;min-width:0}.ranking-main>div:first-child{display:flex;align-items:center;gap:7px;font-size:12px;line-height:1.6;flex-wrap:wrap}.ranking-main b{font-weight:500}.ranking-main>div:first-child>span{margin-left:auto;font-family:"SFMono-Regular",Consolas,monospace;font-size:12px}.rank-track{margin-top:10px;height:4px;border-radius:2px;background:var(--app-hover);overflow:hidden}.rank-track span{display:block;height:100%;border-radius:2px}.rank-note{font-size:11px;line-height:1.7;color:var(--app-text-secondary);margin:12px 0 0}.comparison-panel,.product-panel{margin-top:18px}.table-scroll{overflow:auto}.demo-table{border-collapse:collapse;width:100%;font-size:12px;min-width:960px;text-align:right;font-variant-numeric:tabular-nums}.demo-table th,.demo-table td{padding:15px 12px;border-bottom:1px solid var(--app-border);line-height:1.6}.demo-table thead{color:var(--app-text-secondary);background:var(--app-surface-raised)}.demo-table th{font-weight:500}.demo-table th:first-child{text-align:left;min-width:160px}.demo-table .selected-row{background:var(--app-hover)}.shop-table-button{display:flex;align-items:center;gap:8px;background:transparent;border:0;padding:0;color:var(--app-text);cursor:pointer;font:inherit;text-align:left}.product-search{max-width:260px;flex-shrink:0}.demo-product-cell{display:flex;align-items:center;gap:12px;padding:8px 0}.demo-product-cell>div{min-width:0}.demo-product-cell strong{display:block;font-size:12px;font-weight:550;white-space:normal;word-break:break-word;line-height:1.65}.demo-product-cell small{display:block;font-size:11px;color:var(--app-text-secondary);line-height:1.6;margin-top:5px;word-break:break-all}.demo-product-table{font-size:12px;font-variant-numeric:tabular-nums}.demo-product-table :deep(.cell){white-space:normal;overflow-wrap:anywhere;line-height:1.6}.demo-product-table :deep(th.el-table__cell){font-size:11px;font-weight:500}.product-details{display:grid;grid-template-columns:180px minmax(0,1fr);gap:12px;margin:0;padding:20px 30px;background:var(--app-surface-raised);font-size:12px;line-height:1.8}.product-details dt{color:var(--app-text-secondary)}.product-details dd{margin:0;white-space:normal;word-break:break-word;color:var(--app-text)}.table-footer{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:18px}.table-footer>small{color:var(--app-text-secondary);font-size:11px}.rule-example{display:flex;gap:20px;align-items:flex-start;padding:18px 20px;margin-top:18px;border-left:3px solid var(--demo-blue);background:var(--app-surface);border-radius:0 8px 8px 0}.rule-example>span{font-size:12px;font-weight:600;white-space:nowrap;line-height:1.8}.rule-example p{margin:0;font-size:12px;line-height:1.8;color:var(--app-text-secondary)}.demo-footnote{font-size:11px;line-height:1.9;color:var(--app-text-secondary);margin-top:18px}.loss{color:var(--demo-red)}.demo-empty{text-align:center;padding:68px 20px;border:1px solid var(--app-border);border-radius:12px;background:var(--app-surface)}.demo-empty h2{font-size:18px;font-weight:600}.demo-empty p{font-size:13px;color:var(--app-text-secondary);line-height:1.8;margin-bottom:22px}.loading-ring{display:inline-block;height:26px;width:26px;border:3px solid var(--app-border);border-top-color:var(--demo-blue);border-radius:50%;animation:demo-spin 1s linear infinite}button:focus-visible{outline:2px solid var(--demo-blue);outline-offset:3px}@keyframes demo-spin{to{transform:rotate(360deg)}}
@media(min-width:1600px){.demo-kpis{grid-template-columns:repeat(6,minmax(0,1fr))}.metric-number{font-size:25px}}
@media(max-width:1150px){.shop-selector{grid-template-columns:repeat(3,minmax(0,1fr))}.overview-grid{grid-template-columns:minmax(0,1fr)}.control-context{border:0;padding-left:0}.demo-controls{flex-wrap:wrap}.control-context{flex:1;min-width:190px}}
@media(max-width:860px){.demo-banner{top:70px;padding:11px 16px}.demo-content{padding:20px 16px}.demo-tabs button{padding:12px 11px}.demo-tabs small{display:none}.demo-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.metric-number{font-size:25px}}
@media(max-width:560px){.demo-banner{gap:7px}.demo-banner strong{font-size:12px}.demo-banner>span{font-size:10px;line-height:1.7}.demo-heading{align-items:flex-start;flex-direction:column;gap:12px}.demo-heading h1{font-size:21px}.demo-controls{padding:14px;gap:14px}.control-field{flex:1 1 170px;width:auto}.control-context{flex-basis:100%}.shop-selector{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.demo-tabs{gap:0}.demo-tabs button{flex:1;justify-content:center;font-size:12px;padding:12px 8px}.demo-kpi{padding:14px}.demo-kpi.primary-kpi{padding-top:12px}.metric-number{font-size:20px}.metric-number small{display:block;margin:2px 0 0}.demo-panel{padding:14px}.panel-top{flex-wrap:wrap}.product-search{max-width:100%;width:100%}.product-details{padding:16px;grid-template-columns:1fr;gap:6px}.product-details dd{margin-bottom:8px}.rule-example{display:block;padding:16px}.rule-example p{margin-top:8px}.table-footer{justify-content:center}.demo-empty{padding:38px 16px}}
@media(prefers-reduced-motion:reduce){.loading-ring{animation:none}}
</style>

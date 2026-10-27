<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import http from '@/api/http'
import type { RealtimeDashboardData, RealtimeMetric } from '@/api/types'
import EChart from '@/components/EChart.vue'
import ProductImage from '@/components/ProductImage.vue'
import { getStoredTheme } from '@/theme'

const route = useRoute()

type MetricKey = 'paid_amount' | 'gross_sales' | 'net_sales' | 'gross_profit' | 'net_profit' | 'net_profit_margin' | 'ad_cost' | 'total_custom_cost' | 'gross_profit_margin' | 'buyer_count' | 'paid_units' | 'total_success_refund_amt'

const metricLabels: Record<MetricKey, string> = {
  paid_amount: '成交金额',
  gross_sales: '毛销售额',
  net_sales: '净销售额',
  gross_profit: '毛利润',
  net_profit: '净利润',
  net_profit_margin: '净利率',
  ad_cost: '广告花费',
  total_custom_cost: '自定义成本',
  gross_profit_margin: '毛利率',
  buyer_count: '买家数',
  paid_units: '成交件数',
  total_success_refund_amt: '成功退款',
}

const metricFormats: Record<MetricKey, RealtimeMetric['format']> = {
  paid_amount: 'money',
  gross_sales: 'money',
  net_sales: 'money',
  gross_profit: 'money',
  net_profit: 'money',
  net_profit_margin: 'percent',
  ad_cost: 'money',
  total_custom_cost: 'money',
  gross_profit_margin: 'percent',
  buyer_count: 'int',
  paid_units: 'int',
  total_success_refund_amt: 'money',
}

const metricGroups = [
  {
    badge: '成交收入',
    title: '成交与收入',
    description: '把成交额和净销售放到一张卡里，先看今天是不是在正常轨道上。',
    color: '#1d4ed8',
    metrics: ['paid_amount', 'gross_sales', 'net_sales'] as MetricKey[],
  },
  {
    badge: '利润健康',
    title: '利润与回报',
    description: '看毛利、净利和净利率，确认增长有没有把利润一起带上来。',
    color: '#0f766e',
    metrics: ['gross_profit', 'net_profit', 'net_profit_margin'] as MetricKey[],
  },
  {
    badge: '投放效率',
    title: '广告与成本',
    description: '将广告花费、自定义成本和毛利率放在一起，便于判断投放是否划算。',
    color: '#b45309',
    metrics: ['ad_cost', 'total_custom_cost', 'gross_profit_margin'] as MetricKey[],
  },
  {
    badge: '流量履约',
    title: '流量与退款',
    description: '关注买家、成交件数和退款金额，及时发现流量质量和履约波动。',
    color: '#475569',
    metrics: ['buyer_count', 'paid_units', 'total_success_refund_amt'] as MetricKey[],
  },
] as const

const data = ref<RealtimeDashboardData>({
  date: '',
  compare_date: '',
  data_through: '',
  source: { name: '', status: 'live', warning: '' },
  available_shops: [],
  metrics: {},
  hourly_trend: { available: false, hours: Array.from({ length: 24 }, (_, index) => index), previous: [], current: [], warning: '' },
  trend_granularity: 'hour',
  rankings: { shop: [], item: [], platform_type: [], sku_code: [], op_manager: [] },
})
const filters = reactive({ shop: '' })
const loading = ref(false)
const activeRank = ref<'shop' | 'item' | 'platform_type' | 'sku_code' | 'op_manager'>('shop')
const rankSearch = ref('')
const themeVersion = ref(0)
const isLight = computed(() => {
  void themeVersion.value
  return getStoredTheme() === 'light'
})
const heroFacts = computed(() => [
  { label: '数据截至', value: data.value.data_through || '--:--' },
  { label: '对比基线', value: data.value.compare_date ? `昨日 ${data.value.compare_date.slice(5)}` : '昨日' },
  { label: '店铺范围', value: `${data.value.available_shops.length} 个店铺` },
])

function metricItem(key: MetricKey) {
  return data.value.metrics[key]
}
function formatMetricKey(key: MetricKey) {
  const item = metricItem(key)
  return item ? formatValue(item.current, metricFormats[key]) : '--'
}
function changeText(key: MetricKey) {
  const item = metricItem(key)
  if (!item) return '暂无数据'
  return deltaText(item)
}
function changeClass(key: MetricKey) {
  const rate = metricItem(key)?.change_rate
  if (rate == null) return ''
  return rate >= 0 ? 'positive' : 'negative'
}
function formatValue(value: number | null | undefined, format: RealtimeMetric['format'] = 'decimal') {
  if (value === null || value === undefined) return '--'
  if (format === 'money') return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (format === 'percent') return `${(Number(value) * 100).toFixed(2)}%`
  if (format === 'int') return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function deltaText(metric: RealtimeMetric) {
  if (metric.change_rate === null || metric.change_rate === undefined) return '暂无同比基线'
  const rate = Number(metric.change_rate) * 100
  return `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`
}
const trendOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  legend: {
    data: [`昨日（${data.value.compare_date.slice(5)}）全部店铺`, ...data.value.hourly_trend.current.map(item => item.store_name)],
    top: 0,
    textStyle: { color: isLight.value ? '#667085' : '#a9adb7' },
  },
  grid: { left: 18, right: 24, top: 48, bottom: 8, containLabel: true },
  xAxis: {
    type: 'category',
    data: data.value.hourly_trend.hours.map(hour => `${hour}时`),
    axisLine: { lineStyle: { color: isLight.value ? '#dfe3ea' : '#343741' } },
    axisLabel: { color: isLight.value ? '#667085' : '#8f95a3' },
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    name: '金额（元）',
    nameTextStyle: { color: isLight.value ? '#98a2b3' : '#737987' },
    axisLabel: { color: isLight.value ? '#667085' : '#8f95a3', formatter: (value: number) => value >= 10000 ? `${(value / 10000).toFixed(1)}万` : String(value) },
    splitLine: { lineStyle: { color: isLight.value ? '#edf0f4' : '#292c34' } },
  },
  series: [
    {
      name: `昨日（${data.value.compare_date.slice(5)}）全部店铺`,
      type: 'bar',
      barMaxWidth: 14,
      data: data.value.hourly_trend.previous,
      itemStyle: { color: isLight.value ? '#d9dde3' : '#4b505c', borderRadius: [2, 2, 0, 0] },
    },
    ...data.value.hourly_trend.current.map((item, index) => ({
      name: item.store_name,
      type: 'bar' as const,
      barMaxWidth: 14,
      data: item.values,
      itemStyle: { color: ['#1d4ed8', '#0f766e', '#06b6d4', '#64748b', '#2563eb', '#0ea5e9', '#14b8a6', '#3b82f6'][index % 8], borderRadius: [2, 2, 0, 0] },
    })),
  ],
}))

function rankName(row: Record<string, any>) {
  if (activeRank.value === 'shop') return row.store_name || row.store_id || '未命名店铺'
  if (activeRank.value === 'item') return row.title || row.item_id || '未命名商品'
  if (activeRank.value === 'platform_type') return ({ taobao: '淘宝', tmall: '天猫', jd: '京东', pdd: '拼多多', douyin: '抖音', kuaishou: '快手' } as Record<string, string>)[String(row.platform_type)] || String(row.platform_type || '未识别平台')
  if (activeRank.value === 'sku_code') return row.latest_sku_name || row.sku_code || '未命名产品'
  return row.op_manager_name || row.op_manager || '未分配运营'
}
const rankTabs = [
  { value: 'shop', label: '店铺' },
  { value: 'item', label: '商品' },
  { value: 'platform_type', label: '平台' },
  { value: 'sku_code', label: '产品' },
  { value: 'op_manager', label: '运营' },
] as const
const rankingRows = computed(() => {
  const keyword = rankSearch.value.trim().toLowerCase()
  const rows = data.value.rankings[activeRank.value] || []
  if (!keyword) return rows
  return rows.filter(row => Object.values(row).some(value => String(value ?? '').toLowerCase().includes(keyword)))
})
function rankingSummary({ columns, data: rows }: { columns: Array<{ property?: string }>; data: Array<Record<string, any>> }) {
  return columns.map((column, index) => {
    if (index === 0) return '汇总'
    const key = column.property
    if (!key || ['store_name', 'title', 'platform_type', 'sku_code', 'op_manager_name'].includes(key)) return ''
    const values = rows.map(row => Number(row[key])).filter(Number.isFinite)
    if (!values.length) return '--'
    const total = values.reduce((sum, value) => sum + value, 0)
    if (key.endsWith('_margin') || key === 'ad_roi') return '--'
    return key.includes('amount') || key.includes('cost') || key.includes('sales') || key.includes('profit')
      ? formatValue(total, 'money')
      : total.toLocaleString('zh-CN')
  })
}
async function load(force = false) {
  loading.value = true
  try {
    const response = await http.get<RealtimeDashboardData>('/dashboard/realtime/', {
      params: { ...(filters.shop ? { shop: filters.shop } : {}), ...(force ? { refresh: 1 } : {}) },
    })
    data.value = response.data
    if (force) ElMessage.success('实时数据已刷新')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error?.detail || error?.response?.data?.detail || '实时数据加载失败')
  } finally {
    loading.value = false
  }
}
function handleThemeChange() {
  themeVersion.value += 1
}
onMounted(() => {
  window.addEventListener('warehouse-theme-change', handleThemeChange)
  load()
})
onBeforeUnmount(() => window.removeEventListener('warehouse-theme-change', handleThemeChange))
</script>

<template>
  <div class="page realtime-home" v-loading="loading">
    <section class="panel hero-panel">
      <div class="hero-copy">
        <div class="hero-kicker"><span class="live-chip">{{ route.meta.demo ? 'DEMO' : 'LIVE' }}</span><span>经营总览</span></div>
        <h1>今天的经营状态，一屏就能看懂</h1>
        <p>把成交、利润、投放和流量统一到同一经营口径里，帮助中小企业负责人快速判断今天该看什么、先做什么。</p>
        <div class="hero-facts">
          <span v-for="fact in heroFacts" :key="fact.label"><b>{{ fact.label }}</b>{{ fact.value }}</span>
        </div>
      </div>
      <div class="hero-actions">
        <el-select v-model="filters.shop" clearable filterable placeholder="全部店铺" style="width:100%" @change="load(false)">
          <el-option label="全部店铺" value="" />
          <el-option v-for="item in data.available_shops" :key="item.store_id" :label="item.store_name" :value="item.store_name" />
        </el-select>
        <div class="hero-button-row">
          <el-button :icon="Refresh" @click="load(true)">刷新数据</el-button>
          <el-button type="primary" plain @click="$router.push('/dashboard')">查看月度总览</el-button>
        </div>
        <div class="hero-note">{{ data.source.warning || '实时口径已同步，适合管理层快速查看。' }}</div>
      </div>
    </section>

    <section class="metric-band">
      <article v-for="group in metricGroups" :key="group.title" class="panel metric-card" :style="{ '--accent': group.color }">
        <div class="metric-card-head">
          <div>
            <div class="metric-kicker">{{ group.badge }}</div>
            <h3>{{ group.title }}</h3>
            <p>{{ group.description }}</p>
          </div>
          <span class="metric-chip">{{ route.meta.demo ? '模拟' : data.source.status === 'live' ? '实时' : '受限' }}</span>
        </div>
        <div class="metric-list">
          <div v-for="key in group.metrics" :key="key" class="metric-row">
            <span>{{ metricLabels[key] }}</span>
            <b>{{ formatMetricKey(key) }}</b>
            <small :class="changeClass(key)">{{ changeText(key) }}</small>
          </div>
        </div>
      </article>
    </section>

    <section class="home-grid">
      <div class="panel trend-panel">
        <div class="panel-head">
          <div>
            <div class="section-title">按小时趋势</div>
            <div class="section-subtitle">北京时间 · 今日 vs 昨日 · Top 8 店铺单列</div>
          </div>
          <el-tag effect="plain">{{ data.data_through || '--:--' }}</el-tag>
        </div>
        <EChart v-if="data.hourly_trend.available" :option="trendOption" height="320px" />
        <el-empty v-else :description="data.hourly_trend.warning || '今日和昨日都没有成交数据'" :image-size="72" />
        <div class="trend-footnote">{{ data.hourly_trend.warning || data.source.warning || '趋势数据已就绪，适合判断今天的经营节奏。' }}</div>
      </div>

      <aside class="panel insight-panel">
        <div class="section-title">经营要点</div>
        <div class="insight-list">
          <div><span>数据源</span><b>{{ data.source.name || '实时数据源' }}</b></div>
          <div><span>对比基线</span><b>{{ data.compare_date ? `昨日 ${data.compare_date.slice(5)}` : '--' }}</b></div>
          <div><span>店铺范围</span><b>{{ data.available_shops.length }} 个店铺</b></div>
          <div><span>趋势粒度</span><b>{{ data.trend_granularity === 'hour' ? '小时' : data.trend_granularity }}</b></div>
        </div>
        <div class="insight-note">{{ data.source.warning || '数据口径统一，适合老板、运营和财务一起看。' }}</div>
        <div class="insight-status">
          <span>{{ route.meta.demo ? 'DEMO' : 'LIVE' }}</span>
          <b>{{ data.data_through || '--:--' }}</b>
        </div>
        <el-button type="primary" plain @click="$router.push('/dashboard')">查看月度经营总览</el-button>
      </aside>
    </section>

    <section class="panel ranking-panel">
      <div class="panel-head ranking-head">
        <div>
          <div class="section-title">今日排行榜</div>
          <div class="section-subtitle">数据截至 {{ data.data_through || '--:--' }}</div>
        </div>
        <el-input v-model="rankSearch" clearable placeholder="搜索名称" style="width:190px" />
      </div>
      <el-tabs v-model="activeRank" class="rank-tabs">
        <el-tab-pane v-for="tab in rankTabs" :key="tab.value" :label="tab.label" :name="tab.value" />
      </el-tabs>

      <el-table v-if="rankingRows.length" :data="rankingRows" stripe show-summary :summary-method="rankingSummary" class="metric-group-table">
        <el-table-column fixed="left" label="排名" type="index" width="68" align="center" />
        <el-table-column fixed="left" :label="rankTabs.find(tab => tab.value === activeRank)?.label || '对象'" min-width="210">
          <template #default="{ row }">
            <div class="rank-object"><ProductImage v-if="activeRank === 'item'" :src="String(row.product_image_url || row.pic_url || '')" /><div><div class="rank-name">{{ rankName(row) }}</div>
            <div v-if="activeRank === 'item' && row.item_id" class="row-sub">商品ID {{ row.item_id }}</div>
            </div></div>
          </template>
        </el-table-column>
        <el-table-column label="成交指标" align="center">
          <el-table-column prop="paid_amount" label="成交金额" width="132" align="right"><template #default="{ row }">{{ formatValue(row.paid_amount == null ? null : Number(row.paid_amount), 'money') }}</template></el-table-column>
          <el-table-column prop="paid_units" label="成交件数" width="104" align="right"><template #default="{ row }">{{ formatValue(row.paid_units == null ? null : Number(row.paid_units), 'int') }}</template></el-table-column>
          <el-table-column prop="trade_count" label="成交笔数" width="104" align="right"><template #default="{ row }">{{ formatValue(row.trade_count == null ? null : Number(row.trade_count), 'int') }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="退款指标" align="center">
          <el-table-column prop="total_refund_amt" label="总退款金额" width="132" align="right"><template #default="{ row }">{{ formatValue(row.total_refund_amt == null ? null : Number(row.total_refund_amt), 'money') }}</template></el-table-column>
          <el-table-column prop="total_success_refund_amt" label="成功退款" width="126" align="right"><template #default="{ row }">{{ formatValue(row.total_success_refund_amt == null ? null : Number(row.total_success_refund_amt), 'money') }}</template></el-table-column>
          <el-table-column prop="pre_ship_refund_amt" label="发货前退款" width="132" align="right"><template #default="{ row }">{{ formatValue(row.pre_ship_refund_amt == null ? null : Number(row.pre_ship_refund_amt), 'money') }}</template></el-table-column>
          <el-table-column prop="post_ship_refund_amt" label="发货后退款" width="132" align="right"><template #default="{ row }">{{ formatValue(row.post_ship_refund_amt == null ? null : Number(row.post_ship_refund_amt), 'money') }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="广告指标" align="center">
          <el-table-column prop="ad_cost" label="广告花费" width="126" align="right"><template #default="{ row }">{{ formatValue(row.ad_cost == null ? null : Number(row.ad_cost), 'money') }}</template></el-table-column>
          <el-table-column prop="ad_click" label="广告点击" width="104" align="right"><template #default="{ row }">{{ formatValue(row.ad_click == null ? null : Number(row.ad_click), 'int') }}</template></el-table-column>
          <el-table-column prop="ad_pv" label="广告展现" width="110" align="right"><template #default="{ row }">{{ formatValue(row.ad_pv == null ? null : Number(row.ad_pv), 'int') }}</template></el-table-column>
          <el-table-column prop="ad_roi" label="广告 ROI" width="104" align="right"><template #default="{ row }">{{ formatValue(row.ad_roi == null ? null : Number(row.ad_roi)) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="利润财务" align="center">
          <el-table-column prop="gross_sales" label="毛销售额" width="132" align="right"><template #default="{ row }">{{ formatValue(row.gross_sales == null ? null : Number(row.gross_sales), 'money') }}</template></el-table-column>
          <el-table-column prop="net_sales" label="净销售额" width="132" align="right"><template #default="{ row }">{{ formatValue(row.net_sales == null ? null : Number(row.net_sales), 'money') }}</template></el-table-column>
          <el-table-column prop="gross_profit" label="毛利润" width="126" align="right"><template #default="{ row }">{{ formatValue(row.gross_profit == null ? null : Number(row.gross_profit), 'money') }}</template></el-table-column>
          <el-table-column prop="net_profit" label="净利润" width="126" align="right"><template #default="{ row }">{{ formatValue(row.net_profit == null ? null : Number(row.net_profit), 'money') }}</template></el-table-column>
          <el-table-column prop="net_profit_margin" label="净利率" width="102" align="right"><template #default="{ row }">{{ formatValue(row.net_profit_margin == null ? null : Number(row.net_profit_margin), 'percent') }}</template></el-table-column>
        </el-table-column>
      </el-table>
      <el-empty v-else :description="activeRank === 'sku_code' ? '当前数据接口暂未开放产品编码实时维度' : activeRank === 'op_manager' ? '今日暂无运营维度数据' : '今日暂无排行榜数据'" :image-size="72" />
    </section>
  </div>
</template>

<style scoped>
.realtime-home{display:grid;gap:16px}.hero-panel{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(280px,.7fr);gap:24px;padding:26px 26px 22px;border-radius:18px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(249,251,255,.98));border:1px solid color-mix(in srgb,var(--app-border) 88%,#dbe5ff);box-shadow:0 18px 40px rgba(15,23,42,.04)}.hero-copy{display:grid;gap:12px}.hero-kicker{display:flex;align-items:center;gap:10px;color:#2445a8;font-size:12px;letter-spacing:.18em;font-weight:700;text-transform:uppercase}.live-chip{padding:3px 8px;border-radius:999px;background:color-mix(in srgb,#1d4ed8 10%,transparent);color:#1d4ed8;border:1px solid color-mix(in srgb,#1d4ed8 20%,transparent)}.hero-copy h1{margin:0;font-size:36px;line-height:1.12;letter-spacing:-.03em;color:var(--app-text)}.hero-copy p{margin:0;max-width:760px;font-size:16px;line-height:1.8;color:var(--app-text-secondary)}.hero-facts{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px}.hero-facts span{display:inline-flex;align-items:center;gap:8px;padding:10px 12px;border-radius:999px;background:color-mix(in srgb,var(--app-hover) 70%,transparent);border:1px solid var(--app-border);color:var(--app-text-secondary);font-size:12px;white-space:nowrap}.hero-facts b{color:var(--app-text);font-weight:600}.hero-actions{display:grid;align-content:start;gap:12px;padding:2px 0}.hero-button-row{display:flex;gap:10px;flex-wrap:wrap}.hero-note{padding:14px 15px;border-radius:14px;background:color-mix(in srgb,#1d4ed8 5%,var(--app-surface));border:1px solid color-mix(in srgb,#1d4ed8 14%,var(--app-border));color:var(--app-text-secondary);font-size:13px;line-height:1.6}.metric-band{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric-card{padding:18px 18px 16px;border-radius:18px;position:relative;overflow:hidden;box-shadow:0 12px 28px rgba(15,23,42,.04)}.metric-card:before{content:"";position:absolute;left:0;top:0;right:0;height:3px;background:var(--accent)}.metric-card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}.metric-kicker{font-size:11px;letter-spacing:.14em;color:var(--accent);font-weight:700;text-transform:uppercase}.metric-card h3{margin:4px 0 6px;font-size:18px;line-height:1.2}.metric-card p{margin:0;color:var(--app-text-muted);font-size:13px;line-height:1.65}.metric-chip{display:inline-flex;align-items:center;padding:5px 10px;border-radius:999px;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 18%,transparent);font-size:12px;white-space:nowrap}.metric-list{display:grid;gap:10px}.metric-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;align-items:end;padding:12px 0;border-top:1px solid color-mix(in srgb,var(--app-border) 70%,transparent)}.metric-row:first-child{border-top:0;padding-top:0}.metric-row span{font-size:13px;color:var(--app-text-secondary)}.metric-row b{font-size:22px;line-height:1.15;color:var(--app-text)}.metric-row small{grid-column:2;text-align:right;font-size:12px;font-weight:600}.metric-row small.positive{color:#0f8a67}.metric-row small.negative{color:#d14343}.home-grid{display:grid;grid-template-columns:minmax(0,1.28fr) minmax(280px,.72fr);gap:14px;align-items:start}.trend-panel,.ranking-panel,.insight-panel{border-radius:18px;box-shadow:0 12px 28px rgba(15,23,42,.04)}.trend-panel{padding:18px 18px 14px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}.section-title{font-size:18px;font-weight:700;color:var(--app-text)}.section-subtitle{margin-top:4px;font-size:13px;color:var(--app-text-muted);line-height:1.6}.trend-footnote{margin-top:8px;color:var(--app-text-muted);font-size:12px;line-height:1.6}.insight-panel{padding:18px}.insight-list{display:grid;gap:10px;margin:14px 0 16px}.insight-list div{display:grid;gap:4px;padding:12px 14px;border-radius:14px;background:color-mix(in srgb,var(--app-hover) 58%,transparent);border:1px solid var(--app-border)}.insight-list span{font-size:12px;color:var(--app-text-muted);letter-spacing:.02em}.insight-list b{font-size:15px;color:var(--app-text)}.insight-note{padding:14px 15px;border-radius:14px;background:color-mix(in srgb,#0f766e 6%,var(--app-surface));border:1px solid color-mix(in srgb,#0f766e 16%,var(--app-border));color:var(--app-text-secondary);font-size:13px;line-height:1.7}.insight-status{display:flex;align-items:center;justify-content:space-between;margin:16px 0 14px;padding:12px 14px;border-radius:14px;background:linear-gradient(135deg,color-mix(in srgb,#1d4ed8 10%,var(--app-surface)),color-mix(in srgb,#0f766e 8%,var(--app-surface)));border:1px solid color-mix(in srgb,#1d4ed8 15%,var(--app-border));color:var(--app-text)}.insight-status span{font-size:11px;letter-spacing:.16em;color:#1d4ed8;font-weight:700}.insight-status b{font-size:14px}.ranking-panel{padding:18px;border-radius:18px}.ranking-head{margin-bottom:0}.rank-tabs{margin-top:-4px}.rank-name{font-weight:600;color:var(--app-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row-sub{font-size:11px;color:var(--app-text-muted);margin-top:6px}.metric-group-table{width:100%}.metric-group-table :deep(.el-table__header th){background:color-mix(in srgb,var(--app-surface) 88%,var(--app-bg));color:var(--app-text-secondary)}.metric-group-table :deep(.el-table__footer-wrapper td){font-weight:700;background:color-mix(in srgb,#1d4ed8 4%,var(--app-surface))}
@media(max-width:1280px){.metric-band{grid-template-columns:repeat(2,minmax(0,1fr))}.home-grid,.hero-panel{grid-template-columns:1fr}}
@media(max-width:900px){.hero-copy h1{font-size:30px}.metric-band{grid-template-columns:1fr}.panel-head,.ranking-head{flex-direction:column;align-items:flex-start}.ranking-head :deep(.el-input){width:100%}.trend-panel,.ranking-panel,.insight-panel{padding:16px}.hero-panel{padding:20px}}
@media(max-width:640px){.realtime-home{gap:12px}.hero-copy h1{font-size:26px}.hero-copy p{font-size:14px;line-height:1.7}.hero-facts{gap:8px}.hero-facts span{width:100%;justify-content:space-between;border-radius:14px}.hero-button-row{display:grid;grid-template-columns:1fr;gap:8px;width:100%}.hero-button-row :deep(.el-button){width:100%}.metric-row{grid-template-columns:1fr}.metric-row small{text-align:left;grid-column:1}.panel-head{gap:8px}.trend-panel :deep(.el-empty),.ranking-panel :deep(.el-empty){padding-inline:0}}
.rank-object{display:flex;align-items:center;gap:10px;min-width:0}.rank-object>div:last-child{min-width:0}
</style>

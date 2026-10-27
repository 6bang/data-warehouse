<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import type { EChartsOption } from 'echarts'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { DashboardData, Paginated, ProductData, ShopData } from '@/api/types'
import EChart from '@/components/EChart.vue'
import ProductImage from '@/components/ProductImage.vue'
import { getStoredTheme } from '@/theme'

const empty: DashboardData = { month: null, previous_month: null, available_months: [], metrics: {}, monthly_trend: [], daily_trend: [], abnormal: [], abnormal_count: 0, task_summary: {} }
const loading = ref(false)
const data = ref<DashboardData>(empty)
const products = ref<ProductData[]>([])
const shops = ref<ShopData[]>([])
const rankingDimension = ref<'shop' | 'product'>('shop')
const filters = reactive({ month: '', shop: '' })
const metricDomains = [
  { title: '成交指标', tone: 'purple', items: [['sales', '成交金额', 'currency'], ['sales_volume', '成交件数', 'integer'], ['orders', '订单数', 'integer']] },
  { title: '流量转化', tone: 'green', items: [['visitors', '访客数', 'integer'], ['conversion_rate', '转化率', 'percent']] },
  { title: '广告指标', tone: 'orange', items: [['ad_cost', '广告花费', 'currency'], ['roi', '广告 ROI', 'decimal']] },
  { title: '利润财务', tone: 'blue', items: [['profit', '毛利润', 'currency']] },
] as const
const themeVersion = ref(0)
const isLight = computed(() => { void themeVersion.value; return getStoredTheme() === 'light' })
const axis = computed(() => ({
  axisLine: { lineStyle: { color: isLight.value ? '#d7dce5' : '#3a3d46' } },
  axisLabel: { color: isLight.value ? '#687284' : '#858a96' },
  splitLine: { lineStyle: { color: isLight.value ? '#e8ebf0' : '#282b32' } },
}))

function formatValue(value: number | null | undefined, type: string) {
  if (value === null || value === undefined) return '暂无数据'
  if (type === 'currency') return `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
  if (type === 'percent') return `${(Number(value) * 100).toFixed(2)}%`
  if (type === 'decimal') return Number(value).toFixed(2)
  return Number(value).toLocaleString('zh-CN')
}
function formatDelta(value: number | null | undefined) { return value == null ? '上月暂无基线' : `较上月 ${value >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(1)}%` }

const monthlyOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent', tooltip: { trigger: 'axis' }, legend: { data: ['销售额', '广告花费', '毛利润'], textStyle: { color: isLight.value ? '#566070' : '#a9adb7' }, left: 0 },
  grid: { left: 20, right: 20, top: 48, bottom: 12, containLabel: true },
  xAxis: { type: 'category', data: data.value.monthly_trend.map(item => item.month.replace('-', '')), ...axis.value },
  yAxis: {
    type: 'value', ...axis.value,
    name: '单位：万元',
    nameTextStyle: { color: isLight.value ? '#8992a2' : '#747987', padding: [0, 0, 6, 0] },
    axisLabel: {
      color: isLight.value ? '#687284' : '#858a96',
      formatter: (value: number) => `¥${Number((value / 10000).toFixed(1))}万`,
    },
  },
  series: [
    { name: '销售额', type: 'line', smooth: true, symbolSize: 7, data: data.value.monthly_trend.map(item => item.sales), lineStyle: { width: 3, color: '#7467ff' }, itemStyle: { color: '#7467ff' }, areaStyle: { color: 'rgba(116,103,255,.16)' } },
    { name: '广告花费', type: 'line', smooth: true, data: data.value.monthly_trend.map(item => item.ad_cost), lineStyle: { width: 2, color: '#a94fe0' }, itemStyle: { color: '#a94fe0' } },
    { name: '毛利润', type: 'line', smooth: true, data: data.value.monthly_trend.map(item => item.profit), lineStyle: { width: 2, color: '#26a9e8' }, itemStyle: { color: '#26a9e8' } },
  ],
}))

const dailyOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent', tooltip: { trigger: 'axis' }, legend: { data: ['销售额', '访客'], textStyle: { color: isLight.value ? '#566070' : '#a9adb7' }, left: 0 },
  grid: { left: 15, right: 18, top: 45, bottom: 12, containLabel: true },
  xAxis: { type: 'category', data: data.value.daily_trend.map(item => item.date.slice(8)), ...axis.value },
  yAxis: [{ type: 'value', ...axis.value }, { type: 'value', ...axis.value, splitLine: { show: false } }],
  series: [
    { name: '销售额', type: 'bar', data: data.value.daily_trend.map(item => item.sales), itemStyle: { color: '#7467ff', borderRadius: [3, 3, 0, 0] } },
    { name: '访客', type: 'line', yAxisIndex: 1, smooth: true, data: data.value.daily_trend.map(item => item.visitors), lineStyle: { color: '#44c894' }, itemStyle: { color: '#44c894' } },
  ],
}))

const productOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent', tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 12, right: 20, top: 10, bottom: 10, containLabel: true },
  xAxis: { type: 'value', ...axis.value },
  yAxis: { type: 'category', inverse: true, data: rankingDimension.value === 'shop' ? shops.value.slice(0, 8).map(item => item.shop) : products.value.slice(0, 8).map(item => item.product_name.length > 12 ? `${item.product_name.slice(0, 12)}…` : item.product_name), ...axis.value, axisLabel: { color: isLight.value ? '#566070' : '#a8acb6', width: 120, overflow: 'truncate' } },
  series: [{ name: '月销售额', type: 'bar', data: rankingDimension.value === 'shop' ? shops.value.slice(0, 8).map(item => Number(item.sales)) : products.value.slice(0, 8).map(item => Number(item.sales)), itemStyle: { color: '#7467ff', borderRadius: [0, 4, 4, 0] } }],
}))

const aiBrief = computed(() => data.value.abnormal_count
  ? `${filters.month || data.value.month} 共检测到 ${data.value.abnormal_count} 项异常。优先处理“${data.value.abnormal[0]?.description || '高等级异常'}”，并按月复盘执行效果。`
  : '本月未检测到达到阈值的异常，建议继续观察月内趋势并补齐利润与库存数据。')

async function load() {
  loading.value = true
  try {
    const params = { ...(filters.month ? { month: filters.month } : {}), ...(filters.shop ? { shop: filters.shop } : {}) }
    const [dashboard, ranking, shopRanking] = await Promise.all([
      http.get<DashboardData>('/dashboard/', { params }),
      http.get<Paginated<ProductData>>('/products/monthly/', { params: { ...params, page_size: 8, ordering: '-sales' } }),
      http.get<{ count: number; results: ShopData[] }>('/shops/monthly/', { params: { month: filters.month, ordering: '-sales' } }),
    ])
    data.value = dashboard.data
    products.value = ranking.data.results
    shops.value = shopRanking.data.results
    if (!filters.month && dashboard.data.month) filters.month = dashboard.data.month
  } finally { loading.value = false }
}
async function createTask(abnormalId: number) { await http.post('/tasks/from_abnormal/', { abnormal_record_id: abnormalId }); ElMessage.success('已创建运营任务') }
function levelType(level: string) { return level === 'critical' ? 'danger' : level === 'warning' ? 'warning' : 'info' }
function handleThemeChange() { themeVersion.value += 1 }
onMounted(() => { window.addEventListener('warehouse-theme-change', handleThemeChange); load() })
onBeforeUnmount(() => window.removeEventListener('warehouse-theme-change', handleThemeChange))
</script>

<template><div class="page" v-loading="loading">
  <div class="page-toolbar"><div><div class="month-title">{{ filters.month || data.month || '月度经营数据' }} <el-tag v-if="data.is_partial" size="small" effect="plain">月累计</el-tag></div><div class="month-subtitle">月度经营总览 · 对比 {{ data.comparison_label || data.previous_month || '上月' }}<span v-if="data.data_through"> · 数据截至 {{ data.data_through }}</span></div></div><div class="toolbar-group"><el-select v-model="filters.month" placeholder="选择月份" style="width:140px" @change="load"><el-option v-for="month in data.available_months" :key="month" :label="month" :value="month" /></el-select><el-select v-model="filters.shop" clearable filterable placeholder="全部店铺" style="width:210px" @change="load"><el-option label="全部店铺" value="" /><el-option v-for="shop in shops" :key="shop.shop" :label="shop.shop" :value="shop.shop" /></el-select><el-button type="primary" @click="load">刷新</el-button></div></div>
  <div class="metric-domain-grid"><section v-for="domain in metricDomains" :key="domain.title" class="panel metric-domain" :class="domain.tone"><div class="metric-domain-title">{{ domain.title }}</div><div class="domain-metrics"><div v-for="([key,label,type]) in domain.items" :key="key" class="domain-metric"><div class="kpi-label">{{ label }}</div><div class="kpi-value" :class="{'empty-value':data.metrics[key]?.value==null}">{{ formatValue(data.metrics[key]?.value,type) }}</div><div class="kpi-delta" :class="{down:Number(data.metrics[key]?.change_rate)<0}">{{ formatDelta(data.metrics[key]?.change_rate) }}</div></div></div></section></div>
  <div class="panel" style="margin-top:14px"><div class="panel-title">每月经营业绩分析</div><EChart :option="monthlyOption" height="330px" /></div>
  <div class="content-grid"><div class="panel"><div class="panel-title">{{ filters.month }} 月内每日表现</div><EChart :option="dailyOption" height="285px" /></div><div class="panel ai-block"><div class="panel-title">经营分析 Agent</div><div class="ai-summary">{{ aiBrief }}</div><el-divider /><div class="kpi-label">本月待处理任务</div><div class="kpi-value">{{ data.task_summary.pending || 0 }}</div><el-button text type="primary" @click="$router.push('/ai-analysis')">进入月度分析 →</el-button></div></div>
  <div class="panel" style="margin-top:14px"><div class="panel-heading"><div><div class="panel-title" style="margin-bottom:4px">经营对象排行榜</div><div class="chart-legend-note">用同一经营口径穿透不同对象</div></div><el-radio-group v-model="rankingDimension" size="small"><el-radio-button value="shop">店铺</el-radio-button><el-radio-button value="product">商品</el-radio-button></el-radio-group></div><EChart :option="productOption" height="340px" /></div>
  <div class="panel" style="margin-top:14px"><div class="panel-title">本月异常 <span class="chart-legend-note">共 {{ data.abnormal_count || 0 }} 项</span></div><el-empty v-if="!data.abnormal.length" description="本月暂无异常" :image-size="70" /><div v-for="item in data.abnormal" :key="item.id" class="anomaly-item"><el-tag :type="levelType(item.level)" effect="dark">{{ item.level==='critical'?'严重':item.level==='warning'?'警告':'提示' }}</el-tag><ProductImage v-if="item.product_id || item.product_name" :src="item.product_image_url" /><div><div>{{ item.description }}</div><div class="chart-legend-note" style="margin-top:5px">{{ item.date }} · {{ item.suggestion }}</div></div><el-button :icon="Plus" size="small" @click="createTask(item.id)">创建任务</el-button></div></div>
</div></template>

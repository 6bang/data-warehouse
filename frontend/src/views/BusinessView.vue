<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Connection, Refresh } from '@element-plus/icons-vue'
import http from '@/api/http'
import type { BusinessDimensions, BusinessMetrics, BusinessMetricRow } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const dimensions = ref<BusinessDimensions | null>(null)
const data = ref<BusinessMetrics | null>(null)
const filters = reactive({
  organization: '', month: '', platform: '', shop: '', category_path: '', operator_name: '',
  group_by: 'platform' as BusinessMetrics['group_by'], ordering: '-sales', search: '', limit: 300,
})
const groups = [
  { value: 'platform', label: '平台' }, { value: 'shop', label: '店铺' }, { value: 'category', label: '品类' },
  { value: 'product', label: '商品' }, { value: 'operator', label: '人员' },
] as const
const summary = computed(() => data.value?.summary)
const hasMcpMetrics = computed(() => dimensions.value?.coverage.available.includes('visitors'))

function params() { return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '')) }
function money(value?: number | null) { return value == null ? '暂无' : `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` }
function integer(value?: number | null) { return Number(value || 0).toLocaleString('zh-CN') }
function ratio(value?: number | null) { return value == null ? '暂无' : `${(Number(value) * 100).toFixed(1)}%` }
function decimal(value?: number | null) { return value == null ? '暂无' : Number(value).toFixed(2) }
function categoryTail(path?: string) { return path?.split('->').at(-1) || '未分类' }
function rowTitle(row: BusinessMetricRow) {
  if (filters.group_by === 'platform') return row.platform || '未识别平台'
  if (filters.group_by === 'shop') return row.shop || '未识别店铺'
  if (filters.group_by === 'category') return categoryTail(row.category_path)
  if (filters.group_by === 'operator') return row.operator_name || '未分配运营'
  return row.product_name || row.product_id || '未命名商品'
}
function rowSubtitle(row: BusinessMetricRow) {
  if (filters.group_by === 'product') return `${row.product_id} · ${row.shop} · ${categoryTail(row.category_path)}`
  if (filters.group_by === 'shop') return row.platform || ''
  if (filters.group_by === 'category') return row.category_path || ''
  if (filters.group_by === 'operator') return row.operator_name === '未分配运营' ? '尚未建立人员责任关系' : '责任范围汇总'
  return `${integer(row.products)} 个商品`
}
async function loadDimensions(keepMonth = true) {
  const { data: result } = await http.get<BusinessDimensions>('/business/dimensions/', {
    params: { organization: filters.organization, month: keepMonth ? filters.month : '' },
  })
  dimensions.value = result
  filters.organization = result.selected.organization
  filters.month = result.selected.month
}
async function load() {
  loading.value = true
  try { const response = await http.get<BusinessMetrics>('/business/monthly/', { params: params() }); data.value = response.data }
  finally { loading.value = false }
}
async function changeOrganization() {
  filters.month = ''; filters.platform = ''; filters.shop = ''; filters.category_path = ''; filters.operator_name = ''
  await loadDimensions(false); await load()
}
async function changeMonth() {
  filters.platform = ''; filters.shop = ''; filters.category_path = ''; filters.operator_name = ''
  await loadDimensions(true); await load()
}
async function resetFilters() {
  filters.platform = ''; filters.shop = ''; filters.category_path = ''; filters.operator_name = ''; filters.search = ''
  await load()
}
async function init() { await loadDimensions(false); await load() }
onMounted(init)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-toolbar business-toolbar">
      <div><div class="month-title">多平台经营数据中心</div><div class="month-subtitle">组织 → 平台 → 店铺 → 品类 → 商品 → 负责人，一套月度经营口径</div></div>
      <div class="source-badge"><el-icon><Connection /></el-icon><span>{{ dimensions?.coverage.source || '等待数据源' }}</span></div>
    </div>

    <div class="panel filter-panel">
      <el-select v-model="filters.organization" placeholder="选择组织" style="width:220px" @change="changeOrganization"><el-option v-for="item in dimensions?.organizations" :key="item" :label="item" :value="item" /></el-select>
      <el-select v-model="filters.month" placeholder="选择月份" style="width:130px" @change="changeMonth"><el-option v-for="item in dimensions?.months" :key="item" :label="item" :value="item" /></el-select>
      <el-select v-model="filters.platform" clearable placeholder="全部平台" style="width:140px"><el-option v-for="item in dimensions?.platforms" :key="item" :label="item" :value="item" /></el-select>
      <el-select v-model="filters.shop" clearable placeholder="全部店铺" style="width:170px"><el-option v-for="item in dimensions?.shops" :key="item" :label="item" :value="item" /></el-select>
      <el-select v-model="filters.category_path" clearable filterable placeholder="全部品类" style="width:210px"><el-option v-for="item in dimensions?.categories" :key="item" :label="categoryTail(item)" :value="item" /></el-select>
      <el-select v-model="filters.operator_name" clearable placeholder="全部人员" style="width:160px"><el-option v-for="item in dimensions?.operators" :key="item" :label="item" :value="item" /></el-select>
      <el-button type="primary" @click="load">查询</el-button><el-button :icon="Refresh" @click="resetFilters">重置</el-button>
    </div>

    <div class="business-summary">
      <div><small>成交金额</small><strong>{{ money(summary?.sales) }}</strong><span>订单 {{ integer(summary?.orders) }}</span></div>
      <div><small>净销售额</small><strong>{{ money(summary?.net_sales) }}</strong><span>退款率 {{ ratio(summary?.refund_rate) }}</span></div>
      <div><small>广告花费</small><strong>{{ money(summary?.ad_cost) }}</strong><span>广告 ROI {{ decimal(summary?.roi) }}</span></div>
      <div><small>毛利润</small><strong>{{ money(summary?.gross_profit) }}</strong><span>毛利率 {{ ratio(summary?.gross_margin) }}</span></div>
      <div><small>净利润</small><strong>{{ money(summary?.net_profit) }}</strong><span>净利率 {{ ratio(summary?.net_margin) }}</span></div>
      <div><small>商品覆盖</small><strong>{{ integer(summary?.products) }}</strong><span>{{ dimensions?.latest_sync?.rows || 0 }} 行已同步</span></div>
    </div>

    <div class="panel business-table-panel">
      <div class="table-head">
        <div class="dimension-switch"><button v-for="item in groups" :key="item.value" :class="{active:filters.group_by===item.value}" @click="filters.group_by=item.value;load()">{{ item.label }}</button></div>
        <div class="table-tools"><el-input v-model="filters.search" clearable placeholder="搜索商品 / 品类 / 店铺" style="width:220px" @keyup.enter="load" /><el-select v-model="filters.ordering" style="width:145px" @change="load"><el-option label="成交金额降序" value="-sales" /><el-option label="订单数降序" value="-orders" /><el-option label="毛利润降序" value="-gross_profit" /><el-option label="广告花费降序" value="-ad_cost" /></el-select></div>
      </div>
      <el-table :data="data?.results || []" stripe>
        <el-table-column type="index" label="#" width="54" />
        <el-table-column :label="groups.find(item=>item.value===filters.group_by)?.label" min-width="260" fixed="left"><template #default="{ row }"><div class="object-cell"><ProductImage v-if="filters.group_by==='product'" :src="row.product_image_url" /><div><strong>{{ rowTitle(row) }}</strong><small>{{ rowSubtitle(row) }}</small></div></div></template></el-table-column>
        <el-table-column prop="products" label="商品数" width="80" />
        <el-table-column label="成交指标"><el-table-column label="成交金额" min-width="120"><template #default="{row}">{{ money(row.sales) }}</template></el-table-column><el-table-column prop="orders" label="订单" width="74" /></el-table-column>
        <el-table-column v-if="hasMcpMetrics" label="流量库存"><el-table-column prop="sales_volume" label="销量" width="74" /><el-table-column prop="visitors" label="访客" width="82" /><el-table-column prop="stock" label="库存" width="82" /></el-table-column>
        <el-table-column label="退款售后"><el-table-column label="退款金额" min-width="112"><template #default="{row}">{{ money(row.refund_amount) }}</template></el-table-column><el-table-column label="退款率" width="82"><template #default="{row}">{{ ratio(row.refund_rate) }}</template></el-table-column></el-table-column>
        <el-table-column label="广告指标"><el-table-column label="广告花费" min-width="108"><template #default="{row}">{{ money(row.ad_cost) }}</template></el-table-column><el-table-column label="ROI" width="72"><template #default="{row}">{{ decimal(row.roi) }}</template></el-table-column></el-table-column>
        <el-table-column label="利润财务"><el-table-column label="毛利润" min-width="108"><template #default="{row}">{{ money(row.gross_profit) }}</template></el-table-column><el-table-column label="毛利率" width="86"><template #default="{row}">{{ ratio(row.gross_margin) }}</template></el-table-column><el-table-column label="净利润" min-width="108"><template #default="{row}">{{ money(row.net_profit) }}</template></el-table-column></el-table-column>
      </el-table>
      <el-empty v-if="!data?.results.length && !loading" description="当前筛选范围暂无月度数据" />
    </div>

    <div class="quality-note"><div><b>数据完整性说明</b><span v-if="hasMcpMetrics">实时数据源已同步销量、访客、转化率与库存；点击率需等待数据接口提供后接入。</span><span v-else>当前数据源未包含销量、访客、点击率、转化率和库存；这些指标显示“暂无”，不会按 0 参与判断。</span></div><div><b>智能体查询已开放</b><span>内置经营 MCP 与已授权的经营数据查询工具可共同使用。</span></div></div>
  </div>
</template>

<style scoped>
.business-toolbar{align-items:center}.source-badge{display:flex;align-items:center;gap:8px;color:#9ea3af;border:1px solid #2e313a;background:#191b21;padding:9px 12px;border-radius:8px;font-size:12px}.filter-panel{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:14px;margin-bottom:14px}.business-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:14px}.business-summary>div{background:linear-gradient(145deg,#1b1d24,#17191e);border:1px solid #2b2e36;border-radius:10px;padding:15px;display:grid;gap:8px}.business-summary small{color:#898e9b;font-size:11px}.business-summary strong{font-size:20px;white-space:nowrap}.business-summary span{font-size:11px;color:#777c88}.business-table-panel{padding:0;overflow:hidden}.table-head{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:14px 16px;border-bottom:1px solid #292c34}.dimension-switch{display:flex;background:#111318;border:1px solid #292c34;border-radius:8px;padding:3px}.dimension-switch button{border:0;background:transparent;color:#8c919e;padding:7px 15px;border-radius:6px;cursor:pointer}.dimension-switch button.active{background:#6e5bf6;color:white}.table-tools{display:flex;gap:10px}.object-cell{display:flex;align-items:center;gap:10px}.object-cell img{width:40px;height:40px;object-fit:cover;border-radius:6px;background:#272a31}.object-cell>div{display:grid;gap:5px;min-width:0}.object-cell strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.object-cell small{color:#777c88;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.quality-note{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}.quality-note>div{border:1px solid #2c2f38;background:#17191f;border-radius:9px;padding:13px 15px;display:grid;gap:5px}.quality-note b{font-size:12px}.quality-note span{font-size:11px;color:#858a97;line-height:1.6}.quality-note code{color:#a9a0ff}@media(max-width:1280px){.business-summary{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.business-summary{grid-template-columns:1fr 1fr}.quality-note{grid-template-columns:1fr}.table-head{align-items:flex-start;flex-direction:column}.dimension-switch{overflow-x:auto;max-width:100%}}
</style>

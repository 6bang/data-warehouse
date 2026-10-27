<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { DashboardData, Paginated, ProductData } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const rows = ref<ProductData[]>([])
const total = ref(0)
const months = ref<string[]>([])
const filters = reactive({ month: '', shop: '', search: '', ordering: '-sales', page: 1, page_size: 20 })
const averageScore = computed(() => rows.value.length ? Math.round(rows.value.reduce((sum, row) => sum + row.health_score, 0) / rows.value.length) : 0)

function money(value: string | null) { return value === null ? '暂无' : `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` }
function percent(value: string) { return `${(Number(value) * 100).toFixed(2)}%` }
function decimal(value: string) { return Number(value).toFixed(2) }
function scoreClass(score: number) { return score >= 75 ? 'good' : score >= 60 ? 'warning' : 'danger' }
async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
    const { data } = await http.get<Paginated<ProductData>>('/products/monthly/', { params })
    rows.value = data.results; total.value = data.count
  } finally { loading.value = false }
}
function search() { filters.page = 1; load() }
async function init() { const { data } = await http.get<DashboardData>('/dashboard/'); months.value = data.available_months; filters.month = data.month || ''; await load() }
onMounted(init)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-toolbar">
      <div><div class="month-title">商品月度经营分析</div><div class="month-subtitle">从成交到利润的完整商品经营视图</div></div>
      <div class="toolbar-group">
        <el-select v-model="filters.month" placeholder="选择月份" style="width:140px" @change="search"><el-option v-for="month in months" :key="month" :label="month" :value="month" /></el-select>
        <el-input v-model="filters.shop" clearable placeholder="全部店铺" style="width:150px" />
        <el-input v-model="filters.search" clearable placeholder="商品 ID / 名称" style="width:210px" @keyup.enter="search" />
        <el-select v-model="filters.ordering" style="width:150px" @change="search"><el-option label="销售额降序" value="-sales" /><el-option label="销量降序" value="-sales_volume" /><el-option label="访客降序" value="-visitors" /><el-option label="ROI 降序" value="-roi" /><el-option label="健康分降序" value="-health_score" /></el-select>
        <el-button type="primary" @click="search">查询</el-button>
      </div>
    </div>
    <div class="dimension-tabs"><span @click="$router.push('/shops')">店铺</span><span class="active">商品</span><span class="disabled">品类 · 待接入</span><span class="disabled">SKU · 待接入</span><el-tag effect="dark" style="margin-left:auto">本页平均健康分 {{ averageScore }}</el-tag></div>
    <div class="panel grouped-table">
      <el-table :data="rows" stripe>
        <el-table-column label="#" width="56"><template #default="scope"><span class="rank" :class="{ top: scope.$index < 3 }">{{ (filters.page - 1) * filters.page_size + scope.$index + 1 }}</span></template></el-table-column>
        <el-table-column label="商品信息" min-width="280" fixed="left"><template #default="{ row }"><div class="product-cell"><ProductImage :src="row.product_image_url" /><div><strong>{{ row.product_name }}</strong><div class="row-sub">{{ row.product_id }} · {{ row.shop }}</div></div></div></template></el-table-column>
        <el-table-column label="成交指标">
          <el-table-column label="成交金额" min-width="118"><template #default="{row}">{{ money(row.sales) }}</template></el-table-column>
          <el-table-column prop="sales_volume" label="销量" width="74" />
          <el-table-column prop="orders" label="订单" width="74" />
        </el-table-column>
        <el-table-column label="流量转化">
          <el-table-column prop="visitors" label="访客" width="82" />
          <el-table-column label="点击率" width="88"><template #default="{row}">{{ percent(row.click_rate) }}</template></el-table-column>
          <el-table-column label="转化率" width="88"><template #default="{row}">{{ percent(row.conversion_rate) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="广告指标">
          <el-table-column label="广告费" min-width="105"><template #default="{row}">{{ money(row.ad_cost) }}</template></el-table-column>
          <el-table-column label="ROI" width="72"><template #default="{row}">{{ decimal(row.roi) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="利润库存">
          <el-table-column label="利润" min-width="105"><template #default="{row}"><span :class="{ 'empty-value': row.profit === null }">{{ money(row.profit) }}</span></template></el-table-column>
          <el-table-column label="库存" width="78"><template #default="{row}"><span :class="{ 'empty-value': row.stock === null }">{{ row.stock ?? '暂无' }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="健康度" fixed="right"><el-table-column label="评分" width="88"><template #default="{row}"><el-popover trigger="hover" width="260"><template #reference><span class="health-score" :class="scoreClass(row.health_score)">{{ row.health_score }}</span></template><div v-for="(value,key) in row.health_components" :key="key" style="margin:7px 0"><span>{{ {sales_growth:'销售增长',traffic_growth:'流量增长',conversion_stability:'转化稳定',profit_health:'利润健康'}[key] || key }}</span><el-progress :percentage="value" :stroke-width="7" /></div></el-popover></template></el-table-column></el-table-column>
      </el-table>
    </div>
    <div style="display:flex;justify-content:flex-end;margin-top:14px"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" layout="total, prev, pager, next" :total="total" @current-change="load" /></div>
  </div>
</template>

<style scoped>
.product-cell{display:flex;align-items:center;gap:10px;min-width:0}.product-cell>div:last-child{min-width:0}.product-cell strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>

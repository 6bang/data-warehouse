<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { DashboardData, ShopData } from '@/api/types'

const loading = ref(false)
const rows = ref<ShopData[]>([])
const months = ref<string[]>([])
const filters = reactive({ month: '', search: '', ordering: '-sales' })

function money(value: number | null) { return value == null ? '暂无' : `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` }
function integer(value: number) { return Number(value).toLocaleString('zh-CN') }
function percent(value: number | null) { return value == null ? '暂无' : `${(Number(value) * 100).toFixed(2)}%` }
function delta(value: number | null) { return value == null ? '无对比基线' : `${value >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(1)}%` }
async function load() {
  loading.value = true
  try {
    const { data } = await http.get<{ count: number; results: ShopData[] }>('/shops/monthly/', { params: filters })
    rows.value = data.results
  } finally { loading.value = false }
}
async function init() {
  const { data } = await http.get<DashboardData>('/dashboard/')
  months.value = data.available_months
  filters.month = data.month || ''
  await load()
}
onMounted(init)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-toolbar">
      <div><div class="month-title">店铺月度经营分析</div><div class="month-subtitle">统一查看成交、流量转化、广告与利润表现</div></div>
      <div class="toolbar-group">
        <el-select v-model="filters.month" placeholder="选择月份" style="width:140px" @change="load"><el-option v-for="month in months" :key="month" :label="month" :value="month" /></el-select>
        <el-input v-model="filters.search" clearable placeholder="搜索店铺" style="width:180px" @keyup.enter="load" />
        <el-select v-model="filters.ordering" style="width:150px" @change="load"><el-option label="销售额降序" value="-sales" /><el-option label="订单数降序" value="-orders" /><el-option label="ROI 降序" value="-roi" /><el-option label="利润降序" value="-profit" /></el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </div>
    <div class="dimension-tabs"><span class="active">店铺</span><span @click="$router.push('/products')">商品</span><span class="disabled">品类 · 待接入</span><span class="disabled">SKU · 待接入</span></div>
    <div class="panel grouped-table">
      <el-table :data="rows" stripe>
        <el-table-column type="index" label="#" width="56" />
        <el-table-column label="店铺" min-width="180" fixed="left"><template #default="{row}"><strong>{{ row.shop }}</strong><div class="row-sub">销售环比 <span :class="{negative:Number(row.sales_change_rate)<0}">{{ delta(row.sales_change_rate) }}</span></div></template></el-table-column>
        <el-table-column label="成交指标">
          <el-table-column label="成交金额" min-width="125"><template #default="{row}">{{ money(row.sales) }}</template></el-table-column>
          <el-table-column label="销量" width="82"><template #default="{row}">{{ integer(row.sales_volume) }}</template></el-table-column>
          <el-table-column label="订单" width="82"><template #default="{row}">{{ integer(row.orders) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="流量转化">
          <el-table-column label="访客" width="95"><template #default="{row}">{{ integer(row.visitors) }}</template></el-table-column>
          <el-table-column label="转化率" width="95"><template #default="{row}">{{ percent(row.conversion_rate) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="广告指标">
          <el-table-column label="花费" min-width="115"><template #default="{row}">{{ money(row.ad_cost) }}</template></el-table-column>
          <el-table-column label="ROI" width="76"><template #default="{row}">{{ Number(row.roi).toFixed(2) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="利润财务">
          <el-table-column label="利润" min-width="115"><template #default="{row}">{{ money(row.profit) }}</template></el-table-column>
          <el-table-column label="利润率" width="95"><template #default="{row}">{{ percent(row.profit_rate) }}</template></el-table-column>
        </el-table-column>
      </el-table>
      <el-empty v-if="!rows.length && !loading" description="当前月份暂无店铺数据" />
    </div>
  </div>
</template>

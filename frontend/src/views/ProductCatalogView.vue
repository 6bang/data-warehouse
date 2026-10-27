<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'
import type { Paginated, ProductCatalog, StrategyOptions } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const rows = ref<ProductCatalog[]>([])
const total = ref(0)
const filters = reactive({ search: '', platform: '', shop: '', lifecycle: '', ordering: '-product_created_at', page: 1, page_size: 20 })
const options = ref<StrategyOptions | null>(null)
const createDialog = ref(false)
const creating = ref(false)
const form = reactive({ plan_name: '', strategy: null as number | null, organization: '', shop: '', product_id: '', product_name: '', product_url: '', objective: '', actions: '', owner: null as number | null, start_date: '', deadline: '' })

function dateTime(value: string | null) {
  if (!value) return '暂无'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
    const { data } = await http.get<Paginated<ProductCatalog>>('/product-catalog/', { params })
    rows.value = data.results
    total.value = data.count
  } finally {
    loading.value = false
  }
}

function search() {
  filters.page = 1
  load()
}

function lifecycleLabel(row: ProductCatalog) {
  if (row.lifecycle_label) return row.lifecycle_label
  if (row.product_age_days == null) return '未知'
  return row.product_age_days <= 35 ? '新品' : '老品'
}

function lifecycleTagType(row: ProductCatalog) {
  const lifecycle = row.lifecycle || (row.product_age_days == null ? 'unknown' : row.product_age_days <= 35 ? 'new' : 'mature')
  return lifecycle === 'new' ? 'success' : lifecycle === 'mature' ? 'warning' : 'info'
}

async function loadOptions() {
  if (options.value) return
  try {
    const { data } = await http.get<StrategyOptions>('/strategy-options/')
    options.value = data
  } catch {
    // 负责人是可选字段，选项加载失败不应阻止计划创建
    options.value = null
  }
}

async function openCreatePlan(row: ProductCatalog) {
  await loadOptions()
  const today = new Date().toISOString().slice(0, 10)
  Object.assign(form, {
    plan_name: `${row.product_name || row.product_id || '商品'}运营计划`,
    strategy: null,
    organization: row.organization || options.value?.dimensions.selected.organization || '',
    shop: row.shop || '',
    product_id: row.product_id || '',
    product_name: row.product_name || '',
    product_url: '',
    objective: '',
    actions: '',
    owner: null,
    start_date: today,
    deadline: '',
  })
  createDialog.value = true
}

async function createPlan() {
  if (!form.plan_name.trim()) {
    ElMessage.warning('请填写计划名称')
    return
  }
  if (!form.organization.trim()) {
    ElMessage.warning('缺少所属组织，无法创建计划')
    return
  }
  creating.value = true
  try {
    await http.post('/operation-plans/', form)
    createDialog.value = false
    ElMessage.success('运营计划已创建')
  } catch {
    ElMessage.error('运营计划创建失败，请稍后重试')
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-toolbar">
      <div>
        <div class="month-title">商品档案</div>
        <div class="month-subtitle">独立维护商品名称、创建时间和商品货号，不与月度经营指标混在一起</div>
      </div>
      <div class="toolbar-group">
        <el-input v-model="filters.search" clearable placeholder="商品名称 / ID / 货号" style="width:220px" @keyup.enter="search" />
        <el-input v-model="filters.shop" clearable placeholder="全部店铺" style="width:150px" @keyup.enter="search" />
        <el-select v-model="filters.lifecycle" clearable placeholder="全部商品" style="width:155px" @change="search">
          <el-option label="新品（1-35天）" value="new" />
          <el-option label="老品（36天以上）" value="mature" />
          <el-option label="创建时间未知" value="unknown" />
        </el-select>
        <el-select v-model="filters.ordering" style="width:150px" @change="search">
          <el-option label="创建时间倒序" value="-product_created_at" />
          <el-option label="商品名称排序" value="product_name" />
          <el-option label="货号排序" value="product_code" />
          <el-option label="店铺排序" value="shop" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
      </div>
    </div>

    <div class="panel" style="padding:0;overflow:hidden">
      <el-table :data="rows" stripe>
        <el-table-column type="index" label="#" width="56" />
        <el-table-column label="商品名称" min-width="310" fixed="left">
          <template #default="{ row }">
            <div class="product-cell"><ProductImage :src="row.product_image_url" /><div><strong>{{ row.product_name || '未命名商品' }}</strong><div class="row-sub">{{ row.product_id }}</div></div></div>
          </template>
        </el-table-column>
        <el-table-column prop="product_code" label="商品货号" min-width="160">
          <template #default="{ row }">{{ row.product_code || '暂无' }}</template>
        </el-table-column>
        <el-table-column prop="product_created_at" label="商品创建时间" min-width="190">
          <template #default="{ row }">{{ dateTime(row.product_created_at) }}</template>
        </el-table-column>
        <el-table-column prop="product_age_days" label="创建天数" width="110">
          <template #default="{ row }">{{ row.product_age_days == null || row.lifecycle === 'unknown' ? '暂无' : `第 ${row.product_age_days} 天` }}</template>
        </el-table-column>
        <el-table-column label="商品类型" width="110">
          <template #default="{ row }"><el-tag size="small" :type="lifecycleTagType(row)">{{ lifecycleLabel(row) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="platform" label="平台" width="110" />
        <el-table-column prop="shop" label="店铺" min-width="160" />
        <el-table-column prop="last_seen_month" label="最近同步月份" width="130">
          <template #default="{ row }">{{ row.last_seen_month || '暂无' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }"><el-button link type="primary" @click="openCreatePlan(row)">新建计划</el-button></template>
        </el-table-column>
      </el-table>
    </div>
    <div style="display:flex;justify-content:flex-end;margin-top:14px">
      <el-pagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" layout="total, prev, pager, next" :total="total" @current-change="load" />
    </div>

    <el-dialog v-model="createDialog" title="新建运营计划" width="min(780px,95vw)">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="计划名称"><el-input v-model="form.plan_name" /></el-form-item>
          <el-form-item label="负责人"><el-select v-model="form.owner" clearable class="full-width" placeholder="未分配"><el-option v-for="user in options?.users" :key="user.id" :label="user.first_name || user.username" :value="user.id" /></el-select></el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="商品名称"><el-input v-model="form.product_name" /></el-form-item>
          <el-form-item label="商品 ID"><el-input v-model="form.product_id" /></el-form-item>
        </div>
        <div class="form-grid">
          <el-form-item label="所属店铺"><el-input v-model="form.shop" /></el-form-item>
          <el-form-item label="组织"><el-input v-model="form.organization" /></el-form-item>
        </div>
        <el-form-item label="运营目标"><el-input v-model="form.objective" type="textarea" :rows="3" placeholder="例如：提升新品转化率、完成本周销量目标" /></el-form-item>
        <el-form-item label="执行动作"><el-input v-model="form.actions" type="textarea" :rows="4" placeholder="填写要执行的运营动作" /></el-form-item>
        <div class="form-grid">
          <el-form-item label="开始日期"><el-date-picker v-model="form.start_date" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
          <el-form-item label="截止日期"><el-date-picker v-model="form.deadline" value-format="YYYY-MM-DD" class="full-width" /></el-form-item>
        </div>
      </el-form>
      <template #footer><el-button @click="createDialog = false">取消</el-button><el-button type="primary" :loading="creating" @click="createPlan">创建计划</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.product-cell{display:flex;align-items:center;gap:10px;min-width:0}.product-cell>div:last-child{min-width:0}.product-cell strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.full-width{width:100%}
@media(max-width:800px){.form-grid{grid-template-columns:1fr}}
</style>

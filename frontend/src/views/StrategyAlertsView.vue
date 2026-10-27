<script setup lang="ts">
import { Link, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { OperationStrategy, Paginated, StrategyAlert, StrategyOptions } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const running = ref(false)
const alerts = ref<StrategyAlert[]>([])
const total = ref(0)
const strategies = ref<OperationStrategy[]>([])
const options = ref<StrategyOptions | null>(null)
const filters = reactive({ month: '', status: '', level: '', strategy_id: '' as number | '' })
const planDialog = ref(false)
const selectedAlert = ref<StrategyAlert | null>(null)
const planForm = reactive({ owner_id: null as number | null, deadline: '', objective: '', actions: '' })
const openCount = computed(() => alerts.value.filter(item => item.status === 'open').length)
const criticalCount = computed(() => alerts.value.filter(item => item.level === 'critical' && item.status !== 'resolved').length)
const agentCount = computed(() => new Set(alerts.value.filter(item => item.reporter_name && item.reporter_name !== '系统规则播报').map(item => item.reporter_name)).size)

async function loadOptions() {
  const [optionResult, strategyResult] = await Promise.all([http.get<StrategyOptions>('/strategy-options/'), http.get<Paginated<OperationStrategy>>('/operation-strategies/', { params: { page_size: 100 } })])
  options.value = optionResult.data; strategies.value = strategyResult.data.results
  filters.month ||= optionResult.data.dimensions.selected.month
}
async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([,value]) => value !== ''))
    const { data } = await http.get<Paginated<StrategyAlert>>('/strategy-alerts/', { params: { ...params, page_size: 100 } })
    alerts.value = data.results; total.value = data.count
  } finally { loading.value = false }
}
async function init() { await loadOptions(); await load() }
async function runAll() {
  running.value = true
  try {
    const { data } = await http.post('/operation-strategies/run_all/', { month: filters.month })
    const count = data.results.reduce((sum: number, item: {alerts:number}) => sum + item.alerts, 0)
    ElMessage.success(`已运行 ${data.strategies} 个策略，生成/刷新 ${count} 条预警`); await load()
  } finally { running.value = false }
}
async function setStatus(item: StrategyAlert, status: 'acknowledged' | 'resolved') { await http.post(`/strategy-alerts/${item.id}/set_status/`, { status }); ElMessage.success(status === 'resolved' ? '预警已解除' : '预警已确认'); await load() }
function openPlan(item: StrategyAlert) { selectedAlert.value = item; Object.assign(planForm, { owner_id: null, deadline: '', objective: item.description, actions: item.suggestion || item.agent_report }); planDialog.value = true }
async function createPlan() {
  if (!selectedAlert.value) return
  await http.post(`/strategy-alerts/${selectedAlert.value.id}/convert_plan/`, planForm)
  planDialog.value = false; ElMessage.success('已转为运营计划'); await load()
}
function threshold(item: StrategyAlert) { const value = item.threshold_snapshot; return `${value.operator_label || value.operator} ${value.threshold}${value.threshold_max?` ~ ${value.threshold_max}`:''}` }
function levelType(level: string) { return level === 'critical' ? 'danger' : level === 'warning' ? 'warning' : 'info' }
function statusType(status: string) { return status === 'open' ? 'danger' : status === 'acknowledged' ? 'warning' : status === 'converted' ? 'success' : 'info' }
function formatValue(item: StrategyAlert) { const value = Number(item.observed_value); return ['refund_rate','gross_margin','net_margin'].includes(item.metric) ? `${(value*100).toFixed(1)}%` : ['sales','refund_amount','ad_cost','gross_profit','net_profit'].includes(item.metric) ? `¥${value.toLocaleString('zh-CN',{maximumFractionDigits:2})}` : value.toLocaleString('zh-CN',{maximumFractionDigits:2}) }
onMounted(init)
</script>

<template>
  <div class="page alerts-page" v-loading="loading">
    <div class="page-toolbar"><div><div class="month-title">运营策略预警</div><div class="month-subtitle">规则自动筛选商品链接，命中后由系统或指定智能体播报</div></div><div class="toolbar-group"><el-button :icon="Refresh" @click="load">刷新</el-button><el-button type="primary" :icon="VideoPlay" :loading="running" @click="runAll">立即运行全部策略</el-button></div></div>
    <div class="alert-summary"><div class="panel"><small>预警总数</small><strong>{{ total }}</strong></div><div class="panel"><small>待处理</small><strong>{{ openCount }}</strong></div><div class="panel danger"><small>严重预警</small><strong>{{ criticalCount }}</strong></div><div class="panel"><small>播报智能体</small><strong>{{ agentCount || '系统' }}</strong></div></div>
    <div class="panel alert-filters"><el-select v-model="filters.month" style="width:130px" @change="load"><el-option v-for="month in options?.dimensions.months" :key="month" :label="month" :value="month" /></el-select><el-select v-model="filters.strategy_id" clearable placeholder="全部策略" style="width:220px" @change="load"><el-option v-for="item in strategies" :key="item.id" :label="item.name" :value="item.id!" /></el-select><el-select v-model="filters.level" clearable placeholder="全部等级" style="width:130px" @change="load"><el-option label="严重" value="critical" /><el-option label="警告" value="warning" /><el-option label="提示" value="info" /></el-select><el-select v-model="filters.status" clearable placeholder="全部状态" style="width:140px" @change="load"><el-option label="待处理" value="open" /><el-option label="已确认" value="acknowledged" /><el-option label="已转计划" value="converted" /><el-option label="已解除" value="resolved" /></el-select></div>
    <div class="panel alert-table"><el-table :data="alerts" stripe>
      <el-table-column type="expand"><template #default="{row}"><div class="alert-detail"><section><b>命中说明</b><p>{{ row.description }}</p></section><section><b>{{ row.reporter_name || '系统规则播报' }}</b><p>{{ row.agent_report || '尚未生成播报' }}</p></section><section><b>行动建议</b><p>{{ row.suggestion || '确认数据后制定运营计划' }}</p></section></div></template></el-table-column>
      <el-table-column label="等级" width="82"><template #default="{row}"><el-tag :type="levelType(row.level)" effect="dark">{{ row.level_label }}</el-tag></template></el-table-column>
      <el-table-column label="商品" min-width="310"><template #default="{ row }"><div class="product-alert"><div class="product-alert-main"><ProductImage :src="row.product_image_url" /><div><b>{{ row.product_name || row.product_id }}</b><small>{{ row.platform }} · {{ row.shop }} · {{ row.product_id }}</small></div></div><el-link v-if="row.product_url" :href="row.product_url" target="_blank" type="primary" :icon="Link">商品</el-link></div></template></el-table-column>
      <el-table-column label="策略 / 规则" min-width="210"><template #default="{row}">{{ row.strategy_name }}<div class="row-sub">{{ row.rule_name }}</div></template></el-table-column>
      <el-table-column label="当前指标" width="135"><template #default="{row}"><b>{{ formatValue(row) }}</b><div class="row-sub">{{ row.metric_label }}</div></template></el-table-column>
      <el-table-column label="触发条件" min-width="145"><template #default="{row}">{{ threshold(row) }}</template></el-table-column>
      <el-table-column label="负责人" width="120"><template #default="{row}">{{ row.operator_name || '未分配' }}</template></el-table-column>
      <el-table-column label="播报" width="145"><template #default="{row}"><el-tag effect="plain">{{ row.reporter_name || '系统' }}</el-tag></template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="statusType(row.status)">{{ row.status_label }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="220" fixed="right"><template #default="{row}"><el-button v-if="row.status==='open'" link type="warning" @click="setStatus(row,'acknowledged')">确认</el-button><el-button v-if="!['converted','resolved'].includes(row.status)" link type="primary" @click="openPlan(row)">转运营计划</el-button><el-button v-if="row.status!=='resolved'" link type="info" @click="setStatus(row,'resolved')">解除</el-button></template></el-table-column>
    </el-table><el-empty v-if="!alerts.length" description="当前筛选范围没有策略预警；可先创建策略并立即运行" /></div>
    <el-dialog v-model="planDialog" title="转为运营计划" width="min(680px,94vw)"><el-form label-position="top"><el-form-item label="目标"><el-input v-model="planForm.objective" type="textarea" :rows="3" /></el-form-item><el-form-item label="执行动作"><el-input v-model="planForm.actions" type="textarea" :rows="4" /></el-form-item><div class="plan-grid"><el-form-item label="负责人"><el-select v-model="planForm.owner_id" clearable class="full-width"><el-option v-for="user in options?.users" :key="user.id" :label="user.first_name || user.username" :value="user.id" /></el-select></el-form-item><el-form-item label="截止日期"><el-date-picker v-model="planForm.deadline" value-format="YYYY-MM-DD" class="full-width" /></el-form-item></div></el-form><template #footer><el-button @click="planDialog=false">取消</el-button><el-button type="primary" @click="createPlan">创建计划</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.alerts-page{max-width:1650px;margin:auto}.alert-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.alert-summary .panel{display:grid;gap:8px}.alert-summary small{color:var(--app-text-muted)}.alert-summary strong{font-size:23px}.alert-summary .danger strong{color:#ff7474}.alert-filters{display:flex;gap:10px;flex-wrap:wrap;padding:14px;margin-bottom:14px}.alert-table{padding:0;overflow:hidden}.product-alert{display:flex;align-items:center;justify-content:space-between;gap:10px}.product-alert-main{display:flex;align-items:center;gap:10px;min-width:0}.product-alert-main>div:last-child{display:grid;gap:5px;min-width:0}.product-alert b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.product-alert small{color:var(--app-text-muted)}.alert-detail{padding:6px 42px 18px;display:grid;grid-template-columns:1fr 1.2fr 1fr;gap:20px}.alert-detail section{border-left:2px solid #7567ff;padding-left:14px}.alert-detail p{color:var(--app-text-secondary);line-height:1.7;margin:8px 0 0}.plan-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:900px){.alert-summary{grid-template-columns:1fr 1fr}.alert-detail{grid-template-columns:1fr}}@media(max-width:600px){.alert-summary,.plan-grid{grid-template-columns:1fr}}
</style>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { DashboardData } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

interface ActionItem { task_name: string; product_id?: string; product_image_url?: string; problem: string; suggestion: string; abnormal_record_id?: number; created?: boolean }
interface AnalysisOutput { problems: string[]; reasons: string[]; suggestions: string[]; actions: ActionItem[]; provider_notice?: string }
interface AnalysisRun { id: number; provider: string; model: string; month: string; date: string; input_context: any; output: AnalysisOutput }

const loading = ref(false)
const run = ref<AnalysisRun>()
const months = ref<string[]>([])
const form = reactive({ month: '', shop: '', product_id: '', question: '请分析本月最重要的经营问题，并告诉我下个月先做什么。' })
const evidence = computed(() => {
  const metrics = run.value?.input_context?.dashboard?.metrics || {}
  return Object.entries(metrics).slice(0, 8).map(([key, item]: [string, any]) => ({ key, value: item.value, change: item.change_rate }))
})
const labels: Record<string, string> = { sales: '销售额', sales_volume: '销量', orders: '订单数', visitors: '访客', conversion_rate: '转化率', ad_cost: '广告花费', roi: 'ROI', profit: '毛利润' }

async function analyze() {
  loading.value = true
  try {
    const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => value))
    const { data } = await http.post<AnalysisRun>('/ai-analysis/', payload)
    run.value = data
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '分析失败') } finally { loading.value = false }
}
async function createAction(action: ActionItem) {
  if (action.abnormal_record_id) await http.post('/tasks/from_abnormal/', { abnormal_record_id: action.abnormal_record_id, task_name: action.task_name })
  else await http.post('/tasks/', { task_name: action.task_name, product_id: action.product_id || '', problem: action.problem, ai_suggestion: action.suggestion, source: 'ai', ai_analysis_run: run.value?.id })
  action.created = true; ElMessage.success('行动项已写入任务中心')
}
function evidenceValue(key: string, value: any) {
  if (value === null) return '暂无数据'
  if (['sales','ad_cost','profit'].includes(key)) return `¥${Number(value).toLocaleString('zh-CN')}`
  if (key === 'conversion_rate') return `${(Number(value) * 100).toFixed(2)}%`
  if (key === 'roi') return Number(value).toFixed(2)
  return Number(value).toLocaleString('zh-CN')
}
onMounted(async () => { const { data } = await http.get<DashboardData>('/dashboard/'); months.value = data.available_months; form.month = data.month || '' })
</script>

<template><div class="page"><div class="content-grid" style="grid-template-columns:minmax(280px,.7fr) minmax(0,1.5fr);margin-top:0">
  <div class="panel"><div class="panel-title">月度分析范围</div><el-form label-position="top"><el-form-item label="月份"><el-select v-model="form.month" class="full-width" placeholder="选择月份"><el-option v-for="month in months" :key="month" :label="month" :value="month" /></el-select></el-form-item><el-form-item label="店铺"><el-input v-model="form.shop" placeholder="留空则分析全部店铺" /></el-form-item><el-form-item label="商品 ID"><el-input v-model="form.product_id" placeholder="留空则分析全部商品" /></el-form-item><el-form-item label="补充问题"><el-input v-model="form.question" type="textarea" :rows="5" /></el-form-item><el-button type="primary" class="full-width" :loading="loading" @click="analyze">开始月度分析</el-button></el-form><el-alert style="margin-top:16px" type="info" :closable="false" title="AI 建议需人工确认后才会生成任务，不会自动修改广告或商品。" /></div>
  <div class="section-stack"><div v-if="!run" class="panel"><el-empty description="选择范围并启动经营分析 Agent" /></div><template v-else><div class="panel"><div class="page-toolbar" style="margin-bottom:12px"><div class="panel-title" style="margin:0">证据指标</div><el-tag effect="plain">{{ run.provider === 'openai_compatible' ? `大模型 · ${run.model}` : '可解释规则引擎' }}</el-tag></div><div class="metric-evidence"><div v-for="item in evidence" :key="item.key" class="evidence"><div class="evidence-label">{{ labels[item.key] || item.key }}</div><div class="evidence-value">{{ evidenceValue(item.key,item.value) }}</div><div class="kpi-delta" :class="{down:Number(item.change)<0}">{{ item.change == null ? '无基线' : `${Number(item.change)>=0?'+':''}${(Number(item.change)*100).toFixed(1)}%` }}</div></div></div></div><div v-if="run.output.provider_notice" class="panel"><el-alert type="warning" :closable="false" :title="run.output.provider_notice" /></div><div class="panel analysis-section"><h3>问题</h3><ul><li v-for="item in run.output.problems" :key="item">{{ item }}</li></ul></div><div class="panel analysis-section"><h3>原因</h3><ul><li v-for="item in run.output.reasons" :key="item">{{ item }}</li></ul></div><div class="panel analysis-section"><h3>建议</h3><ul><li v-for="item in run.output.suggestions" :key="item">{{ item }}</li></ul></div><div class="panel"><div class="panel-title">行动任务</div><el-empty v-if="!run.output.actions.length" description="当前没有需要创建的任务" :image-size="65" /><div v-for="action in run.output.actions" :key="action.task_name" class="anomaly-item"><el-tag effect="plain">行动</el-tag><ProductImage v-if="action.product_id" :src="action.product_image_url" /><div><div>{{ action.task_name }}</div><div style="font-size:12px;color:#8792a4;margin-top:5px">{{ action.suggestion }}</div></div><el-button size="small" type="primary" plain :disabled="action.created" @click="createAction(action)">{{ action.created ? '已创建' : '创建任务' }}</el-button></div></div></template></div>
</div></div></template>

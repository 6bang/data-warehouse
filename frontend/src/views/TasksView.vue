<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { DashboardData, Paginated, Task } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const tasks = ref<Task[]>([])
const total = ref(0)
const months = ref<string[]>([])
const dialogVisible = ref(false)
const filters = reactive({ month: '', status: '', page: 1 })
const form = reactive({ task_name: '', product_id: '', problem: '', ai_suggestion: '', owner: null as number | null, deadline: '', source: 'manual' })
const statusCounts = computed(() => ({
  pending: tasks.value.filter(item => item.status === 'pending').length,
  in_progress: tasks.value.filter(item => item.status === 'in_progress').length,
  completed: tasks.value.filter(item => item.status === 'completed').length,
  reviewed: tasks.value.filter(item => item.status === 'reviewed').length,
}))

async function load() {
  loading.value = true
  try {
    const { data } = await http.get<Paginated<Task>>('/tasks/', { params: { page: filters.page, ...(filters.month ? { month: filters.month } : {}), ...(filters.status ? { status: filters.status } : {}) } })
    tasks.value = data.results; total.value = data.count
  } finally { loading.value = false }
}
async function createTask() {
  await http.post('/tasks/', { ...form, owner: form.owner || null, deadline: form.deadline || null })
  ElMessage.success('任务已创建'); dialogVisible.value = false; Object.assign(form, { task_name: '', product_id: '', problem: '', ai_suggestion: '', owner: null, deadline: '', source: 'manual' }); load()
}
async function transition(task: Task, target: string) {
  const payload: Record<string, string> = { status: target }
  if (target === 'completed') payload.result = task.result || '已执行，待复盘'
  if (target === 'reviewed') payload.review_result = task.review_result || '已完成复盘'
  await http.post(`/tasks/${task.id}/transition/`, payload)
  ElMessage.success('状态已更新'); load()
}
function nextAction(task: Task) {
  return task.status === 'pending' ? ['开始执行', 'in_progress'] : task.status === 'in_progress' ? ['标记完成', 'completed'] : task.status === 'completed' ? ['完成复盘', 'reviewed'] : ['', '']
}
function tagType(status: string) { return status === 'pending' ? 'warning' : status === 'in_progress' ? 'primary' : status === 'completed' ? 'success' : 'info' }
async function init() { const { data } = await http.get<DashboardData>('/dashboard/'); months.value = data.available_months; filters.month = data.month || ''; await load() }
onMounted(init)
</script>

<template><div class="page" v-loading="loading">
  <div class="page-toolbar"><div><div class="month-title">月度运营任务</div><div class="month-subtitle">按任务创建月份跟踪执行与复盘</div></div><div class="toolbar-group"><el-select v-model="filters.month" placeholder="选择月份" style="width:140px" @change="load"><el-option v-for="month in months" :key="month" :label="month" :value="month" /></el-select><el-select v-model="filters.status" clearable placeholder="全部状态" style="width:150px" @change="load"><el-option label="待处理" value="pending" /><el-option label="执行中" value="in_progress" /><el-option label="已完成" value="completed" /><el-option label="已复盘" value="reviewed" /></el-select><el-button type="primary" :icon="Plus" @click="dialogVisible = true">新建任务</el-button></div></div>
  <div class="kpi-grid" style="margin-bottom:12px"><div v-for="item in [{k:'pending',l:'待处理'},{k:'in_progress',l:'执行中'},{k:'completed',l:'已完成'},{k:'reviewed',l:'已复盘'}]" :key="item.k" class="panel"><div class="kpi-label">{{ item.l }}（当前页）</div><div class="kpi-value">{{ statusCounts[item.k as keyof typeof statusCounts] }}</div></div></div>
  <div class="panel task-table-panel">
    <el-table :data="tasks" stripe class="task-table">
      <el-table-column label="任务名称" width="290">
        <template #default="{row}"><div class="task-title">{{ row.task_name }}</div><div class="task-source">{{ row.source === 'ai' ? 'AI 分析' : row.source === 'abnormal' ? '异常分析' : '人工创建' }}</div></template>
      </el-table-column>
      <el-table-column label="商品" width="210"><template #default="{ row }"><div class="task-product"><ProductImage v-if="row.product_id" :src="row.product_image_url" /><div class="wrap-cell product-id">{{ row.product_id || '—' }}</div></div></template></el-table-column>
      <el-table-column label="问题" min-width="300"><template #default="{row}"><div class="wrap-cell">{{ row.problem || '—' }}</div></template></el-table-column>
      <el-table-column label="AI 建议" min-width="330"><template #default="{row}"><div class="wrap-cell suggestion-cell">{{ row.ai_suggestion || '—' }}</div></template></el-table-column>
      <el-table-column label="负责人" width="95"><template #default="{row}">{{ row.owner_name || '未分配' }}</template></el-table-column>
      <el-table-column label="截止时间" width="150"><template #default="{row}">{{ row.deadline ? row.deadline.slice(0,16).replace('T',' ') : '未设置' }}</template></el-table-column>
      <el-table-column label="状态" width="95"><template #default="{row}"><el-tag :type="tagType(row.status)">{{ row.status_label }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="110"><template #default="{row}"><el-button v-if="nextAction(row)[0]" link type="primary" @click="transition(row, nextAction(row)[1])">{{ nextAction(row)[0] }}</el-button><span class="closed-text" v-else>已闭环</span></template></el-table-column>
    </el-table>
  </div>
  <div style="display:flex;justify-content:flex-end;margin-top:14px"><el-pagination v-model:current-page="filters.page" layout="total, prev, pager, next" :total="total" @current-change="load" /></div>
  <el-dialog v-model="dialogVisible" title="新建运营任务" width="min(620px,92vw)"><el-form label-position="top"><el-form-item label="任务名称"><el-input v-model="form.task_name" /></el-form-item><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><el-form-item label="商品 ID"><el-input v-model="form.product_id" /></el-form-item><el-form-item label="截止时间"><el-date-picker v-model="form.deadline" value-format="YYYY-MM-DDTHH:mm:ssZ" type="datetime" class="full-width" /></el-form-item></div><el-form-item label="问题"><el-input v-model="form.problem" type="textarea" :rows="3" /></el-form-item><el-form-item label="处理建议"><el-input v-model="form.ai_suggestion" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" :disabled="!form.task_name" @click="createTask">创建</el-button></template></el-dialog>
</div></template>

<style scoped>
.task-table-panel{padding:0;overflow:hidden}.task-product{display:flex;align-items:center;gap:9px;min-width:0}.task-table :deep(.el-table__cell){vertical-align:top}.task-title,.wrap-cell{white-space:normal;overflow-wrap:anywhere;word-break:break-word;line-height:1.55}.task-title{font-weight:600}.task-source{font-size:12px;color:var(--app-text-muted);margin-top:7px}.wrap-cell{padding:2px 0;color:var(--app-text-secondary)}.suggestion-cell{color:var(--app-text)}.product-id{font-variant-numeric:tabular-nums}.closed-text{color:var(--app-text-muted)}
</style>

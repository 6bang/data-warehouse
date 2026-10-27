<script setup lang="ts">
import { Link, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { OperationPlan, OperationStrategy, Paginated, StrategyOptions } from '@/api/types'
import ProductImage from '@/components/ProductImage.vue'

const loading = ref(false)
const plans = ref<OperationPlan[]>([])
const total = ref(0)
const options = ref<StrategyOptions | null>(null)
const strategies = ref<OperationStrategy[]>([])
const filters = reactive({ status: '', owner_id: '' as number | '', strategy_id: '' as number | '' })
const createDialog = ref(false)
const resultDialog = ref(false)
const selectedPlan = ref<OperationPlan | null>(null)
const targetStatus = ref('')
const resultText = ref('')
const form = reactive({ plan_name: '', strategy: null as number | null, organization: '', shop: '', product_id: '', product_name: '', product_url: '', objective: '', actions: '', owner: null as number | null, start_date: '', deadline: '' })
const counts = computed(() => ({ pending: plans.value.filter(item=>item.status==='pending').length, in_progress: plans.value.filter(item=>item.status==='in_progress').length, completed: plans.value.filter(item=>item.status==='completed').length, reviewed: plans.value.filter(item=>item.status==='reviewed').length }))

async function loadOptions() {
  const [optionResult, strategyResult] = await Promise.all([http.get<StrategyOptions>('/strategy-options/'), http.get<Paginated<OperationStrategy>>('/operation-strategies/', { params: { page_size: 100 } })])
  options.value = optionResult.data; strategies.value = strategyResult.data.results
}
async function load() {
  loading.value = true
  try { const params = Object.fromEntries(Object.entries(filters).filter(([,value])=>value!=='')); const {data}=await http.get<Paginated<OperationPlan>>('/operation-plans/',{params:{...params,page_size:100}}); plans.value=data.results;total.value=data.count }
  finally { loading.value=false }
}
async function init(){await loadOptions();await load()}
function openCreate(){Object.assign(form,{plan_name:'',strategy:null,organization:options.value?.dimensions.selected.organization||'',shop:'',product_id:'',product_name:'',product_url:'',objective:'',actions:'',owner:null,start_date:new Date().toISOString().slice(0,10),deadline:''});createDialog.value=true}
async function create(){if(!form.plan_name)return ElMessage.warning('请填写计划名称');await http.post('/operation-plans/',form);createDialog.value=false;ElMessage.success('运营计划已创建');await load()}
function nextAction(plan:OperationPlan){return plan.status==='pending'?['开始执行','in_progress']:plan.status==='in_progress'?['完成','completed']:plan.status==='completed'?['复盘','reviewed']:['','']}
async function transition(plan:OperationPlan){const [,target]=nextAction(plan);if(!target)return;selectedPlan.value=plan;targetStatus.value=target;resultText.value='';if(['completed','reviewed'].includes(target)){resultDialog.value=true;return}await submitTransition()}
async function submitTransition(){if(!selectedPlan.value)return;const payload:Record<string,string>={status:targetStatus.value};if(targetStatus.value==='completed')payload.result=resultText.value;if(targetStatus.value==='reviewed')payload.review_result=resultText.value;await http.post(`/operation-plans/${selectedPlan.value.id}/transition/`,payload);resultDialog.value=false;ElMessage.success('计划状态已更新');await load()}
function tagType(status:string){return status==='pending'?'warning':status==='in_progress'?'primary':status==='completed'?'success':'info'}
onMounted(init)
</script>

<template>
  <div class="page plans-page" v-loading="loading">
    <div class="page-toolbar"><div><div class="month-title">运营计划</div><div class="month-subtitle">承接策略预警，明确负责人、截止日期、执行结果与复盘结论</div></div><div class="toolbar-group"><el-button :icon="Refresh" @click="load">刷新</el-button><el-button type="primary" :icon="Plus" @click="openCreate">新建计划</el-button></div></div>
    <div class="plan-summary"><div class="panel"><small>计划总数</small><strong>{{ total }}</strong></div><div class="panel"><small>待执行</small><strong>{{ counts.pending }}</strong></div><div class="panel"><small>执行中</small><strong>{{ counts.in_progress }}</strong></div><div class="panel"><small>已复盘</small><strong>{{ counts.reviewed }}</strong></div></div>
    <div class="panel plan-filters"><el-select v-model="filters.status" clearable placeholder="全部状态" style="width:150px" @change="load"><el-option label="待执行" value="pending" /><el-option label="执行中" value="in_progress" /><el-option label="已完成" value="completed" /><el-option label="已复盘" value="reviewed" /></el-select><el-select v-model="filters.strategy_id" clearable placeholder="全部策略" style="width:220px" @change="load"><el-option v-for="item in strategies" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-select v-model="filters.owner_id" clearable placeholder="全部负责人" style="width:160px" @change="load"><el-option v-for="user in options?.users" :key="user.id" :label="user.first_name||user.username" :value="user.id" /></el-select></div>
    <div class="panel plan-table"><el-table :data="plans" stripe>
      <el-table-column label="计划名称" min-width="240"><template #default="{row}"><b>{{ row.plan_name }}</b><div class="row-sub">{{ row.strategy_name || '人工计划' }}</div></template></el-table-column>
      <el-table-column label="商品" min-width="300"><template #default="{ row }"><div class="plan-product"><div v-if="row.product_id || row.product_name" class="plan-product-main"><ProductImage :src="row.product_image_url" /><span>{{ row.product_name||row.product_id }}<small>{{ row.shop||row.organization }}</small></span></div><span v-else>全部商品<small>{{ row.shop||row.organization }}</small></span><el-link v-if="row.product_url" :href="row.product_url" target="_blank" type="primary" :icon="Link">链接</el-link></div></template></el-table-column>
      <el-table-column prop="objective" label="目标" min-width="230" show-overflow-tooltip />
      <el-table-column prop="actions" label="执行动作" min-width="250" show-overflow-tooltip />
      <el-table-column label="负责人" width="110"><template #default="{row}">{{ row.owner_name||'未分配' }}</template></el-table-column>
      <el-table-column label="周期" width="175"><template #default="{row}">{{ row.start_date||'—' }}<div class="row-sub">截止 {{ row.deadline||'未设置' }}</div></template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="tagType(row.status)">{{ row.status_label }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="110" fixed="right"><template #default="{row}"><el-button v-if="nextAction(row)[0]" link type="primary" @click="transition(row)">{{ nextAction(row)[0] }}</el-button><span v-else class="row-sub">已闭环</span></template></el-table-column>
    </el-table><el-empty v-if="!plans.length" description="尚无运营计划，可从预警一键转入或手动创建" /></div>
    <el-dialog v-model="createDialog" title="新建运营计划" width="min(780px,95vw)"><el-form label-position="top"><div class="form-grid"><el-form-item label="计划名称"><el-input v-model="form.plan_name" /></el-form-item><el-form-item label="关联策略"><el-select v-model="form.strategy" clearable class="full-width"><el-option v-for="item in strategies" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div><div class="form-grid"><el-form-item label="商品名称"><el-input v-model="form.product_name" /></el-form-item><el-form-item label="商品 ID"><el-input v-model="form.product_id" /></el-form-item></div><el-form-item label="商品链接"><el-input v-model="form.product_url" /></el-form-item><el-form-item label="运营目标"><el-input v-model="form.objective" type="textarea" :rows="3" /></el-form-item><el-form-item label="执行动作"><el-input v-model="form.actions" type="textarea" :rows="4" /></el-form-item><div class="form-grid three"><el-form-item label="负责人"><el-select v-model="form.owner" clearable class="full-width"><el-option v-for="user in options?.users" :key="user.id" :label="user.first_name||user.username" :value="user.id" /></el-select></el-form-item><el-form-item label="开始日期"><el-date-picker v-model="form.start_date" value-format="YYYY-MM-DD" class="full-width" /></el-form-item><el-form-item label="截止日期"><el-date-picker v-model="form.deadline" value-format="YYYY-MM-DD" class="full-width" /></el-form-item></div></el-form><template #footer><el-button @click="createDialog=false">取消</el-button><el-button type="primary" @click="create">创建计划</el-button></template></el-dialog>
    <el-dialog v-model="resultDialog" :title="targetStatus==='completed'?'填写执行结果':'填写复盘结论'" width="min(620px,92vw)"><el-input v-model="resultText" type="textarea" :rows="6" :placeholder="targetStatus==='completed'?'记录完成动作与数据变化':'记录策略有效性、经验和下一轮调整'" /><template #footer><el-button @click="resultDialog=false">取消</el-button><el-button type="primary" @click="submitTransition">确认提交</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.plans-page{max-width:1650px;margin:auto}.plan-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.plan-summary .panel{display:grid;gap:8px}.plan-summary small{color:var(--app-text-muted)}.plan-summary strong{font-size:23px}.plan-filters{display:flex;gap:10px;padding:14px;margin-bottom:14px}.plan-table{padding:0;overflow:hidden}.plan-product{display:flex;align-items:center;justify-content:space-between;gap:10px}.plan-product span,.plan-product small{display:block}.plan-product small{color:var(--app-text-muted);margin-top:4px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.form-grid.three{grid-template-columns:repeat(3,1fr)}@media(max-width:800px){.plan-summary{grid-template-columns:1fr 1fr}.form-grid,.form-grid.three{grid-template-columns:1fr}}@media(max-width:500px){.plan-summary{grid-template-columns:1fr}}
</style>

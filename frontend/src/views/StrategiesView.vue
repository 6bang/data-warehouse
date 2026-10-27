<script setup lang="ts">
import { Delete, Plus, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { OperationStrategy, Paginated, StrategyOptions, StrategyRule } from '@/api/types'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const strategies = ref<OperationStrategy[]>([])
const options = ref<StrategyOptions | null>(null)
const selectedMonth = ref('')
const metrics = [
  ['sales', '成交金额'], ['orders', '订单数'], ['refund_amount', '退款金额'], ['refund_rate', '退款率'],
  ['ad_cost', '广告花费'], ['roi', '广告 ROI'], ['gross_profit', '毛利润'], ['gross_margin', '毛利率'],
  ['net_profit', '净利润'], ['net_margin', '净利率'], ['product_age_days', '商品上架天数'],
  ['conversion_rate', '转化率'], ['cumulative_35d_sales', '新品35天累计销量'],
  ['daily_sales_volume', '日销量'], ['weekly_sales_volume', '周销量'], ['recent_30d_sales', '近30天销量'],
]
const operators = [['lt', '小于'], ['lte', '小于等于'], ['gt', '大于'], ['gte', '大于等于'], ['eq', '等于'], ['between', '介于']]
const stages = [['', '不限定'], ['week1', '第1周（1-7天，不评估）'], ['week2', '第2周（8-14天）'], ['week3', '第3周（15-21天）'], ['week4', '第4周（22-28天）'], ['week5', '第5周（29-35天）'], ['final35', '第35天结束（累计评级）'], ['old30', '老品近30天']]
const grades = [['', '不限定'], ['A', 'A类'], ['B', 'B类'], ['C', 'C类'], ['D', 'D类'], ['E', 'E类（0销量）']]
const conversionBands = [['', '不限定'], ['high', '上等马（≥3%）'], ['middle', '中等马（2-3%）'], ['low', '下等马（<2%）']]
type StrategyTemplate = 'standard' | 'new_product_35d' | 'mature_product_30d'

const newProductTargets: Record<string, Array<[number, number]>> = {
  A: [[4, 28], [5, 35], [8, 56], [10, 70]],
  B: [[3, 21], [4, 28], [5, 35], [8, 40]],
  C: [[1, 7], [1, 7], [1, 7], [1, 7]],
  D: [[0, 0], [0, 0], [0, 0], [0, 0]],
}
const newProductWeekNames = ['week2', 'week3', 'week4', 'week5']
const oldProductTargets: Record<string, number> = { A: 1000, B: 500, C: 100, D: 1, E: 0 }

function makeRule(input: Partial<StrategyRule> = {}): StrategyRule {
  return {
    name: '', metric: 'sales', operator: 'lt', threshold: 0, threshold_max: null, weekly_threshold: null,
    stage: '', product_grade: '', conversion_band: '', level: 'warning', message_template: '', suggestion: '', enabled: true,
    ...input,
  }
}
function templateRules(code: StrategyTemplate): StrategyRule[] {
  if (code === 'new_product_35d') {
    const rules: StrategyRule[] = [makeRule({ name: '第1周不评估（1-7天）', metric: 'daily_sales_volume', operator: 'eq', threshold: 0, stage: 'week1', level: 'info', enabled: false, message_template: '新品第1周不做销量预警', suggestion: '完成评价、买家秀、问大家、短视频和营销基础建设' })]
    newProductWeekNames.forEach((stage, weekIndex) => Object.entries(newProductTargets).forEach(([grade, targets]) => {
      const [daily, weekly] = targets[weekIndex]
      const gradeLabel = grade === 'D' ? 'D类滞销款' : `${grade}类`
      const suggestion = grade === 'A' || grade === 'B'
        ? '重点关注；内功：评价、买家秀、问大家；付费：测图、拉升'
        : grade === 'C'
          ? '优化标题、主图点击率、详情页、评价、买家秀、问大家及详情页短视频；付费测图'
          : '检查商品基础信息和库存，暂停无效投放并制定去化计划'
      rules.push(makeRule({
        name: `${stage === 'week2' ? '第2周' : stage === 'week3' ? '第3周' : stage === 'week4' ? '第4周' : '第5周'} ${gradeLabel}销量`,
        metric: 'daily_sales_volume', operator: daily === 0 ? 'eq' : 'lt', threshold: daily, weekly_threshold: weekly,
        stage, product_grade: grade, level: grade === 'A' || grade === 'B' ? 'critical' : 'warning',
        message_template: `${gradeLabel}新品日销量或周销量未达标`, suggestion,
      }))
    }))
    rules.push(
      makeRule({ name: '第35天结束 A类超级潜力爆款', metric: 'cumulative_35d_sales', operator: 'gte', threshold: 500, stage: 'final35', product_grade: 'A', level: 'critical', message_template: '新品35天累计销量达到A类', suggestion: '沉淀为重点潜力爆款，进入拉升计划' }),
      makeRule({ name: '第35天结束 B类潜力爆款', metric: 'cumulative_35d_sales', operator: 'between', threshold: 100, threshold_max: 499, stage: 'final35', product_grade: 'B', level: 'warning', message_template: '新品35天累计销量达到B类', suggestion: '持续关注评价、买家秀、问大家，配合测图和拉升' }),
      makeRule({ name: '第35天结束 C类动销款', metric: 'cumulative_35d_sales', operator: 'between', threshold: 1, threshold_max: 99, stage: 'final35', product_grade: 'C', level: 'warning', message_template: '新品35天累计销量达到C类', suggestion: '优化标题、主图点击率、详情页及内容组件，付费测图' }),
      makeRule({ name: '第35天结束 D类滞销款', metric: 'cumulative_35d_sales', operator: 'eq', threshold: 0, stage: 'final35', product_grade: 'D', level: 'critical', message_template: '新品35天累计销量为0', suggestion: '检查商品基础信息、库存与投放，制定去化或下架计划' }),
    )
    return rules
  }
  if (code === 'mature_product_30d') {
    const rules: StrategyRule[] = []
    Object.entries(oldProductTargets).forEach(([grade, minimum]) => {
      ;(['high', 'middle', 'low'] as const).forEach((band) => {
        const bandLabel = band === 'high' ? '上等马' : band === 'middle' ? '中等马' : '下等马'
        const plan = band === 'high' ? '拉升计划' : '优化计划'
        rules.push(makeRule({
          name: `${grade}类${bandLabel}（近30天销量）`, metric: 'recent_30d_sales', operator: grade === 'E' ? 'eq' : 'gte',
          threshold: minimum, stage: 'old30', product_grade: grade, conversion_band: band,
          level: band === 'low' ? 'critical' : 'warning', message_template: `${grade}类老品${bandLabel}需要${plan}`,
          suggestion: `${plan}：标题、点击主图、转化主图、详情页、评价、问大家、SKU优化；付费方向：拉新-蓄水-收割-测图，平补/递增，单/多计划与单/多工具，关键词、精准人群、万相台、全站推广`,
        }))
      })
    })
    return rules
  }
  return [makeRule()]
}
const emptyStrategy = (): OperationStrategy => ({
  name: '', strategy_type: 'new_product', description: '', organization: '', platform: '', shop: '', category_path: '',
  strategy_code: 'standard', new_product_days: 30, report_mode: 'system', agent_provider: null, enabled: true, schedule_enabled: true,
  schedule_hour: 7, rules: [makeRule()],
})
const form = reactive<OperationStrategy>(emptyStrategy())
const enabledCount = computed(() => strategies.value.filter(item => item.enabled).length)
const ruleCount = computed(() => strategies.value.reduce((sum, item) => sum + item.rules.length, 0))

function normalizeRule(rule?: Partial<StrategyRule> | null): StrategyRule {
  return makeRule({
    ...rule,
    name: rule?.name || '', metric: rule?.metric || 'sales', operator: rule?.operator || 'lt',
    threshold: rule?.threshold ?? 0, threshold_max: rule?.threshold_max ?? null, weekly_threshold: rule?.weekly_threshold ?? null,
    stage: rule?.stage || '', product_grade: rule?.product_grade || '', conversion_band: rule?.conversion_band || '',
    level: rule?.level || 'warning', message_template: rule?.message_template || '', suggestion: rule?.suggestion || '',
    enabled: rule?.enabled !== false,
  })
}
function normalizeStrategy(strategy?: Partial<OperationStrategy> | null): OperationStrategy {
  const base = emptyStrategy()
  return {
    ...base, ...strategy,
    strategy_code: strategy?.strategy_code || 'standard', strategy_type: strategy?.strategy_type || 'new_product',
    new_product_days: Number(strategy?.new_product_days ?? base.new_product_days),
    agent_provider: strategy?.agent_provider ?? null, rules: (strategy?.rules || [makeRule()]).map(normalizeRule),
  } as OperationStrategy
}

async function load() {
  loading.value = true
  try {
    const [strategyResult, optionResult] = await Promise.all([
      http.get<Paginated<OperationStrategy>>('/operation-strategies/', { params: { page_size: 100 } }),
      http.get<StrategyOptions>('/strategy-options/'),
    ])
    strategies.value = strategyResult.data.results.map(item => normalizeStrategy(item))
    options.value = optionResult.data
    selectedMonth.value ||= optionResult.data.dimensions.selected.month
  } finally { loading.value = false }
}
function openDialog(item?: OperationStrategy) {
  Object.assign(form, item ? normalizeStrategy(JSON.parse(JSON.stringify(item))) : emptyStrategy())
  dialogVisible.value = true
}
function applyTemplate(code: StrategyTemplate) {
  form.strategy_code = code
  if (code === 'new_product_35d') {
    form.strategy_type = 'new_product'; form.new_product_days = 35
    if (!form.name || form.name === '通用运营策略') form.name = '新品35天分级运营策略'
    form.description = '新品创建35天内按周、商品等级和销量阈值评估；第36天自动转为老品。新品第1周不评估。'
  } else if (code === 'mature_product_30d') {
    form.strategy_type = 'mature_product'; form.new_product_days = 35
    if (!form.name || form.name === '通用运营策略') form.name = '老品近30天分级运营策略'
    form.description = '商品创建超过35天即为老品，按最近30天累计销量和转化率分为上等马、中等马、下等马。'
  } else {
    form.strategy_type = 'new_product'; form.new_product_days = 30
    if (!form.name || form.name.includes('分级运营策略')) form.name = ''
    form.description = ''
  }
  form.rules = templateRules(code)
}
function addRule() { form.rules.push(makeRule()) }
function removeRule(index: number) { if (form.rules.length > 1) form.rules.splice(index, 1) }
async function save() {
  if (!form.name.trim() || form.rules.some(item => !item.name.trim())) return ElMessage.warning('请填写策略名称和规则名称')
  saving.value = true
  try {
    const readOnlyFields = ['strategy_type_label', 'strategy_code_label', 'report_mode_label', 'agent_provider_name', 'version', 'last_run_at', 'last_run_summary']
    const editable = Object.fromEntries(Object.entries(form).filter(([key]) => !readOnlyFields.includes(key)))
    const payload = {
      ...editable,
      agent_provider: form.report_mode === 'agent' ? form.agent_provider : null,
      rules: form.rules.map(rule => Object.fromEntries(Object.entries(rule).filter(([key]) => !['metric_label', 'operator_label', 'level_label'].includes(key)))),
    }
    if (form.id) await http.put(`/operation-strategies/${form.id}/`, payload)
    else await http.post('/operation-strategies/', payload)
    dialogVisible.value = false; ElMessage.success('策略规则已保存'); await load()
  } finally { saving.value = false }
}
async function toggle(item: OperationStrategy) { await http.patch(`/operation-strategies/${item.id}/`, { enabled: item.enabled }); ElMessage.success(item.enabled ? '策略已启用' : '策略已停用') }
async function run(item: OperationStrategy) {
  const { data } = await http.post(`/operation-strategies/${item.id}/run/`, { month: selectedMonth.value })
  ElMessage.success(`已扫描 ${data.scanned_products} 个商品，命中 ${data.alerts} 条预警`); await load()
}
async function remove(item: OperationStrategy) {
  await ElMessageBox.confirm(`删除策略“${item.name}”及其规则？`, '确认删除', { type: 'warning' })
  await http.delete(`/operation-strategies/${item.id}/`); await load()
}
function formatTime(value?: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚未运行' }
onMounted(load)
</script>

<template>
  <div class="page strategy-page" v-loading="loading">
    <div class="page-toolbar"><div><div class="month-title">运营策略</div><div class="month-subtitle">把新品、老品运营 SOP 写成规则，系统自动执行并沉淀版本</div></div><div class="toolbar-group"><el-select v-model="selectedMonth" style="width:130px"><el-option v-for="month in options?.dimensions.months" :key="month" :label="month" :value="month" /></el-select><el-button :icon="Refresh" @click="load">刷新</el-button><el-button type="primary" :icon="Plus" @click="openDialog()">新建策略</el-button></div></div>
    <div class="strategy-summary"><div class="panel"><small>策略总数</small><strong>{{ strategies.length }}</strong></div><div class="panel"><small>运行中</small><strong>{{ enabledCount }}</strong></div><div class="panel"><small>规则数量</small><strong>{{ ruleCount }}</strong></div><div class="panel"><small>执行月份</small><strong>{{ selectedMonth || '暂无数据' }}</strong></div></div>
    <div class="panel strategy-table"><el-table :data="strategies" stripe>
      <el-table-column label="策略" min-width="250"><template #default="{row}"><b>{{ row.name }}</b><div class="row-sub">V{{ row.version || 1 }} · {{ row.strategy_code === 'new_product_35d' ? '新品35天分级' : row.strategy_code === 'mature_product_30d' ? '老品近30天分级' : (row.strategy_type_label || '通用规则') }}</div></template></el-table-column>
      <el-table-column label="商品范围" min-width="210"><template #default="{row}">{{ row.organization || '全部组织' }}<div class="row-sub">{{ [row.platform,row.shop,row.category_path].filter(Boolean).join(' / ') || '全部平台、店铺、品类' }}</div></template></el-table-column>
      <el-table-column label="预警规则" min-width="260"><template #default="{row}"><el-tag v-for="rule in row.rules.slice(0,3)" :key="rule.id" size="small" effect="plain" style="margin:2px">{{ rule.name }}</el-tag><span v-if="row.rules.length>3" class="row-sub">+{{ row.rules.length-3 }}</span></template></el-table-column>
      <el-table-column label="播报" width="145"><template #default="{row}">{{ row.agent_provider_name || row.report_mode_label }}</template></el-table-column>
      <el-table-column label="自动执行" width="130"><template #default="{row}"><el-switch v-model="row.enabled" @change="toggle(row)" /><div class="row-sub">{{ row.schedule_enabled?`${String(row.schedule_hour).padStart(2,'0')}:20`:'仅手动' }}</div></template></el-table-column>
      <el-table-column label="上次运行" min-width="165"><template #default="{row}">{{ formatTime(row.last_run_at) }}<div v-if="row.last_run_summary" class="row-sub">扫描 {{ row.last_run_summary.scanned_products||0 }} · 预警 {{ row.last_run_summary.alerts||0 }}</div></template></el-table-column>
      <el-table-column label="操作" width="200" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openDialog(row)">编辑</el-button><el-button link type="success" :icon="VideoPlay" @click="run(row)">立即运行</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column>
    </el-table><el-empty v-if="!strategies.length" description="先创建一条新品或老品策略" /></div>

    <el-dialog v-model="dialogVisible" :title="form.id?'编辑运营策略':'新建运营策略'" width="min(1040px,96vw)" top="4vh">
      <el-form label-position="top">
        <div class="form-grid four"><el-form-item label="策略名称"><el-input v-model="form.name" placeholder="例如：新品35天分级运营策略" /></el-form-item><el-form-item label="策略模板"><el-select v-model="form.strategy_code" class="full-width" @change="applyTemplate"><el-option label="通用规则" value="standard" /><el-option label="新品35天分级策略" value="new_product_35d" /><el-option label="老品近30天分级策略" value="mature_product_30d" /></el-select></el-form-item><el-form-item label="商品阶段"><el-select v-model="form.strategy_type" class="full-width"><el-option label="新品策略" value="new_product" /><el-option label="老品策略" value="mature_product" /><el-option label="全量商品策略" value="all_product" /></el-select></el-form-item><el-form-item label="新品周期"><el-input-number v-model="form.new_product_days" :min="1" :max="365" class="full-width" /><div class="form-help">新品创建时间35天内；第36天自动归为老品</div></el-form-item></div>
        <el-form-item label="策略说明"><el-input v-model="form.description" type="textarea" :rows="2" placeholder="说明业务目标、适用场景和验收口径" /></el-form-item>
        <div class="scope-title">商品筛选范围</div><div class="form-grid four"><el-form-item label="组织"><el-select v-model="form.organization" clearable class="full-width"><el-option v-for="item in options?.dimensions.organizations" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="平台"><el-select v-model="form.platform" clearable allow-create filterable class="full-width"><el-option v-for="item in options?.dimensions.platforms" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="店铺"><el-select v-model="form.shop" clearable allow-create filterable class="full-width"><el-option v-for="item in options?.dimensions.shops" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="品类"><el-select v-model="form.category_path" clearable allow-create filterable class="full-width"><el-option v-for="item in options?.dimensions.categories" :key="item" :label="item" :value="item" /></el-select></el-form-item></div>
        <div class="scope-title rule-heading"><span>预警规则</span><el-button size="small" :icon="Plus" @click="addRule">添加规则</el-button></div>
        <div v-if="form.strategy_code !== 'standard'" class="strategy-hint"><el-alert v-if="form.strategy_code === 'new_product_35d'" title="新品口径：创建时间35天内为新品；第36天转老品。第1周不评估，第35天结束按累计销量确定 A/B/C/D 类。" type="info" :closable="false" /><el-alert v-else title="老品口径：创建时间超过35天为老品；按最近30天销量分 A/B/C/D/E 类，再结合转化率判断上等马（≥3%）、中等马（2-3%）、下等马（<2%）。" type="info" :closable="false" /></div>
        <div v-for="(rule,index) in form.rules" :key="index" class="rule-card"><div class="rule-index">规则 {{ index+1 }} <span v-if="rule.stage || rule.product_grade || rule.conversion_band" class="rule-context">{{ stages.find(item => item[0] === rule.stage)?.[1] || '' }} {{ rule.product_grade ? `${rule.product_grade}类` : '' }} {{ conversionBands.find(item => item[0] === rule.conversion_band)?.[1] || '' }}</span></div><div class="rule-fields"><el-input v-model="rule.name" placeholder="规则名称，如：新品成交不足" /><el-select v-model="rule.metric"><el-option v-for="item in metrics" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select><el-select v-model="rule.operator"><el-option v-for="item in operators" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select><el-input-number v-model="rule.threshold as number" :controls="false" placeholder="阈值" /><el-input-number v-if="rule.operator==='between'" v-model="rule.threshold_max as number" :controls="false" placeholder="上限" /><el-select v-model="rule.level"><el-option label="提示" value="info" /><el-option label="警告" value="warning" /><el-option label="严重" value="critical" /></el-select><el-button :icon="Delete" circle plain type="danger" :disabled="form.rules.length===1" @click="removeRule(index)" /></div><div class="rule-fields rule-context-fields"><el-select v-model="rule.stage" placeholder="评估阶段" clearable><el-option v-for="item in stages" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select><el-select v-model="rule.product_grade" placeholder="商品等级" clearable><el-option v-for="item in grades" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select><el-select v-model="rule.conversion_band" placeholder="转化带" clearable><el-option v-for="item in conversionBands" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select><el-input-number v-model="rule.weekly_threshold as number" :controls="false" placeholder="周阈值" /><span class="field-help">周销量目标（新品规则适用）</span></div><div class="rule-notes"><el-input v-model="rule.message_template" placeholder="预警标题模板（可选）：{product} 的 {metric} 为 {value}" /><el-input v-model="rule.suggestion" placeholder="命中后的运营建议" /></div></div>
        <div class="scope-title">执行与播报</div><div class="execution-row"><el-switch v-model="form.enabled" active-text="启用策略" /><el-switch v-model="form.schedule_enabled" active-text="每日自动执行" /><el-select v-model="form.schedule_hour" style="width:130px"><el-option v-for="hour in 24" :key="hour-1" :label="`${String(hour-1).padStart(2,'0')}:20`" :value="hour-1" /></el-select><el-radio-group v-model="form.report_mode"><el-radio-button value="system">系统播报</el-radio-button><el-radio-button value="agent">智能体播报</el-radio-button></el-radio-group><el-select v-if="form.report_mode==='agent'" v-model="form.agent_provider" placeholder="选择智能体" style="width:220px"><el-option v-for="agent in options?.agents" :key="agent.id" :label="`${agent.name} · ${agent.model}`" :value="agent.id" /></el-select></div>
      </el-form><template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存策略并启用规则</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.strategy-page{max-width:1600px;margin:auto}.strategy-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.strategy-summary .panel{display:grid;gap:8px}.strategy-summary small{color:var(--app-text-muted)}.strategy-summary strong{font-size:23px}.strategy-table{padding:0;overflow:hidden}.form-grid{display:grid;gap:14px}.form-grid.three{grid-template-columns:2fr 1fr 1fr}.form-grid.four{grid-template-columns:repeat(4,1fr)}.form-help{font-size:11px;color:var(--app-text-muted);margin-top:5px}.scope-title{font-weight:650;margin:4px 0 12px}.rule-heading{display:flex;align-items:center;justify-content:space-between}.rule-card{border:1px solid var(--app-border);background:var(--app-surface-raised);border-radius:10px;padding:12px;margin-bottom:10px}.rule-index{font-size:12px;color:var(--app-text-muted);margin-bottom:9px}.rule-fields{display:grid;grid-template-columns:1.4fr 1fr .8fr .8fr .8fr auto;gap:8px}.rule-context-fields{margin-top:8px;grid-template-columns:1.4fr .8fr 1.1fr .8fr 1fr}.rule-context{margin-left:12px;color:var(--el-color-primary)}.field-help{align-self:center;color:var(--app-text-muted);font-size:11px}.strategy-hint{margin-bottom:14px}.rule-notes{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}.execution-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px;background:var(--app-surface-raised);border:1px solid var(--app-border);border-radius:10px}@media(max-width:1000px){.strategy-summary{grid-template-columns:1fr 1fr}.form-grid.three,.form-grid.four{grid-template-columns:1fr 1fr}.rule-fields{grid-template-columns:1fr 1fr 1fr}.rule-notes{grid-template-columns:1fr}}@media(max-width:600px){.strategy-summary,.form-grid.three,.form-grid.four{grid-template-columns:1fr}.rule-fields{grid-template-columns:1fr 1fr}}
</style>

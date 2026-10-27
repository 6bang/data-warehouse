<script setup lang="ts">
import { Connection, CopyDocument, Key, Link, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import http from '@/api/http'
import type { AIProviderConfig, FeishuConfig, IntegrationEvent, MCPAccessToken, MCPServerConfig, Paginated } from '@/api/types'

const loading = ref(false)
const activeTab = ref('feishu')
const summary = ref<any>({})
const feishu = reactive<FeishuConfig>({ name: '飞书经营数据', app_id: '', app_secret: '', has_app_secret: false, allowed_tenant_keys: '', default_base_url: '', enabled: false, connection_status: 'untested', connection_status_label: '未测试', last_tested_at: null, last_error: '' })
const providers = ref<AIProviderConfig[]>([])
const mcpServers = ref<MCPServerConfig[]>([])
const mcpTokens = ref<MCPAccessToken[]>([])
const events = ref<IntegrationEvent[]>([])
const providerDialog = ref(false)
const mcpDialog = ref(false)
const mcpTokenDialog = ref(false)
const issuedMcpToken = ref('')
const editingMcpTokenId = ref<number | undefined>()
type MCPTokenForm = { name: string; agent_name: string; agent_platform: string; agent_id: string; allowed_tools: string[]; permission_codes: string[]; allowed_shops_text: string; expires_at: string; review_note: string }
const mcpTokenForm = reactive<MCPTokenForm>({ name: '飞书经营智能体', agent_name: '飞书经营智能体', agent_platform: 'feishu', agent_id: '', allowed_tools: ['query_realtime_metrics', 'query_monthly_metrics'], permission_codes: ['realtime.view', 'monthly.view'], allowed_shops_text: '', expires_at: '', review_note: '' })
const mcpPermissionGroups = [
  { label: '数据权限', items: [{ code: 'realtime.view', label: '查看实时经营数据' }, { code: 'monthly.view', label: '查看月度经营数据' }, { code: 'dimensions.view', label: '查看组织与数据维度' }] },
  { label: '自动化权限', items: [{ code: 'analysis.run', label: '发起 AI 分析' }, { code: 'tasks.create', label: '创建运营任务' }, { code: 'sync.request', label: '请求数据刷新' }] },
  { label: '其他功能权限', items: [{ code: 'export.data', label: '导出经营数据' }] },
]
const providerForm = reactive<AIProviderConfig>({ name: '示例模型服务', provider: 'custom', api_base_url: 'https://example.invalid/v1', model: 'example-model', api_key: '', has_api_key: false, enabled: false, is_default: true, connection_status: 'untested', last_tested_at: null, last_error: '' })
const mcpForm = reactive<MCPServerConfig>({ name: '', endpoint_url: '', auth_type: 'none', auth_token: '', has_auth_token: false, enabled: false, agent_query_enabled: false, data_sync_enabled: false, organization_name: '', schedule_enabled: false, schedule_interval_minutes: 120, next_scheduled_at: null, last_synced_at: null, last_sync_attempted_at: null, consecutive_sync_failures: 0, sync_in_progress: false, sync_started_at: null, allow_private_network: false, allowed_tools: [], discovered_tools: [], protocol_version: '2025-06-18', connection_status: 'untested', last_tested_at: null, last_error: '' })
const statusType = (status: string) => status === 'connected' ? 'success' : status === 'error' ? 'danger' : 'info'
const activeProvider = computed(() => providers.value.find(item => item.is_default && item.enabled))
const route = useRoute()
const mcpEndpoint = computed(() => route.meta.demo ? 'https://example.invalid/mcp/NOT-A-LIVE-ENDPOINT' : `${window.location.origin}/api/v1/mcp/business/`)
const agentPrompt = `你是数据云仓经营分析智能体。\n\n当用户询问今日经营情况、实时销售额、订单、访客、广告费或小时趋势时，调用 query_realtime_metrics。\n当用户询问月度经营数据、店铺排名、商品经营表现或人员经营数据时，调用 query_monthly_metrics。\n当用户询问可用企业、月份、店铺、平台或品类时，调用 list_business_dimensions。\n\n默认使用已同步数据；只有用户明确要求“立即刷新”或“重新采集”时，才将 force_refresh 设置为 true。\n不得询问、展示或传播上游数据源账号、密码、Bearer Token 或 MCP 密钥。所有结论必须标注数据时间；数据源不可用时明确说明，不得编造数据。`
const mcpSetupText = computed(() => `${route.meta.demo ? '【演示样例，不可用于接入；密钥无效】\n' : ''}【数据云仓 MCP 接入】\n类型：Streamable HTTP\n地址：${mcpEndpoint.value}\n请求头：Authorization: Bearer ${issuedMcpToken.value}\n\n【飞书智能体提示词】\n${agentPrompt}`)

function errorText(error: any) {
  const data = error.response?.data
  const detail = data?.detail || data?.message || data?.error?.detail || data?.error || data
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const value = Object.values(detail)[0]
    return Array.isArray(value) ? String(value[0]) : String(value || '')
  }
  return '操作失败'
}

async function loadAll() {
  loading.value = true
  try {
    const [summaryRes, feishuRes, aiRes, mcpRes, tokenRes, eventsRes] = await Promise.all([
      http.get('/configuration/summary/'), http.get<Paginated<FeishuConfig>>('/configuration/feishu/'),
      http.get<Paginated<AIProviderConfig>>('/configuration/ai-providers/'), http.get<Paginated<MCPServerConfig>>('/configuration/mcp-servers/'), http.get<Paginated<MCPAccessToken>>('/configuration/mcp-tokens/'),
      http.get<Paginated<IntegrationEvent>>('/configuration/events/', { params: { page_size: 20 } }),
    ])
    summary.value = summaryRes.data
    if (feishuRes.data.results[0]) Object.assign(feishu, feishuRes.data.results[0], { app_secret: '' })
    providers.value = aiRes.data.results
    mcpServers.value = mcpRes.data.results
    mcpTokens.value = tokenRes.data.results
    events.value = eventsRes.data.results
  } finally { loading.value = false }
}

async function saveFeishu() {
  const payload = { name: feishu.name, app_id: feishu.app_id, allowed_tenant_keys: feishu.allowed_tenant_keys, default_base_url: feishu.default_base_url, enabled: feishu.enabled, ...(feishu.app_secret ? { app_secret: feishu.app_secret } : {}) }
  try {
    const { data } = feishu.id ? await http.patch(`/configuration/feishu/${feishu.id}/`, payload) : await http.post('/configuration/feishu/', payload)
    Object.assign(feishu, data, { app_secret: '' }); ElMessage.success('飞书配置已保存'); await loadAll()
  } catch (error) { ElMessage.error(errorText(error)) }
}
async function testFeishu() {
  if (!feishu.id) return ElMessage.warning('请先保存配置')
  try { const { data } = await http.post(`/configuration/feishu/${feishu.id}/test/`); ElMessage.success(data.message); await loadAll() } catch (error) { ElMessage.error(errorText(error)); await loadAll() }
}

function providerPreset(value: string) {
  if (route.meta.demo) {
    Object.assign(providerForm, { name: '演示模型服务', api_base_url: 'https://example.invalid/v1', model: 'demo-model' })
    return
  }
  if (value === 'deepseek') Object.assign(providerForm, { name: 'DeepSeek', api_base_url: 'https://api.deepseek.com', model: 'deepseek-chat' })
  if (value === 'openai') Object.assign(providerForm, { name: 'OpenAI', api_base_url: 'https://api.openai.com/v1', model: 'gpt-5-mini' })
}
function openProvider(item?: AIProviderConfig) {
  Object.assign(providerForm, item ? { ...item, api_key: '' } : { id: undefined, name: '示例模型服务', provider: 'custom', api_base_url: 'https://example.invalid/v1', model: 'example-model', api_key: '', has_api_key: false, enabled: false, is_default: providers.value.length === 0, connection_status: 'untested', last_tested_at: null, last_error: '' })
  providerDialog.value = true
}
async function saveProvider() {
  const payload = { name: providerForm.name, provider: providerForm.provider, api_base_url: providerForm.api_base_url, model: providerForm.model, enabled: providerForm.enabled, is_default: providerForm.is_default, ...(providerForm.api_key ? { api_key: providerForm.api_key } : {}) }
  try {
    if (providerForm.id) await http.patch(`/configuration/ai-providers/${providerForm.id}/`, payload)
    else await http.post('/configuration/ai-providers/', payload)
    providerDialog.value = false; ElMessage.success('模型配置已保存'); await loadAll()
  } catch (error) { ElMessage.error(errorText(error)) }
}
async function testProvider(item: AIProviderConfig) {
  try { const { data } = await http.post(`/configuration/ai-providers/${item.id}/test/`); ElMessage.success(data.message) } catch (error) { ElMessage.error(errorText(error)) } finally { await loadAll() }
}
async function setDefault(item: AIProviderConfig) { await http.post(`/configuration/ai-providers/${item.id}/set_default/`); ElMessage.success('已设为 Agent 默认模型'); await loadAll() }
async function deleteProvider(item: AIProviderConfig) { await ElMessageBox.confirm(`删除模型配置“${item.name}”？`, '确认删除', { type: 'warning' }); await http.delete(`/configuration/ai-providers/${item.id}/`); await loadAll() }

function openMcp(item?: MCPServerConfig) {
  Object.assign(mcpForm, item ? { ...item, auth_token: '', allowed_tools: [...item.allowed_tools], discovered_tools: [...item.discovered_tools] } : { id: undefined, name: '', endpoint_url: '', auth_type: 'none', auth_token: '', has_auth_token: false, enabled: false, agent_query_enabled: false, data_sync_enabled: false, organization_name: '', schedule_enabled: false, schedule_interval_minutes: 120, next_scheduled_at: null, last_synced_at: null, last_sync_attempted_at: null, consecutive_sync_failures: 0, sync_in_progress: false, sync_started_at: null, allow_private_network: false, allowed_tools: [], discovered_tools: [], protocol_version: '2025-06-18', connection_status: 'untested', last_tested_at: null, last_error: '' })
  mcpDialog.value = true
}
async function saveMcp() {
  const payload = { name: mcpForm.name, endpoint_url: mcpForm.endpoint_url, auth_type: mcpForm.auth_type, enabled: mcpForm.enabled, agent_query_enabled: mcpForm.agent_query_enabled, data_sync_enabled: mcpForm.data_sync_enabled, organization_name: mcpForm.organization_name, schedule_enabled: mcpForm.schedule_enabled, schedule_interval_minutes: mcpForm.schedule_interval_minutes, allow_private_network: mcpForm.allow_private_network, allowed_tools: mcpForm.allowed_tools, protocol_version: mcpForm.protocol_version, ...(mcpForm.auth_token ? { auth_token: mcpForm.auth_token } : {}) }
  try {
    if (mcpForm.id) await http.patch(`/configuration/mcp-servers/${mcpForm.id}/`, payload)
    else await http.post('/configuration/mcp-servers/', payload)
    mcpDialog.value = false; ElMessage.success('MCP 服务已保存'); await loadAll()
  } catch (error) { ElMessage.error(errorText(error)) }
}
async function discoverMcp(item: MCPServerConfig) {
  try { const { data } = await http.post(`/configuration/mcp-servers/${item.id}/discover/`); ElMessage.success(data.message) } catch (error) { ElMessage.error(errorText(error)) } finally { await loadAll() }
}
async function deleteMcp(item: MCPServerConfig) { await ElMessageBox.confirm(`删除 MCP 服务“${item.name}”？`, '确认删除', { type: 'warning' }); await http.delete(`/configuration/mcp-servers/${item.id}/`); await loadAll() }
function openMcpToken(item?: MCPAccessToken) {
  editingMcpTokenId.value = item?.id
  Object.assign(mcpTokenForm, item ? {
    name: item.name, agent_name: item.agent_name || item.name, agent_platform: item.agent_platform || 'feishu', agent_id: item.agent_id || '',
    allowed_tools: [...item.allowed_tools], permission_codes: [...(item.permission_codes || [])], allowed_shops_text: item.allowed_shops.join(','),
    expires_at: item.expires_at ? new Date(item.expires_at).toISOString().slice(0, 16).replace('T', ' ') : '', review_note: item.review_note || '',
  } : { name: '飞书经营智能体', agent_name: '飞书经营智能体', agent_platform: 'feishu', agent_id: '', allowed_tools: ['query_realtime_metrics', 'query_monthly_metrics'], permission_codes: ['realtime.view', 'monthly.view'], allowed_shops_text: '', expires_at: '', review_note: '' })
  issuedMcpToken.value = ''
  mcpTokenDialog.value = true
}
async function createMcpToken() {
  try {
    const payload = {
      name: mcpTokenForm.name,
      agent_name: mcpTokenForm.agent_name,
      agent_platform: mcpTokenForm.agent_platform,
      agent_id: mcpTokenForm.agent_id,
      allowed_tools: mcpTokenForm.allowed_tools,
      permission_codes: mcpTokenForm.permission_codes,
      allowed_shops: mcpTokenForm.allowed_shops_text.split(',').map(item => item.trim()).filter(Boolean),
      ...(mcpTokenForm.expires_at ? { expires_at: new Date(mcpTokenForm.expires_at).toISOString() } : {}),
    }
    if (editingMcpTokenId.value) {
      await http.patch(`/configuration/mcp-tokens/${editingMcpTokenId.value}/`, payload)
      mcpTokenDialog.value = false
      ElMessage.success('智能体及权限已更新；如需生效请重新审核')
      await loadAll()
      return
    }
    const { data } = await http.post('/configuration/mcp-tokens/', payload)
    issuedMcpToken.value = data.token
    ElMessage.success(route.meta.demo ? '已生成无效演示密钥，仅供体验复制流程' : 'MCP 密钥已生成；请立即复制，关闭后不再显示明文')
    await loadAll()
  } catch (error) { ElMessage.error(errorText(error)) }
}
async function copyMcpToken() {
  if (!issuedMcpToken.value) return
  await navigator.clipboard.writeText(issuedMcpToken.value)
  ElMessage.success('密钥已复制')
}
async function copyAgentPrompt() {
  await navigator.clipboard.writeText(agentPrompt)
  ElMessage.success('智能体提示词已复制')
}
async function copyMcpSetup() {
  if (!issuedMcpToken.value) return
  await navigator.clipboard.writeText(mcpSetupText.value)
  ElMessage.success(route.meta.demo ? '已复制演示样例；地址与密钥无效，不能连接真实服务' : 'MCP 地址、请求头和提示词已复制，可直接粘贴到飞书智能体')
}
async function disableMcpToken(item: MCPAccessToken) {
  await ElMessageBox.confirm(`停用密钥“${item.name}”？停用后飞书智能体将立即无法查询。`, '确认停用', { type: 'warning' })
  await http.patch(`/configuration/mcp-tokens/${item.id}/`, { enabled: false })
  await loadAll()
}
async function reviewMcpToken(item: MCPAccessToken, decision: 'pending' | 'approved' | 'rejected') {
  if (decision === 'rejected') await ElMessageBox.confirm(`驳回“${item.name}”的 MCP 接入申请？驳回后密钥会立即停用。`, '确认驳回', { type: 'warning' })
  try {
    await http.post(`/configuration/mcp-tokens/${item.id}/review/`, { approval_status: decision })
    ElMessage.success(route.meta.demo ? '模拟审核已更新；演示密钥始终无效' : decision === 'approved' ? '审核已通过，密钥现在可以调用' : decision === 'rejected' ? '已驳回并停用密钥' : '已退回待审核')
    await loadAll()
  } catch (error) { ElMessage.error(errorText(error)) }
}
function formatTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚未测试' }
function intervalLabel(minutes: number) { return ({ 5: '每 5 分钟', 30: '每 30 分钟', 60: '每 1 小时', 120: '每 2 小时', 360: '每 6 小时', 1440: '每天' } as Record<number, string>)[minutes] || `每 ${minutes} 分钟` }

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading" class="page config-page">
    <div class="page-toolbar"><div><div class="month-title">系统配置</div><div class="month-subtitle">{{ route.meta.demo ? '演示配置仅在当前会话生效；不会连接服务，请勿输入真实密钥' : '连接数据、模型与智能体工具；所有密钥仅在后端加密保存' }}</div></div><el-button :icon="Refresh" @click="loadAll">刷新状态</el-button></div>
    <div class="config-overview">
      <div class="panel status-card"><el-icon><Link /></el-icon><div><span>飞书连接</span><strong>{{ summary.feishu?.connection_status_label || '未配置' }}</strong></div></div>
      <div class="panel status-card"><el-icon><Refresh /></el-icon><div><span>经营数据同步</span><strong>{{ summary.mcp?.data_sync_enabled ? '实时数据服务已连接' : '未配置' }}</strong></div></div>
      <div class="panel status-card"><el-icon><Key /></el-icon><div><span>Agent 默认模型</span><strong>{{ activeProvider?.name || '规则引擎' }}</strong></div></div>
      <div class="panel status-card"><el-icon><Connection /></el-icon><div><span>MCP 查询服务</span><strong>{{ summary.mcp?.agent_enabled || 0 }} 个已开放</strong></div></div>
    </div>
    <div class="panel config-panel">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="飞书接入" name="feishu">
          <div class="tab-header"><div><h3>飞书自建应用</h3><p>使用 App ID / App Secret 获取 tenant_access_token，数据同步将优先走 OpenAPI。</p></div><el-tag :type="statusType(feishu.connection_status)">{{ feishu.connection_status_label }}</el-tag></div>
          <el-form label-position="top" class="config-form"><div class="form-grid"><el-form-item label="配置名称"><el-input v-model="feishu.name" /></el-form-item><el-form-item label="App ID"><el-input v-model="feishu.app_id" placeholder="cli_xxxxxxxxx" /></el-form-item></div><el-form-item label="App Secret"><el-input v-model="feishu.app_secret" type="password" show-password :placeholder="feishu.has_app_secret?'已保存；留空表示不修改':'请输入 App Secret'" /></el-form-item><el-form-item label="允许登录的企业 Tenant Key"><el-input v-model="feishu.allowed_tenant_keys" placeholder="tenant_xxx；多个企业用逗号分隔" /><div class="field-help">用于限制飞书登录企业。可在飞书开发者后台应用凭证或用户信息中确认；留空时使用服务器环境变量配置。</div></el-form-item><el-form-item label="默认多维表格 Base 链接"><el-input v-model="feishu.default_base_url" placeholder="https://xxx.feishu.cn/base/...?table=tbl..." /></el-form-item><el-switch v-model="feishu.enabled" active-text="启用飞书 OpenAPI 连接" /><div v-if="feishu.last_error" class="error-note">{{ feishu.last_error }}</div><div class="form-actions"><el-button type="primary" @click="saveFeishu">保存配置</el-button><el-button :icon="Connection" @click="testFeishu">测试连接</el-button><span>上次测试：{{ formatTime(feishu.last_tested_at) }}</span></div></el-form>
        </el-tab-pane>
        <el-tab-pane label="模型 API" name="ai">
          <div class="tab-header"><div><h3>模型服务</h3><p>兼容 DeepSeek、OpenAI 及其他 Chat Completions API；默认模型供经营分析 Agent 使用。</p></div><el-button type="primary" :icon="Plus" @click="openProvider()">添加模型</el-button></div>
          <el-table :data="providers" stripe><el-table-column prop="name" label="名称" min-width="130" /><el-table-column prop="provider_label" label="类型" width="130" /><el-table-column prop="model" label="模型" min-width="150" /><el-table-column label="密钥" width="90"><template #default="{row}"><el-tag :type="row.has_api_key?'success':'warning'">{{ row.has_api_key?'已保存':'未设置' }}</el-tag></template></el-table-column><el-table-column label="连接" width="105"><template #default="{row}"><el-tag :type="statusType(row.connection_status)">{{ row.connection_status_label }}</el-tag></template></el-table-column><el-table-column label="状态" width="120"><template #default="{row}"><el-tag v-if="row.is_default" type="primary">Agent 默认</el-tag><span v-else>{{ row.enabled?'已启用':'已停用' }}</span></template></el-table-column><el-table-column label="操作" width="255" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openProvider(row)">编辑</el-button><el-button link type="primary" @click="testProvider(row)">测试</el-button><el-button v-if="!row.is_default" link type="success" @click="setDefault(row)">设为默认</el-button><el-button link type="danger" @click="deleteProvider(row)">删除</el-button></template></el-table-column></el-table>
        </el-tab-pane>
        <el-tab-pane label="MCP 服务" name="mcp">
          <div class="tab-header"><div><h3>MCP 工具注册</h3><p>仅管理员勾选的工具会开放给 Agent。请只授权查询类工具，写操作仍需人工确认。</p></div><el-button type="primary" :icon="Plus" @click="openMcp()">添加 MCP</el-button></div>
          <el-alert type="warning" :closable="false" title="安全边界：MCP 服务默认关闭；必须连接成功、选择工具白名单并启用“允许 Agent 查询”后才会参与分析。" style="margin-bottom:16px" />
          <el-table :data="mcpServers" stripe>
            <el-table-column prop="name" label="服务" min-width="150" />
            <el-table-column prop="endpoint_url" label="Streamable HTTP 地址" min-width="230" show-overflow-tooltip />
            <el-table-column label="连接" width="105"><template #default="{row}"><el-tag :type="statusType(row.connection_status)">{{ row.sync_in_progress ? '同步中' : row.connection_status_label }}</el-tag></template></el-table-column>
            <el-table-column label="工具" width="90"><template #default="{row}">{{ row.allowed_tools.length }} / {{ row.discovered_tools.length }}</template></el-table-column>
            <el-table-column label="自动同步" min-width="170"><template #default="{row}"><div class="sync-status"><el-tag :type="row.schedule_enabled?'success':'info'">{{ row.schedule_enabled ? intervalLabel(row.schedule_interval_minutes) : '未开启' }}</el-tag><small v-if="row.schedule_enabled">下次：{{ formatTime(row.next_scheduled_at) }}</small><small v-if="row.consecutive_sync_failures">连续失败 {{ row.consecutive_sync_failures }} 次</small></div></template></el-table-column>
            <el-table-column label="Agent" width="110"><template #default="{row}"><el-tag :type="row.agent_query_enabled?'success':'info'">{{ row.agent_query_enabled?'允许查询':'未开放' }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="220" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openMcp(row)">编辑</el-button><el-button link type="primary" @click="discoverMcp(row)">发现工具</el-button><el-button link type="danger" @click="deleteMcp(row)">删除</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="智能体密钥" name="mcp-tokens">
          <div class="tab-header"><div><h3>飞书智能体业务 MCP 密钥</h3><p>生成接入包后先进入“待审核”，管理员可以编辑绑定的智能体、店铺范围和权限；审核通过后才允许调用。</p></div><el-button type="primary" :icon="Plus" @click="openMcpToken()">生成接入包</el-button></div>
          <el-alert type="warning" :closable="false" title="密钥只显示一次；未审核前密钥不能调用 MCP。请勿把上游数据源的 Bearer Token 粘贴给飞书智能体。" style="margin-bottom:16px" />
          <el-table :data="mcpTokens" stripe>
            <el-table-column prop="name" label="名称" min-width="170" />
            <el-table-column label="绑定智能体" min-width="170"><template #default="{row}">{{ row.agent_name || '未设置' }}<small class="table-subtext">{{ row.agent_platform }}{{ row.agent_id ? ` · ${row.agent_id}` : '' }}</small></template></el-table-column>
            <el-table-column prop="token_prefix" label="密钥前缀" width="150" />
            <el-table-column prop="owner_name" label="归属账号" width="130" />
            <el-table-column label="工具" min-width="230"><template #default="{row}">{{ row.allowed_tools.join('、') }}</template></el-table-column>
            <el-table-column label="权限" min-width="180"><template #default="{row}">{{ row.permission_codes?.join('、') || '未设置' }}</template></el-table-column>
            <el-table-column label="店铺范围" min-width="150"><template #default="{row}">{{ row.allowed_shops.length ? row.allowed_shops.join('、') : '沿用账号范围' }}</template></el-table-column>
            <el-table-column label="审核 / 状态" width="150"><template #default="{row}"><el-tag :type="row.approval_status === 'approved' ? 'success' : row.approval_status === 'rejected' ? 'danger' : 'warning'">{{ row.approval_status_label || (row.approval_status === 'approved' ? '已通过' : row.approval_status === 'rejected' ? '已驳回' : '待审核') }}</el-tag><small class="table-subtext">{{ row.enabled ? '密钥启用' : '密钥停用' }}</small></template></el-table-column>
            <el-table-column label="最近使用" width="180"><template #default="{row}">{{ formatTime(row.last_used_at) }}</template></el-table-column>
            <el-table-column label="操作" width="250" fixed="right"><template #default="{row}"><el-button link type="primary" @click="openMcpToken(row)">编辑权限</el-button><el-button v-if="row.approval_status === 'pending'" link type="success" @click="reviewMcpToken(row, 'approved')">通过</el-button><el-button v-if="row.approval_status === 'pending'" link type="danger" @click="reviewMcpToken(row, 'rejected')">驳回</el-button><el-button v-if="row.enabled" link type="danger" @click="disableMcpToken(row)">停用</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="调用日志" name="logs">
          <div class="tab-header"><div><h3>连接与 Agent 调用日志</h3><p>记录连接测试、模型分析和 MCP 工具调用，不保存 API Key 或认证 Token。</p></div></div>
          <el-table :data="events" stripe><el-table-column label="时间" width="180"><template #default="{row}">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column prop="integration_type" label="类型" width="100" /><el-table-column prop="action" label="动作" width="150" /><el-table-column label="结果" width="90"><template #default="{row}"><el-tag :type="row.success?'success':'danger'">{{ row.success?'成功':'失败' }}</el-tag></template></el-table-column><el-table-column prop="duration_ms" label="耗时(ms)" width="100" /><el-table-column prop="actor_name" label="操作者" width="110" /><el-table-column label="详情" min-width="240"><template #default="{row}">{{ row.error || JSON.stringify(row.detail) }}</template></el-table-column></el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
    <el-dialog v-model="providerDialog" :title="providerForm.id?'编辑模型':'添加模型'" width="min(620px,92vw)"><el-form label-position="top"><div class="form-grid"><el-form-item label="服务类型"><el-select v-model="providerForm.provider" class="full-width" @change="providerPreset"><el-option label="DeepSeek" value="deepseek" /><el-option label="OpenAI" value="openai" /><el-option label="OpenAI 兼容服务" value="custom" /></el-select></el-form-item><el-form-item label="配置名称"><el-input v-model="providerForm.name" /></el-form-item></div><el-form-item label="API Base URL"><el-input v-model="providerForm.api_base_url" /></el-form-item><el-form-item label="模型名称"><el-input v-model="providerForm.model" /></el-form-item><el-form-item label="API Key"><el-input v-model="providerForm.api_key" type="password" show-password :placeholder="providerForm.has_api_key?'已保存；留空表示不修改':'请输入 API Key'" /></el-form-item><el-checkbox v-model="providerForm.enabled">启用</el-checkbox><el-checkbox v-model="providerForm.is_default">设为 Agent 默认模型</el-checkbox></el-form><template #footer><el-button @click="providerDialog=false">取消</el-button><el-button type="primary" @click="saveProvider">保存</el-button></template></el-dialog>
    <el-dialog v-model="mcpDialog" :title="mcpForm.id?'编辑 MCP 服务':'添加 MCP 服务'" width="min(720px,94vw)">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="服务名称"><el-input v-model="mcpForm.name" /></el-form-item><el-form-item label="协议版本"><el-input v-model="mcpForm.protocol_version" /></el-form-item></div>
        <el-form-item label="Streamable HTTP 地址"><el-input v-model="mcpForm.endpoint_url" placeholder="https://example.invalid/mcp" /></el-form-item>
        <div class="form-grid"><el-form-item label="认证方式"><el-select v-model="mcpForm.auth_type" class="full-width"><el-option label="无认证" value="none" /><el-option label="Bearer Token" value="bearer" /></el-select></el-form-item><el-form-item v-if="mcpForm.auth_type==='bearer'" label="Token"><el-input v-model="mcpForm.auth_token" type="password" show-password :placeholder="mcpForm.has_auth_token?'已保存；留空表示不修改':'请输入 Token'" /></el-form-item></div>
        <el-form-item v-if="mcpForm.data_sync_enabled" label="数据归属企业"><el-input v-model="mcpForm.organization_name" placeholder="例如：示例企业" /></el-form-item>
        <div v-if="mcpForm.data_sync_enabled" class="schedule-row"><el-switch v-model="mcpForm.schedule_enabled" active-text="自动同步" /><el-select v-model="mcpForm.schedule_interval_minutes" :disabled="!mcpForm.schedule_enabled" style="width:170px"><el-option label="每 5 分钟" :value="5" /><el-option label="每 30 分钟" :value="30" /><el-option label="每 1 小时" :value="60" /><el-option label="每 2 小时（推荐）" :value="120" /><el-option label="每 6 小时" :value="360" /><el-option label="每天" :value="1440" /></el-select><span>服务器每 5 分钟检查；失败后自动退避重试，月初回补上月。</span></div>
        <el-form-item v-if="mcpForm.discovered_tools.length" label="允许 Agent 使用的只读工具"><el-checkbox-group v-model="mcpForm.allowed_tools" class="tool-list"><el-checkbox v-for="tool in mcpForm.discovered_tools" :key="tool.name" :value="tool.name"><b>{{ tool.name }}</b><span>{{ tool.description }}</span></el-checkbox></el-checkbox-group></el-form-item>
        <el-checkbox v-model="mcpForm.enabled">启用服务</el-checkbox><el-checkbox v-model="mcpForm.data_sync_enabled">允许经营数据一键同步</el-checkbox><el-checkbox v-model="mcpForm.agent_query_enabled">允许经营分析 Agent 查询</el-checkbox><el-checkbox v-model="mcpForm.allow_private_network">允许连接内网地址（高风险）</el-checkbox>
        <div v-if="mcpForm.last_synced_at || mcpForm.next_scheduled_at" class="form-actions"><span>上次同步：{{ formatTime(mcpForm.last_synced_at) }}</span><span>下次同步：{{ formatTime(mcpForm.next_scheduled_at) }}</span><span v-if="mcpForm.consecutive_sync_failures">连续失败 {{ mcpForm.consecutive_sync_failures }} 次</span></div>
      </el-form>
      <template #footer><el-button @click="mcpDialog=false">取消</el-button><el-button type="primary" @click="saveMcp">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="mcpTokenDialog" :title="editingMcpTokenId ? '编辑智能体 MCP 权限' : '生成飞书智能体 MCP 接入包'" width="min(720px,94vw)">
      <el-form label-position="top">
        <el-form-item label="密钥名称"><el-input v-model="mcpTokenForm.name" placeholder="例如：飞书经营智能体" /></el-form-item>
        <div class="form-grid"><el-form-item label="绑定智能体名称"><el-input v-model="mcpTokenForm.agent_name" placeholder="例如：经营分析助手" /></el-form-item><el-form-item label="智能体平台"><el-select v-model="mcpTokenForm.agent_platform" class="full-width"><el-option label="飞书智能体" value="feishu" /><el-option label="其他 Agent" value="custom" /></el-select></el-form-item></div>
        <el-form-item label="智能体 ID / App ID（可选）"><el-input v-model="mcpTokenForm.agent_id" placeholder="用于审核时确认具体智能体" /></el-form-item>
        <el-form-item label="权限设置"><div class="permission-groups"><div v-for="group in mcpPermissionGroups" :key="group.label" class="permission-group"><b>{{ group.label }}</b><el-checkbox-group v-model="mcpTokenForm.permission_codes"><el-checkbox v-for="item in group.items" :key="item.code" :label="item.code">{{ item.label }}</el-checkbox></el-checkbox-group></div></div></el-form-item>
        <el-form-item label="允许调用的工具"><el-checkbox-group v-model="mcpTokenForm.allowed_tools"><el-checkbox label="query_realtime_metrics">实时经营指标</el-checkbox><el-checkbox label="query_monthly_metrics">月度经营指标</el-checkbox><el-checkbox label="list_business_dimensions">组织与月份维度</el-checkbox></el-checkbox-group></el-form-item>
        <el-form-item label="店铺范围（可选）"><el-input v-model="mcpTokenForm.allowed_shops_text" placeholder="留空沿用归属账号权限；多个店铺用逗号分隔" /></el-form-item>
        <el-form-item label="过期时间（可选）"><el-input v-model="mcpTokenForm.expires_at" placeholder="例如 2026-12-31 23:59；留空不过期" /></el-form-item>
        <el-form-item v-if="editingMcpTokenId" label="审核备注"><el-input v-model="mcpTokenForm.review_note" type="textarea" :rows="2" placeholder="记录本次权限变更原因" /></el-form-item>
      </el-form>
      <el-alert v-if="issuedMcpToken" type="success" :closable="false" :title="route.meta.demo ? '演示接入包不可用于接入；示例地址和密钥均无效。' : '接入包已生成。密钥只显示这一次；复制后到飞书智能体的 MCP 配置中粘贴。'" style="margin-top:10px">
        <div class="setup-field"><span>MCP 地址</span><code>{{ mcpEndpoint }}</code></div>
        <div class="setup-field"><span>Authorization</span><code>{{ `Bearer ${issuedMcpToken}` }}</code><el-button link type="primary" @click="copyMcpToken">复制密钥</el-button></div>
        <div class="setup-actions"><el-button type="primary" :icon="CopyDocument" @click="copyMcpSetup">一键复制 MCP 配置 + 提示词</el-button><el-button @click="copyAgentPrompt">只复制提示词</el-button></div>
        <details class="prompt-preview"><summary>查看将发送给智能体的提示词</summary><pre>{{ agentPrompt }}</pre></details>
      </el-alert>
      <template #footer><el-button @click="mcpTokenDialog=false">关闭</el-button><el-button v-if="!issuedMcpToken" type="primary" @click="createMcpToken">{{ editingMcpTokenId ? '保存权限' : '生成接入包' }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.config-page{max-width:1500px;margin:0 auto}.config-overview{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}.status-card{display:flex;align-items:center;gap:14px}.status-card>.el-icon{width:42px;height:42px;border-radius:11px;background:#28244d;color:#9487ff;font-size:21px}.status-card span,.status-card strong{display:block}.status-card span{font-size:12px;color:#8e929d}.status-card strong{margin-top:6px;font-size:17px}.config-panel{padding:18px 20px}.tab-header{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin:4px 0 18px}.tab-header h3{margin:0 0 7px}.tab-header h3{margin:0 0 7px}.tab-header p{margin:0;color:#8e929d;line-height:1.5}.config-form{max-width:920px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.field-help{font-size:12px;color:#8e929d;line-height:1.5;margin-top:6px}.form-actions{display:flex;align-items:center;gap:12px;margin-top:20px;color:#818692;font-size:13px}.schedule-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;border:1px solid #30323a;background:#191b20;border-radius:9px;padding:14px;margin-top:12px}.schedule-row span{font-size:12px;color:#818692}.error-note{color:#ff7474;margin-top:12px}.tool-list{display:grid;gap:8px;width:100%}.tool-list :deep(.el-checkbox){height:auto;align-items:flex-start;padding:10px;border:1px solid #30323a;border-radius:8px;margin:0}.tool-list b,.tool-list span{display:block}.tool-list span{color:#8e929d;font-size:12px;margin-top:4px;white-space:normal}.sync-status{display:grid;gap:4px}.sync-status small{color:#818692;white-space:nowrap}.issued-token{display:flex;align-items:center;gap:10px;margin-top:10px}.issued-token code{display:block;flex:1;overflow:auto;padding:8px;background:#15171c;border-radius:6px;white-space:nowrap}@media(max-width:1050px){.config-overview{grid-template-columns:repeat(2,1fr)}}@media(max-width:800px){.config-overview,.form-grid{grid-template-columns:1fr}.form-actions{align-items:flex-start;flex-wrap:wrap}}
.setup-field{display:flex;align-items:center;gap:8px;margin-top:10px}.setup-field span{min-width:115px;color:var(--app-text-secondary);font-size:12px}.setup-field code{flex:1;overflow:auto;padding:7px 9px;background:var(--app-bg);border-radius:6px;white-space:nowrap}.setup-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.prompt-preview{margin-top:12px}.prompt-preview summary{cursor:pointer;color:var(--app-text-secondary);font-size:12px}.prompt-preview pre{white-space:pre-wrap;line-height:1.6;color:var(--app-text-secondary);font-size:12px;background:var(--app-bg);border-radius:6px;padding:10px;margin-top:8px}@media(max-width:800px){.setup-field{align-items:flex-start;flex-direction:column}.setup-field span{min-width:auto}.setup-field code{width:100%}}
.table-subtext{display:block;color:var(--app-text-secondary);font-size:11px;margin-top:4px}.permission-groups{display:grid;gap:12px;width:100%}.permission-group{border:1px solid var(--app-border);border-radius:8px;padding:10px 12px}.permission-group b{display:block;margin-bottom:8px}.permission-group .el-checkbox{margin-right:16px;margin-bottom:4px}
</style>

<script setup lang="ts">
import { Delete, Plus, Refresh, UserFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import http from '@/api/http'
import type { AccessRole, Account, Paginated, PermissionGroup, PermissionModule } from '@/api/types'

const activeTab = ref<'accounts' | 'roles'>('accounts')
const loading = ref(false)
const accounts = ref<Account[]>([])
const total = ref(0)
const query = reactive({ approval_status: 'pending', search: '', page: 1, page_size: 20 })
const pendingCount = computed(() => accounts.value.filter(item => item.approval_status === 'pending').length)
const roles = ref<AccessRole[]>([])
const permissionGroups = ref<PermissionGroup[]>([])
const shops = ref<string[]>([])
const selectedRoleId = ref<number | null>(null)
const roleSaving = ref(false)
const roleForm = reactive({ id: null as number | null, name: '', code: '', description: '', data_scope: 'assigned' as 'all' | 'assigned', permissions: [] as string[], is_active: true, sort_order: 100, role_type: 'custom' as 'system' | 'custom' })

const reviewVisible = ref(false)
const reviewSubmitting = ref(false)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewingAccount = ref<Account | null>(null)
const reviewForm = reactive({ access_role: null as number | null, allowed_shops: [] as string[], note: '' })
const accessVisible = ref(false)
const accessAccount = ref<Account | null>(null)
const accessForm = reactive({ access_role: null as number | null, allowed_shops: [] as string[] })

const statusTypes: Record<string, 'warning' | 'success' | 'danger'> = { pending: 'warning', approved: 'success', rejected: 'danger' }
const selectedRole = computed(() => roles.value.find(item => item.id === selectedRoleId.value) || null)
const selectedAccessRole = computed(() => roles.value.find(item => item.id === reviewForm.access_role) || null)
const selectedEditAccessRole = computed(() => roles.value.find(item => item.id === accessForm.access_role) || null)
const systemRoles = computed(() => roles.value.filter(item => item.role_type === 'system'))
const customRoles = computed(() => roles.value.filter(item => item.role_type === 'custom'))

async function loadAccounts() {
  loading.value = true
  try {
    const params = { ...query, approval_status: query.approval_status || undefined, search: query.search || undefined }
    const { data } = await http.get<Paginated<Account>>('/accounts/', { params })
    accounts.value = data.results
    total.value = data.count
  } catch { ElMessage.error('用户列表加载失败') } finally { loading.value = false }
}

async function loadAccessControl() {
  try {
    const [roleResponse, catalogResponse] = await Promise.all([
      http.get<Paginated<AccessRole>>('/access-roles/', { params: { page_size: 100 } }),
      http.get<{ permission_groups: PermissionGroup[]; shops: string[] }>('/access-roles/catalog/'),
    ])
    roles.value = roleResponse.data.results
    permissionGroups.value = catalogResponse.data.permission_groups
    shops.value = catalogResponse.data.shops
    if (!selectedRoleId.value && roles.value.length) selectRole(roles.value[0])
    else if (selectedRoleId.value) {
      const current = roles.value.find(item => item.id === selectedRoleId.value)
      if (current) selectRole(current)
    }
  } catch { ElMessage.error('角色权限配置加载失败') }
}

async function refreshAll() { await Promise.all([loadAccounts(), loadAccessControl()]) }

function openReview(account: Account, action: 'approve' | 'reject') {
  reviewingAccount.value = account
  reviewAction.value = action
  const requested = roles.value.find(item => item.code === account.requested_role_code && item.code !== 'owner') || roles.value.find(item => item.code === 'viewer')
  reviewForm.access_role = requested?.id || null
  reviewForm.allowed_shops = [...account.allowed_shops]
  reviewForm.note = ''
  reviewVisible.value = true
}

async function submitReview() {
  const account = reviewingAccount.value
  if (!account) return
  if (reviewAction.value === 'approve' && !reviewForm.access_role) return ElMessage.warning('请选择批准后的角色')
  if (reviewAction.value === 'approve' && selectedAccessRole.value?.data_scope === 'assigned' && !reviewForm.allowed_shops.length) return ElMessage.warning('该角色需要选择至少一个店铺')
  reviewSubmitting.value = true
  try {
    const payload = reviewAction.value === 'approve'
      ? { note: reviewForm.note, access_role: reviewForm.access_role, allowed_shops: reviewForm.allowed_shops }
      : { note: reviewForm.note }
    await http.post(`/accounts/${account.id}/${reviewAction.value}/`, payload)
    ElMessage.success(reviewAction.value === 'approve' ? '用户已批准并分配权限' : '注册申请已拒绝')
    reviewVisible.value = false
    await Promise.all([loadAccounts(), loadAccessControl()])
  } catch { ElMessage.error('审批操作失败') } finally { reviewSubmitting.value = false }
}

function openAccess(account: Account) {
  accessAccount.value = account
  accessForm.access_role = account.access_role_id || roles.value.find(item => item.code === account.role)?.id || null
  accessForm.allowed_shops = [...account.allowed_shops]
  accessVisible.value = true
}

async function saveAccess() {
  if (!accessAccount.value || !accessForm.access_role) return ElMessage.warning('请选择角色')
  if (selectedEditAccessRole.value?.data_scope === 'assigned' && !accessForm.allowed_shops.length) return ElMessage.warning('请选择至少一个店铺')
  try {
    await http.post(`/accounts/${accessAccount.value.id}/update_access/`, accessForm)
    ElMessage.success('账户权限已更新')
    accessVisible.value = false
    await Promise.all([loadAccounts(), loadAccessControl()])
  } catch { ElMessage.error('账户权限更新失败') }
}

function selectRole(role: AccessRole) {
  selectedRoleId.value = role.id
  Object.assign(roleForm, {
    id: role.id, name: role.name, code: role.code, description: role.description,
    data_scope: role.data_scope, permissions: [...role.permissions], is_active: role.is_active,
    sort_order: role.sort_order, role_type: role.role_type,
  })
}

function createRole() {
  selectedRoleId.value = null
  Object.assign(roleForm, {
    id: null, name: '新自定义角色', code: `custom_${Date.now().toString().slice(-8)}`,
    description: '', data_scope: 'assigned', permissions: ['dashboard.view'], is_active: true,
    sort_order: 100, role_type: 'custom',
  })
}

async function saveRole() {
  if (!roleForm.name.trim() || !roleForm.code.trim()) return ElMessage.warning('请填写角色名称和编码')
  roleSaving.value = true
  try {
    const payload = {
      name: roleForm.name, code: roleForm.code, description: roleForm.description,
      data_scope: roleForm.data_scope, permissions: roleForm.permissions,
      is_active: roleForm.is_active, sort_order: roleForm.sort_order,
    }
    const { data } = roleForm.id
      ? await http.patch<AccessRole>(`/access-roles/${roleForm.id}/`, payload)
      : await http.post<AccessRole>('/access-roles/', payload)
    selectedRoleId.value = data.id
    ElMessage.success('角色权限已保存')
    await loadAccessControl()
  } catch { ElMessage.error('角色保存失败，请检查编码是否重复') } finally { roleSaving.value = false }
}

async function deleteRole() {
  const role = selectedRole.value
  if (!role || role.role_type === 'system') return
  try {
    await ElMessageBox.confirm(`确定删除自定义角色“${role.name}”？`, '删除角色', { type: 'warning' })
    await http.delete(`/access-roles/${role.id}/`)
    selectedRoleId.value = null
    ElMessage.success('角色已删除')
    await loadAccessControl()
  } catch (error: unknown) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('角色仍有成员或删除失败')
  }
}

function modulePermissions(module: PermissionModule) { return module.actions.map(item => item.permission) }
function moduleChecked(module: PermissionModule) { return modulePermissions(module).every(code => roleForm.permissions.includes(code)) }
function moduleIndeterminate(module: PermissionModule) {
  const count = modulePermissions(module).filter(code => roleForm.permissions.includes(code)).length
  return count > 0 && count < module.actions.length
}
function toggleModule(module: PermissionModule, checked: boolean) {
  const codes = modulePermissions(module)
  roleForm.permissions = checked
    ? Array.from(new Set([...roleForm.permissions, ...codes]))
    : roleForm.permissions.filter(code => !codes.includes(code))
}
function toggleModuleFromUi(module: PermissionModule, value: string | number | boolean) { toggleModule(module, Boolean(value)) }

function formatTime(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' }

onMounted(() => Promise.all([loadAccounts(), loadAccessControl()]))
</script>

<template>
  <div class="page access-page">
    <div class="page-toolbar">
      <div><div class="month-title">用户与权限</div><div class="month-subtitle">注册审批、角色权限与店铺数据范围统一管理</div></div>
      <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
    </div>

    <el-tabs v-model="activeTab" class="access-tabs">
      <el-tab-pane name="accounts">
        <template #label><span>用户与审批 <el-badge v-if="pendingCount" :value="pendingCount" /></span></template>
        <div class="account-toolbar panel">
          <div><strong>账户访问</strong><span>注册后必须审批；批准时分配角色和店铺范围</span></div>
          <div class="toolbar-group">
            <el-select v-model="query.approval_status" style="width:130px" @change="query.page=1;loadAccounts()">
              <el-option label="全部状态" value="" /><el-option label="待审批" value="pending" /><el-option label="已批准" value="approved" /><el-option label="已拒绝" value="rejected" />
            </el-select>
            <el-input v-model="query.search" clearable placeholder="用户名 / 姓名 / 邮箱" style="width:230px" @keyup.enter="query.page=1;loadAccounts()" />
            <el-button type="primary" @click="query.page=1;loadAccounts()">查询</el-button>
          </div>
        </div>
        <div class="panel table-panel">
          <el-table v-loading="loading" :data="accounts" stripe>
            <el-table-column label="用户" min-width="180"><template #default="{row}"><div class="user-cell"><span class="mini-avatar">{{ row.username.slice(0,1).toUpperCase() }}</span><span><b>{{ row.first_name || row.username }}</b><small>@{{ row.username }}<template v-if="row.department"> · {{ row.department }}</template></small></span></div></template></el-table-column>
            <el-table-column prop="email" label="邮箱" min-width="180"><template #default="{row}">{{ row.email || '—' }}</template></el-table-column>
            <el-table-column label="角色" width="130"><template #default="{row}"><el-tag effect="plain">{{ row.role_name }}</el-tag></template></el-table-column>
            <el-table-column label="数据范围" min-width="170"><template #default="{row}"><span v-if="row.data_scope==='all'">全部店铺</span><span v-else>{{ row.allowed_shops.length ? row.allowed_shops.join('、') : '尚未分配' }}</span></template></el-table-column>
            <el-table-column label="状态" width="105"><template #default="{row}"><el-tag :type="statusTypes[row.approval_status]" effect="dark">{{ row.approval_status_label }}</el-tag></template></el-table-column>
            <el-table-column label="申请信息" min-width="190"><template #default="{row}"><span>{{ formatTime(row.registered_at) }}</span><small v-if="row.registration_reason" class="review-note">{{ row.registration_reason }}</small></template></el-table-column>
            <el-table-column label="操作" width="230" fixed="right"><template #default="{row}">
              <template v-if="row.role!=='owner'">
                <template v-if="row.approval_status==='pending'"><el-button size="small" type="success" plain @click="openReview(row,'approve')">审批</el-button><el-button size="small" type="danger" plain @click="openReview(row,'reject')">拒绝</el-button></template>
                <el-button v-else size="small" type="primary" plain @click="openAccess(row)">设置权限</el-button>
              </template><span v-else class="empty-value">系统所有者</span>
            </template></el-table-column>
          </el-table>
          <div class="pagination"><el-pagination v-model:current-page="query.page" :page-size="query.page_size" :total="total" layout="total, prev, pager, next" @current-change="loadAccounts" /></div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="角色权限" name="roles">
        <div class="permission-layout panel">
          <aside class="role-list">
            <div class="role-list-head"><div><strong>角色</strong><small>系统角色与自定义角色</small></div><el-button circle size="small" type="primary" :icon="Plus" @click="createRole" /></div>
            <div class="role-section-label">系统角色</div>
            <button v-for="role in systemRoles" :key="role.id" :class="{active:selectedRoleId===role.id}" @click="selectRole(role)"><el-icon><UserFilled /></el-icon><span><b>{{ role.name }}</b><small>{{ role.member_count }} 名成员 · {{ role.permission_count }} 项权限</small></span></button>
            <div class="role-section-label">自定义角色</div>
            <button v-for="role in customRoles" :key="role.id" :class="{active:selectedRoleId===role.id}" @click="selectRole(role)"><el-icon><UserFilled /></el-icon><span><b>{{ role.name }}</b><small>{{ role.member_count }} 名成员 · {{ role.permission_count }} 项权限</small></span></button>
            <div v-if="!customRoles.length" class="role-empty">还没有自定义角色</div>
          </aside>

          <section class="role-editor">
            <div class="role-editor-head">
              <div><strong>{{ roleForm.name || '新角色' }}</strong><small>配置功能操作与店铺数据边界；保存后对角色成员生效</small></div>
              <div><el-button v-if="selectedRole?.role_type==='custom'" :icon="Delete" plain type="danger" @click="deleteRole">删除</el-button><el-button type="primary" :loading="roleSaving" @click="saveRole">保存角色</el-button></div>
            </div>
            <div class="role-basic">
              <el-form label-position="top">
                <div class="form-grid-3">
                  <el-form-item label="角色名称"><el-input v-model="roleForm.name" /></el-form-item>
                  <el-form-item label="角色编码"><el-input v-model="roleForm.code" :disabled="roleForm.role_type==='system'" /></el-form-item>
                  <el-form-item label="状态"><el-switch v-model="roleForm.is_active" active-text="启用" inactive-text="停用" :disabled="roleForm.code==='owner'" /></el-form-item>
                </div>
                <el-form-item label="角色说明"><el-input v-model="roleForm.description" /></el-form-item>
                <el-form-item label="数据权限">
                  <el-radio-group v-model="roleForm.data_scope" :disabled="roleForm.code==='owner'">
                    <el-radio-button value="all">全部店铺</el-radio-button><el-radio-button value="assigned">按账户指定店铺</el-radio-button>
                  </el-radio-group>
                  <span class="scope-tip">指定店铺由管理员在用户审批或“设置权限”时分配。</span>
                </el-form-item>
              </el-form>
            </div>
            <div class="permission-title"><strong>功能权限</strong><span>查看、编辑、执行和管理权限分别控制；未勾选的入口会隐藏，接口同时拒绝访问。</span></div>
            <div v-for="group in permissionGroups" :key="group.code" class="permission-group">
              <div class="permission-group-name">{{ group.name }}</div>
              <div v-for="module in group.modules" :key="module.code" class="permission-row">
                <el-checkbox :model-value="moduleChecked(module)" :indeterminate="moduleIndeterminate(module)" :disabled="roleForm.code==='owner'" @change="toggleModuleFromUi(module, $event)">{{ module.name }}</el-checkbox>
                <el-checkbox-group v-model="roleForm.permissions" :disabled="roleForm.code==='owner'">
                  <el-checkbox v-for="action in module.actions" :key="action.permission" :value="action.permission">{{ action.name }}</el-checkbox>
                </el-checkbox-group>
              </div>
            </div>
          </section>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="reviewVisible" :title="reviewAction==='approve'?'批准注册申请':'拒绝注册申请'" width="560px">
      <div v-if="reviewingAccount" class="dialog-user"><span class="mini-avatar">{{ reviewingAccount.username.slice(0,1).toUpperCase() }}</span><div><b>{{ reviewingAccount.first_name || reviewingAccount.username }}</b><small>{{ reviewingAccount.department || '未填写部门' }} · 申请{{ reviewingAccount.requested_role_code==='editor'?'编辑者':'阅读者' }}</small></div></div>
      <el-form label-position="top">
        <template v-if="reviewAction==='approve'">
          <el-form-item label="分配角色"><el-select v-model="reviewForm.access_role" style="width:100%"><el-option v-for="role in roles.filter(item=>item.code!=='owner'&&item.is_active)" :key="role.id" :label="`${role.name} · ${role.description}`" :value="role.id" /></el-select></el-form-item>
          <el-form-item v-if="selectedAccessRole?.data_scope==='assigned'" label="授权店铺"><el-select v-model="reviewForm.allowed_shops" multiple filterable style="width:100%" placeholder="选择可查看的店铺"><el-option v-for="shop in shops" :key="shop" :label="shop" :value="shop" /></el-select></el-form-item>
        </template>
        <el-form-item :label="reviewAction==='approve'?'审批备注（选填）':'拒绝原因'"><el-input v-model="reviewForm.note" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item>
      </el-form>
      <template #footer><el-button @click="reviewVisible=false">取消</el-button><el-button :type="reviewAction==='approve'?'primary':'danger'" :loading="reviewSubmitting" @click="submitReview">{{ reviewAction==='approve'?'批准并授权':'确认拒绝' }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="accessVisible" title="设置账户权限" width="540px">
      <el-form label-position="top">
        <el-form-item label="角色"><el-select v-model="accessForm.access_role" style="width:100%"><el-option v-for="role in roles.filter(item=>item.code!=='owner'&&item.is_active)" :key="role.id" :label="role.name" :value="role.id" /></el-select></el-form-item>
        <el-form-item v-if="selectedEditAccessRole?.data_scope==='assigned'" label="授权店铺"><el-select v-model="accessForm.allowed_shops" multiple filterable style="width:100%"><el-option v-for="shop in shops" :key="shop" :label="shop" :value="shop" /></el-select></el-form-item>
        <div class="access-summary">角色权限 {{ selectedEditAccessRole?.permission_count || 0 }} 项 · 数据范围 {{ selectedEditAccessRole?.data_scope_label || '—' }}</div>
      </el-form>
      <template #footer><el-button @click="accessVisible=false">取消</el-button><el-button type="primary" @click="saveAccess">保存权限</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.access-page{max-width:1600px;margin:0 auto}.access-tabs{--el-tabs-header-height:48px}.account-toolbar{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;margin-bottom:14px}.account-toolbar>div:first-child{display:grid;gap:4px}.account-toolbar span,.role-list-head small,.role-editor-head small{color:var(--app-text-muted);font-size:12px}.table-panel{padding:0;overflow:hidden}.user-cell,.dialog-user{display:flex;align-items:center;gap:10px}.user-cell b,.user-cell small,.dialog-user b,.dialog-user small{display:block}.user-cell small,.dialog-user small{color:var(--app-text-muted);margin-top:3px}.mini-avatar{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;background:color-mix(in srgb,#7367ff 20%,var(--app-surface));color:#9186ff;font-weight:700;flex:0 0 auto}.review-note{display:block;color:var(--app-text-muted);margin-top:4px;line-height:1.4}.pagination{display:flex;justify-content:flex-end;padding:16px 18px}.permission-layout{padding:0;display:grid;grid-template-columns:270px minmax(0,1fr);min-height:690px;overflow:hidden}.role-list{border-right:1px solid var(--app-border);padding:18px 12px;background:color-mix(in srgb,var(--app-surface) 86%,var(--app-bg))}.role-list-head{display:flex;align-items:center;justify-content:space-between;padding:0 8px 14px}.role-list-head>div,.role-editor-head>div:first-child{display:grid;gap:4px}.role-section-label{padding:14px 9px 7px;color:var(--app-text-muted);font-size:11px;letter-spacing:.08em}.role-list>button{width:100%;border:0;background:transparent;color:var(--app-text-secondary);display:flex;align-items:center;gap:10px;padding:11px;border-radius:8px;text-align:left;cursor:pointer}.role-list>button:hover,.role-list>button.active{background:var(--app-hover);color:var(--app-text)}.role-list>button.active{box-shadow:inset 3px 0 #7367ff}.role-list>button span{display:grid;gap:3px}.role-list>button small{color:var(--app-text-muted)}.role-empty{padding:12px;color:var(--app-text-muted);font-size:12px}.role-editor{padding:20px 24px;overflow:auto}.role-editor-head{display:flex;justify-content:space-between;align-items:center;padding-bottom:18px;border-bottom:1px solid var(--app-border)}.role-basic{padding:18px 0 8px}.form-grid-3{display:grid;grid-template-columns:1fr 1fr 150px;gap:14px}.scope-tip{margin-left:14px;color:var(--app-text-muted);font-size:12px}.permission-title{display:grid;gap:5px;padding:18px 0 12px;border-top:1px solid var(--app-border)}.permission-title span{font-size:12px;color:var(--app-text-muted)}.permission-group{border:1px solid var(--app-border);border-radius:10px;margin-bottom:12px;overflow:hidden}.permission-group-name{padding:11px 14px;background:var(--app-hover);font-weight:600;font-size:13px}.permission-row{display:grid;grid-template-columns:220px minmax(0,1fr);align-items:center;padding:11px 14px;border-top:1px solid var(--app-border)}.permission-row :deep(.el-checkbox-group){display:flex;gap:20px;flex-wrap:wrap}.permission-row :deep(.el-checkbox){margin-right:0}.dialog-user{padding:12px;margin-bottom:16px;border:1px solid var(--app-border);border-radius:9px;background:var(--app-hover)}.access-summary{padding:12px;border-radius:8px;background:var(--app-hover);color:var(--app-text-secondary);font-size:13px}@media(max-width:900px){.permission-layout{grid-template-columns:1fr}.role-list{border-right:0;border-bottom:1px solid var(--app-border)}.form-grid-3{grid-template-columns:1fr}.permission-row{grid-template-columns:1fr;gap:8px}.account-toolbar{align-items:flex-start;gap:12px;flex-direction:column}}
</style>

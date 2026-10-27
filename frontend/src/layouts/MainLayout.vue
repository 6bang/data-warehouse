<script setup lang="ts">
import { Bell, Calendar, DataAnalysis, Document, Goods, Grid, List, MagicStick, Moon, Refresh, Setting, Shop, Sunny, TrendCharts, Upload, UserFilled } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/api/http'
import ImportDialog from '@/components/ImportDialog.vue'
import { getStoredTheme, setTheme, type AppTheme } from '@/theme'

const route = useRoute()
const router = useRouter()
const importVisible = ref(false)
const importMode = ref<'file' | 'feishu' | 'mcp'>('file')
const collapsed = ref(false)
const theme = ref<AppTheme>(getStoredTheme())
const userLoaded = ref(false)
const userLoadFailed = ref(false)
const isDemo = computed(() => route.meta.demo === true)
const user = ref<{ username: string; role: string; role_name: string; permission_codes: string[] }>({ username: '', role: 'viewer', role_name: '', permission_codes: [] })
const can = (permission: string) => user.value.permission_codes?.includes(permission) ?? false
const pageAllowed = computed(() => userLoaded.value && (!route.meta.permission || can(String(route.meta.permission))))
const businessGroups = computed(() => [
  { code: '01', label: '经营驾驶舱', items: [{ path: '/realtime', label: '实时数据', icon: TrendCharts, permission: 'dashboard.view' }, { path: '/dashboard', label: '经营总览', icon: DataAnalysis, permission: 'dashboard.view' }] },
  { code: '02', label: '数据 BI 看板', items: [{ path: '/business', label: '综合经营 BI', icon: Grid, permission: 'business.view' }, { path: '/shops', label: '店铺经营 BI', icon: Shop, permission: 'shops.view' }, { path: '/products', label: '商品经营 BI', icon: Goods, permission: 'products.view' }, { path: '/product-catalog', label: '商品档案', icon: Goods, permission: 'products.view' }] },
  { code: '03', label: '运营策略', items: [{ path: '/strategy-alerts', label: '运营策略预警', icon: Bell, permission: 'strategy_alerts.view' }, { path: '/strategies', label: '运营策略', icon: Document, permission: 'strategies.view' }, { path: '/operation-plans', label: '运营计划', icon: Calendar, permission: 'operation_plans.view' }] },
  { code: '04', label: 'AI 工具区', items: [{ path: '/ai-analysis', label: 'AI 分析中心', icon: MagicStick, permission: 'ai_analysis.view' }, { path: '/tasks', label: '运营任务中心', icon: List, permission: 'tasks.view' }] },
  { code: '05', label: '配置区', items: [{ path: '/configuration', label: '配置中心', icon: Setting, permission: 'configuration.view' }, { path: '/users', label: '用户与权限', icon: UserFilled, permission: 'accounts.view' }] },
].map(group => ({ ...group, items: group.items.filter(item => can(item.permission)) })).filter(group => group.items.length))
const groups = computed(() => businessGroups.value.map(group => ({ ...group, items: group.items.map(item => ({ ...item, path: isDemo.value ? `/demo${item.path}` : item.path })) })))
const pageTitle = computed(() => String(route.meta.title || '经营数据云仓'))
const pageSubtitle = computed(() => isDemo.value ? '演示模式 · 经营数据与操作均为模拟，刷新后重置' : route.path === '/realtime' ? '今日经营总览 · 一屏看清成交、利润与投放' : '月度经营口径 · 数据驱动运营闭环')

let userRequestVersion = 0
async function loadUser() {
  const version = ++userRequestVersion
  const demo = isDemo.value
  userLoadFailed.value = false
  try {
    const { data } = await http.get('/users/me/')
    if (version !== userRequestVersion || demo !== isDemo.value) return
    user.value = data
    userLoaded.value = true
    checkPagePermission()
  } catch {
    if (version !== userRequestVersion || demo !== isDemo.value) return
    userLoadFailed.value = true
  }
}
watch(isDemo, () => {
  userLoaded.value = false
  user.value = { username: '', role: 'viewer', role_name: '', permission_codes: [] }
  void loadUser()
}, { immediate: true })
function checkPagePermission() {
  if (isDemo.value) return
  if (!userLoaded.value) return
  const required = String(route.meta.permission || '')
  const fallback = businessGroups.value[0]?.items[0]?.path
  if (required && !can(required) && fallback) router.replace(fallback)
}
watch(() => route.fullPath, () => {
  importVisible.value = false
  checkPagePermission()
})
function exitDemo() {
  window.location.assign('/login')
}
function openImport(mode: 'file' | 'feishu' | 'mcp') { importMode.value = mode; importVisible.value = true }
function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark'; setTheme(theme.value) }
function logout() {
  if (isDemo.value) { exitDemo(); return }
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  router.push('/login')
}
</script>

<template>
  <div class="app-shell" :class="{ collapsed, 'demo-mode': isDemo }">
    <aside class="side-nav">
      <div class="app-brand" @click="router.push(isDemo ? '/demo' : '/realtime')"><span class="app-logo">云</span><span class="brand-copy"><b>经营数据云仓</b><small>Commerce Intelligence</small></span></div>
      <nav aria-label="主导航">
        <section v-for="group in groups" :key="group.label" class="nav-group">
          <div class="nav-group-title"><span>{{ group.code }}</span><b>{{ group.label }}</b></div>
          <button v-for="item in group.items" :key="item.path" :class="{active:route.path===item.path}" @click="router.push(item.path)"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></button>
        </section>
      </nav>
    </aside>
    <div class="workspace">
      <header class="top-nav">
        <div class="header-title"><button class="collapse-button" @click="collapsed=!collapsed">☰</button><div><b>{{ pageTitle }}</b><small>{{ pageSubtitle }}</small></div></div>
        <div class="header-actions">
          <el-button class="theme-toggle" :icon="theme==='dark'?Sunny:Moon" @click="toggleTheme">{{ theme==='dark'?'浅色':'深色' }}</el-button>
          <el-button v-if="!isDemo && can('products.view')" :icon="TrendCharts" aria-label="进入演示模式" title="进入演示模式" @click="router.push('/demo')">演示模式</el-button>
          <el-button v-if="isDemo" class="exit-demo" type="primary" plain title="仅演示；不会采集数据、调用模型或保存真实配置" aria-label="退出演示" @click="exitDemo">演示 · 退出</el-button>
          <el-button v-if="can('data_sync.manage')" :icon="Refresh" @click="openImport('mcp')">数据同步</el-button>
          <el-button v-if="can('data_import.manage')" type="primary" :icon="Upload" @click="openImport('file')">导入数据</el-button>
          <el-dropdown><button class="user-avatar">{{ (user.username || 'U').slice(0,1).toUpperCase() }}</button><template #dropdown><el-dropdown-menu><el-dropdown-item disabled>{{ user.username }} · {{ user.role_name || user.role }}</el-dropdown-item><el-dropdown-item @click="logout">退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>
      </header>
      <main class="app-main"><router-view v-if="pageAllowed" :key="route.fullPath" /><div v-else class="page" role="status"><template v-if="userLoadFailed">无法确认访问权限，请检查网络后重试。<el-button @click="loadUser">重试</el-button></template><template v-else-if="userLoaded">暂无页面访问权限，请联系管理员授权。<el-button @click="logout">退出登录</el-button></template><template v-else>正在确认访问权限…</template></div></main>
    </div>
  </div>
  <ImportDialog v-model="importVisible" :initial-tab="importMode" @imported="router.go(0)" />
</template>

<style scoped>
.app-shell{min-height:100vh;background:var(--app-bg);display:grid;grid-template-columns:240px minmax(0,1fr);transition:grid-template-columns .2s,background .2s}.side-nav{height:100vh;position:sticky;top:0;background:var(--app-sidebar);border-right:1px solid var(--app-border);padding:18px 12px;display:flex;flex-direction:column;z-index:21;box-shadow:0 8px 24px rgba(15,23,42,.03)}.app-brand{height:54px;display:flex;align-items:center;gap:12px;padding:0 10px;color:var(--app-text);cursor:pointer;border-radius:14px;border:1px solid transparent}.app-brand:hover{background:color-mix(in srgb,var(--app-hover) 60%,transparent);border-color:color-mix(in srgb,var(--app-border) 55%,transparent)}.app-logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,#1f4ed8,#10a7b7);color:#fff;flex:0 0 auto;box-shadow:0 10px 22px rgba(31,78,216,.22)}.brand-copy{display:grid;gap:2px;white-space:nowrap}.brand-copy b{font-size:15px;letter-spacing:.01em}.brand-copy small{color:var(--app-text-muted);font-size:9px;letter-spacing:.18em;text-transform:uppercase}.side-nav nav{min-height:0;overflow-y:auto;padding-right:2px}.nav-group{margin-top:18px}.nav-group+.nav-group{padding-top:15px;border-top:1px solid color-mix(in srgb,var(--app-border) 70%,transparent)}.nav-group-title{padding:0 10px 9px;display:flex;align-items:center;gap:8px;color:var(--app-text-muted)}.nav-group-title span{font-size:9px;letter-spacing:.08em;color:#5d7cf0;background:color-mix(in srgb,#2f6df6 10%,transparent);border:1px solid color-mix(in srgb,#2f6df6 20%,transparent);border-radius:5px;padding:2px 4px}.nav-group-title b{font-size:11px;letter-spacing:.1em}.nav-group button{width:100%;border:0;background:transparent;color:var(--app-text-secondary);padding:11px 12px;border-radius:10px;font:inherit;display:flex;align-items:center;gap:10px;cursor:pointer;text-align:left;margin:3px 0;transition:background .15s,color .15s,transform .15s}.nav-group button:hover{color:var(--app-text);background:color-mix(in srgb,var(--app-hover) 72%,transparent)}.nav-group button.active{color:#1745c7;background:color-mix(in srgb,#2f6df6 12%,var(--app-hover));box-shadow:inset 3px 0 #2f6df6}.workspace{min-width:0}.top-nav{height:70px;background:var(--app-header);backdrop-filter:blur(12px);border-bottom:1px solid var(--app-border);display:flex;align-items:center;justify-content:space-between;padding:0 22px;gap:20px;position:sticky;top:0;z-index:20;box-shadow:0 8px 24px rgba(15,23,42,.03)}.header-title{display:flex;align-items:center;gap:12px}.header-title>div{display:grid;gap:3px}.header-title b{font-size:15px;letter-spacing:.01em}.header-title small{font-size:11px;color:var(--app-text-muted)}.collapse-button{border:0;background:transparent;color:var(--app-text-secondary);font-size:18px;cursor:pointer}.header-actions{display:flex;align-items:center;gap:10px}.theme-toggle{min-width:78px}.user-avatar{width:34px;height:34px;border:0;border-radius:50%;background:linear-gradient(135deg,#1f4ed8,#10a7b7);color:#fff;cursor:pointer;font-weight:600;box-shadow:0 10px 22px rgba(31,78,216,.18)}.app-main{min-height:calc(100vh - 70px)}.collapsed{grid-template-columns:76px minmax(0,1fr)}.collapsed .brand-copy,.collapsed .nav-group-title,.collapsed .nav-group button span{display:none}.collapsed .nav-group button{justify-content:center}.collapsed .app-brand{justify-content:center;padding:0}
@media(max-width:860px){.app-shell,.app-shell.collapsed{display:block}.side-nav{height:auto;position:sticky;padding:8px 10px;flex-direction:row;align-items:center;overflow-x:auto}.app-brand{height:44px}.brand-copy,.nav-group-title{display:none}.side-nav nav{display:flex}.nav-group{margin:0;display:flex}.nav-group button{width:auto;white-space:nowrap}.top-nav{top:60px;padding:0 12px}.header-title small{display:none}.header-actions :deep(.el-button span){display:none}}
</style>

<style scoped>
@media(max-width:860px){.header-actions .exit-demo :deep(span){display:inline}.header-actions .exit-demo{padding-inline:10px}}
@media(max-width:860px){.demo-mode .top-nav{height:auto;min-height:70px;flex-wrap:wrap;gap:8px;padding-block:8px}.demo-mode .header-title{flex-basis:100%}.demo-mode .header-actions{flex-wrap:wrap;gap:6px;max-width:100%}.demo-mode .header-actions :deep(.el-button){margin-left:0}.demo-mode .theme-toggle{min-width:0}}
.demo-mode :deep(.realtime-home){grid-template-columns:minmax(0,1fr)}
.demo-mode :deep(.realtime-home > *){min-width:0}
</style>

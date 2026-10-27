import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { DEMO_PAGE_PATHS } from '@/demo/contracts'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    { path: '/register', component: () => import('@/views/RegisterView.vue') },
    {
      path: '/', component: MainLayout, redirect: '/realtime', children: [
        { path: 'realtime', component: () => import('@/views/RealtimeView.vue'), meta: { title: '实时数据', permission: 'dashboard.view' } },
        { path: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '经营总览', permission: 'dashboard.view' } },
        { path: 'business', component: () => import('@/views/BusinessView.vue'), meta: { title: '综合经营 BI', permission: 'business.view' } },
        { path: 'shops', component: () => import('@/views/ShopsView.vue'), meta: { title: '店铺经营 BI', permission: 'shops.view' } },
        { path: 'products', component: () => import('@/views/ProductsView.vue'), meta: { title: '商品经营 BI', permission: 'products.view' } },
        { path: 'product-catalog', component: () => import('@/views/ProductCatalogView.vue'), meta: { title: '商品档案', permission: 'products.view' } },
        { path: 'strategy-alerts', component: () => import('@/views/StrategyAlertsView.vue'), meta: { title: '运营策略预警', permission: 'strategy_alerts.view' } },
        { path: 'strategies', component: () => import('@/views/StrategiesView.vue'), meta: { title: '运营策略', permission: 'strategies.view' } },
        { path: 'operation-plans', component: () => import('@/views/OperationPlansView.vue'), meta: { title: '运营计划', permission: 'operation_plans.view' } },
        { path: 'tasks', component: () => import('@/views/TasksView.vue'), meta: { title: '运营任务中心', permission: 'tasks.view' } },
        { path: 'ai-analysis', component: () => import('@/views/AIAnalysisView.vue'), meta: { title: 'AI 分析中心', permission: 'ai_analysis.view' } },
        { path: 'users', component: () => import('@/views/UsersView.vue'), meta: { title: '用户与权限', permission: 'accounts.view' } },
        { path: 'configuration', component: () => import('@/views/ConfigurationView.vue'), meta: { title: '系统配置', permission: 'configuration.view' } },
      ],
    },
  ],
})

// Use the exact same page components and layout; only the transport is simulated.
const businessRoute = router.options.routes.find(record => record.path === '/')!
router.addRoute({
  path: '/demo', component: MainLayout, redirect: '/demo/realtime', meta: { demo: true },
  children: businessRoute.children!.map(record => ({ ...record, meta: { ...record.meta, demo: true } })),
})

router.beforeEach((to, from) => {
  // Keep existing in-page links within the demo when they target business pages.
  if (from.meta.demo && DEMO_PAGE_PATHS.includes(to.path)) return `/demo${to.fullPath}`
  if (to.meta.demo === true) return true
  const publicRoutes = ['/login', '/register']
  if (!publicRoutes.includes(to.path) && !localStorage.getItem('access_token')) return '/login'
  if (publicRoutes.includes(to.path) && localStorage.getItem('access_token')) return '/realtime'
})

export default router

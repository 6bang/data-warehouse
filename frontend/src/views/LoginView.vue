<script setup lang="ts">
import axios, { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const feishuLoading = ref(false)
const form = reactive({ username: '', password: '' })

async function login() {
  if (!form.username || !form.password) return ElMessage.warning('请输入用户名和密码')
  loading.value = true
  try {
    const { data } = await axios.post('/api/v1/auth/token/', form)
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    router.push('/realtime')
  } catch (error) {
    const responseData = (error as AxiosError<{ detail?: string; error?: { detail?: string } }>).response?.data
    const detail = responseData?.detail || responseData?.error?.detail
    ElMessage.error(detail || '用户名或密码错误')
  } finally {
    loading.value = false
  }
}

const feishuReason: Record<string, string> = {
  not_configured: '飞书登录尚未配置，请联系管理员',
  invalid_state: '飞书登录状态已失效，请重新发起登录',
  cancelled: '你已取消飞书授权',
  tenant_denied: '该飞书账号不属于本公司，无法进入系统',
  oauth_failed: '飞书授权失败，请稍后重试',
}

async function exchangeFeishuLogin() {
  if (route.query.feishu !== 'complete') return
  feishuLoading.value = true
  try {
    const { data } = await axios.post('/api/v1/auth/feishu/exchange/')
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    await router.replace('/realtime')
  } catch (error) {
    const responseData = (error as AxiosError<{ detail?: string }>).response?.data
    ElMessage.warning(responseData?.detail || '飞书账号已提交，等待管理员审批')
    await router.replace('/login')
  } finally {
    feishuLoading.value = false
  }
}

function startFeishuLogin() {
  window.location.href = '/api/v1/auth/feishu/start/'
}

onMounted(() => {
  const reason = String(route.query.feishu || '')
  if (reason && reason !== 'complete') ElMessage.warning(feishuReason[reason] || '飞书登录未完成')
  void exchangeFeishuLogin()
})
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand-mark">云</div>
      <div class="brand-title">经营数据云仓</div>
      <div class="brand-subtitle">看数据、找异常、定行动、做复盘</div>
      <el-form label-position="top" @submit.prevent="login">
        <el-form-item label="用户名"><el-input v-model="form.username" size="large" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" size="large" show-password autocomplete="current-password" @keyup.enter="login" /></el-form-item>
        <el-button type="primary" size="large" class="full-width" :loading="loading" @click="login">登录</el-button>
      </el-form>
      <el-divider>或</el-divider>
      <el-button size="large" class="full-width feishu-login-button" :loading="feishuLoading" @click="startFeishuLogin">使用飞书账号登录 / 注册</el-button>
      <div class="login-hint">仅允许已授权企业租户的飞书成员，首次登录需管理员审批</div>
      <div class="auth-switch">还没有账号？<router-link to="/register">申请注册</router-link></div>
      <div class="demo-entry"><router-link to="/demo">免登录体验五店经营演示 →</router-link><small>虚构商品样本 · 虚拟店铺 · 模拟经营数据</small></div>
    </div>
  </div>
</template>

<style scoped>
.auth-switch{text-align:center;color:#9296a1;font-size:14px;margin-top:20px}.auth-switch a{color:#8c7cff;text-decoration:none}.auth-switch a:hover{color:#a89dff}.feishu-login-button{border-color:#3370ff;color:#3370ff}.login-hint{text-align:center;color:#9296a1;font-size:12px;line-height:1.5;margin-top:10px}
.demo-entry{display:grid;gap:8px;text-align:center;margin-top:24px;padding-top:20px;border-top:1px solid var(--app-border)}.demo-entry a{color:var(--app-text);font-size:14px;line-height:1.6;text-underline-offset:4px}.demo-entry a:hover{color:#3370ff}.demo-entry a:focus-visible{outline:2px solid #3370ff;outline-offset:4px}.demo-entry small{color:var(--app-text-muted);font-size:11px;line-height:1.6}
</style>

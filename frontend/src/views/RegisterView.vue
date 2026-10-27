<script setup lang="ts">
import axios, { AxiosError } from 'axios'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({
  username: '', display_name: '', email: '', department: '', requested_role_code: 'viewer',
  registration_reason: '', password: '', password_confirm: '',
})
const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 150, message: '用户名至少 3 个字符', trigger: 'blur' },
    { pattern: /^[\w.@+-]+$/, message: '用户名只能包含字母、数字和 @/./+/-/_', trigger: 'blur' },
  ],
  display_name: [{ required: true, min: 2, max: 50, message: '请输入姓名或称呼', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 个字符', trigger: 'blur' }],
  password_confirm: [{
    validator: (_rule, value, callback) => value === form.password ? callback() : callback(new Error('两次输入的密码不一致')),
    trigger: 'blur',
  }],
}

function firstError(data: Record<string, unknown> | undefined) {
  if (!data) return ''
  const value = Object.values(data)[0]
  return Array.isArray(value) ? String(value[0]) : typeof value === 'string' ? value : ''
}

async function register() {
  if (!await formRef.value?.validate().catch(() => false)) return
  loading.value = true
  try {
    const { data } = await axios.post('/api/v1/auth/register/', form)
    ElMessage.success(data.message || '注册申请已提交')
    router.push('/login')
  } catch (error) {
    const data = (error as AxiosError<Record<string, unknown>>).response?.data
    const details = data?.error && typeof data.error === 'object' ? data.error as Record<string, unknown> : data
    ElMessage.error(firstError(details) || '注册失败，请检查填写内容')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card register-card">
      <div class="brand-mark">云</div>
      <div class="brand-title">申请加入数据云仓</div>
      <div class="brand-subtitle">提交后由管理员审批，批准后即可登录</div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="register">
        <div class="form-row">
          <el-form-item label="用户名" prop="username"><el-input v-model="form.username" size="large" autocomplete="username" /></el-form-item>
          <el-form-item label="姓名 / 称呼" prop="display_name"><el-input v-model="form.display_name" size="large" /></el-form-item>
        </div>
        <el-form-item label="邮箱（选填）" prop="email"><el-input v-model="form.email" size="large" autocomplete="email" /></el-form-item>
        <div class="form-row">
          <el-form-item label="部门 / 团队（选填）"><el-input v-model="form.department" size="large" placeholder="例如：电商运营部" /></el-form-item>
          <el-form-item label="申请角色">
            <el-select v-model="form.requested_role_code" size="large" style="width:100%">
              <el-option label="阅读者 · 查看授权数据" value="viewer" />
              <el-option label="编辑者 · 维护策略与任务" value="editor" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="申请说明（选填）"><el-input v-model="form.registration_reason" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="说明负责的店铺或需要使用的功能" /></el-form-item>
        <div class="form-row">
          <el-form-item label="密码" prop="password"><el-input v-model="form.password" type="password" size="large" show-password autocomplete="new-password" /></el-form-item>
          <el-form-item label="确认密码" prop="password_confirm"><el-input v-model="form.password_confirm" type="password" size="large" show-password autocomplete="new-password" @keyup.enter="register" /></el-form-item>
        </div>
        <el-button type="primary" size="large" class="full-width" :loading="loading" @click="register">提交注册申请</el-button>
      </el-form>
      <div class="auth-switch">已有账号？<router-link to="/login">返回登录</router-link></div>
    </div>
  </div>
</template>

<style scoped>
.register-card{width:min(620px,calc(100vw - 32px))}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.auth-switch{text-align:center;color:#9296a1;font-size:14px;margin-top:20px}.auth-switch a{color:#8c7cff;text-decoration:none}@media(max-width:600px){.form-row{grid-template-columns:1fr;gap:0}}
</style>

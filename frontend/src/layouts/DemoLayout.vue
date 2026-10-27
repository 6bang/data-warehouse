<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { ref } from 'vue'
import { getStoredTheme, setTheme, type AppTheme } from '@/theme'

const theme = ref<AppTheme>(getStoredTheme())
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  setTheme(theme.value)
}
</script>

<template>
  <div class="demo-shell">
    <header class="demo-header">
      <router-link to="/demo" class="demo-brand" aria-label="经营数据云仓演示首页">
        <span class="demo-logo">云</span>
        <span class="brand-copy"><b>经营数据云仓</b><small>DEMO · 免登录演示</small></span>
      </router-link>
      <nav class="demo-header-actions" aria-label="演示工具">
        <el-button class="theme-toggle" :icon="theme === 'dark' ? Sunny : Moon" @click="toggleTheme">{{ theme === 'dark' ? '浅色' : '深色' }}</el-button>
        <router-link to="/login" class="login-link">返回登录</router-link>
      </nav>
    </header>
    <main class="demo-main"><router-view /></main>
  </div>
</template>

<style scoped>
.demo-shell{min-height:100vh;background:var(--app-bg);color:var(--app-text)}
.demo-header{height:70px;position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 24px;background:var(--app-header);border-bottom:1px solid var(--app-border);backdrop-filter:blur(12px)}
.demo-brand{display:flex;align-items:center;gap:12px;color:var(--app-text);text-decoration:none;border-radius:10px}
.demo-logo{width:38px;height:38px;display:grid;place-items:center;flex-shrink:0;border-radius:11px;background:linear-gradient(135deg,#1f4ed8,#10a7b7);color:#fff;box-shadow:0 10px 22px rgba(31,78,216,.22)}
.brand-copy{display:grid;gap:3px;white-space:nowrap}.brand-copy b{font-size:15px;letter-spacing:.01em}.brand-copy small{font-size:10px;letter-spacing:.12em;color:var(--app-text-muted)}
.demo-header-actions{display:flex;align-items:center;gap:12px}.theme-toggle{min-width:78px}.login-link{display:inline-flex;align-items:center;justify-content:center;min-height:32px;padding:0 14px;border:1px solid var(--app-border);border-radius:6px;color:var(--app-text-secondary);background:var(--app-surface);font-size:14px;text-decoration:none;white-space:nowrap}.login-link:hover{color:var(--app-text);background:var(--app-hover)}
.demo-brand:focus-visible,.login-link:focus-visible{outline:2px solid #2f6df6;outline-offset:4px}.demo-main{min-width:0;min-height:calc(100vh - 70px)}
@media(max-width:560px){.demo-header{padding:0 12px;gap:10px}.demo-brand{gap:8px}.demo-logo{width:32px;height:32px}.brand-copy b{font-size:13px}.brand-copy small{font-size:9px;letter-spacing:.04em}.demo-header-actions{gap:7px}.theme-toggle{min-width:0;padding-inline:8px}.login-link{font-size:12px;padding-inline:8px}}
</style>

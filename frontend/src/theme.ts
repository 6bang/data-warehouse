export type AppTheme = 'dark' | 'light'

const STORAGE_KEY = 'commerce_warehouse_theme'

export function getStoredTheme(): AppTheme {
  try { return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light' }
  catch { return 'light' }
}

export function applyTheme(theme: AppTheme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.classList.toggle('light-theme', theme === 'light')
  root.style.colorScheme = theme
  window.dispatchEvent(new CustomEvent('warehouse-theme-change', { detail: { theme } }))
}

export function setTheme(theme: AppTheme) {
  try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* use current session only */ }
  applyTheme(theme)
}

export function initTheme() { applyTheme(getStoredTheme()) }

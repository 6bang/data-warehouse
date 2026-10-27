import axios, { type AxiosAdapter } from 'axios'
import { isDemoPath } from '@/demo/contracts'

const demoAdapter: AxiosAdapter = async (config) => {
  const { respondToDemoRequest } = await import('@/demo/adapter')
  return respondToDemoRequest(config)
}

const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1', timeout: 120000 })

http.interceptors.request.use((config) => {
  // Demo requests are fulfilled in memory, never sent to the backend — even
  // when a real user's access token exists or a caller provides an absolute URL.
  if (isDemoPath(window.location.pathname)) {
    config.headers.delete('Authorization')
    config.headers.delete('Cookie')
    config.withCredentials = false
    config.adapter = demoAdapter
    return config
  }
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(undefined, async (error) => {
  const original = error.config
  if (original?.adapter === demoAdapter) return Promise.reject(error)
  if (error.response?.status === 401 && !original?._retried) {
    original._retried = true
    const refresh = localStorage.getItem('refresh_token')
    if (refresh) {
      try {
        const { data } = await axios.post('/api/v1/auth/token/refresh/', { refresh })
        localStorage.setItem('access_token', data.access)
        original.headers.Authorization = `Bearer ${data.access}`
        return http(original)
      } catch { /* clear below */ }
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
  }
  return Promise.reject(error)
})

export default http

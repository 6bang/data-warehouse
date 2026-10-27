import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { loadDemoCatalog } from './catalog'
import { demoDate } from './data'
import { handleBusinessDemo } from './business'
import { handleOperationsDemo } from './operations'
import { handleAdminDemo } from './admin'
import type { DemoContext, DemoRequest } from './contracts'

let contextPromise: Promise<DemoContext> | undefined
function context() {
  contextPromise ??= loadDemoCatalog().then(products => ({ products, date: demoDate() })).catch(error => {
    contextPromise = undefined
    throw error
  })
  return contextPromise
}

export async function respondToDemoRequest(config: InternalAxiosRequestConfig) {
  try {
    const requestUrl = config.url || '/'
    // Accept only root-relative API paths before URL parsing can normalize an
    // absolute URL, protocol-relative URL, backslash or control character.
    const unsafeCharacters = Array.from(requestUrl).some(character => character === '\\' || character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)
    if (!/^\/(?!\/)/.test(requestUrl) || unsafeCharacters) {
      throw new Error('演示模式只接受本地相对 API 路径，不会连接外部服务')
    }
    const url = new URL(requestUrl, 'https://example.invalid')
    // This is a finite mock API, not a proxy. Unknown calls fail closed.
    if (url.origin !== 'https://example.invalid') throw new Error('演示模式不会连接外部服务')
    let path = url.pathname.replace(/^\/api\/v1(?=\/)/, '')
    if (!path.endsWith('/')) path += '/'
    let body: Record<string, unknown> = {}
    if (typeof config.data === 'string') body = JSON.parse(config.data)
    else if (config.data && !(config.data instanceof FormData)) body = config.data
    const request: DemoRequest = { method: (config.method || 'GET').toUpperCase(), path, params: { ...Object.fromEntries(url.searchParams), ...config.params }, body }
    const ctx = await context()
    if (config.signal?.aborted) throw new Error('演示请求已取消')
    const result = handleAdminDemo(request, ctx) ?? handleBusinessDemo(request, ctx) ?? handleOperationsDemo(request, ctx)
    if (result === undefined) throw new Error('此操作尚未开放演示；未请求真实服务')
    if (request.method !== 'GET') {
      const { ElMessage } = await import('element-plus')
      ElMessage.info({ message: '演示操作：仅在当前页面会话生效，未调用或修改真实服务。', grouping: true })
    }
    return { data: structuredClone(result), status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : '演示数据读取失败'
    throw new AxiosError(detail, 'ERR_DEMO_REQUEST', config, undefined, {
      data: { detail }, status: 400, statusText: 'Demo request unavailable', headers: new AxiosHeaders(), config,
    })
  }
}

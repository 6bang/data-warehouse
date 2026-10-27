import type { DemoProduct } from './data'

// Exact, shipped-file allowlist. Reject remote URLs, traversal, query strings,
// fragments and protocol-relative URLs rather than normalizing untrusted input.
const DEMO_ASSETS = new Set(Array.from({ length: 60 }, (_, index) =>
  `/demo-assets/product-${String(index + 1).padStart(3, '0')}.svg`,
))
export function isDemoAssetUrl(value: string): boolean {
  return DEMO_ASSETS.has(value)
}

/** Fully fictional local catalog; never query authenticated business APIs. */
export async function loadDemoCatalog(signal?: AbortSignal): Promise<DemoProduct[]> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  const timer = setTimeout(abort, 15000)
  try {
    const response = await fetch('/demo-products.json', {
      credentials: 'omit', signal: controller.signal, cache: 'no-cache',
    })
    if (!response.ok) throw new Error('Demo catalog unavailable')
    const data = await response.json()
    if (data?.version !== 1 || !Array.isArray(data.products)) throw new Error('Invalid demo catalog')
    const products: DemoProduct[] = []
    const seen = new Set<string>()
    for (const row of data.products) {
      if (!row || typeof row.id !== 'string' || typeof row.name !== 'string') continue
      const id = row.id.trim()
      const name = row.name.trim()
      if (!id || !name || seen.has(id)) continue
      seen.add(id)
      let imageUrl = typeof row.imageUrl === 'string' ? row.imageUrl : ''
      if (!isDemoAssetUrl(imageUrl)) imageUrl = ''
      products.push({
        id, name, code: typeof row.code === 'string' ? row.code : '', imageUrl, createdAt: null,
      })
      if (products.length === 60) break
    }
    return products
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

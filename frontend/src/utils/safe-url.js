// Keep navigation and embedded content away from executable URL schemes.
export function safeHttpUrl(value, origin) {
  if (typeof value !== 'string') return ''
  const raw = value.trim()
  if (!raw || /[\\\u0000-\u0020\u007f]/.test(raw)) return ''
  try {
    if (raw.startsWith('/')) {
      const path = decodeURIComponent(raw.split(/[?#]/, 1)[0])
      if (/[\\\u0000-\u0020\u007f]/.test(path) || path.startsWith('//')) return ''
    } else if (!/^https?:\/\//i.test(raw)) {
      return ''
    }
    const parsed = new URL(raw, origin)
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) return ''
    return parsed.toString()
  } catch {
    return ''
  }
}

export function safeInternalPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/')) return ''
  const origin = 'https://internal.invalid'
  const resolved = safeHttpUrl(value, origin)
  if (!resolved) return ''
  const parsed = new URL(resolved)
  return parsed.origin === origin ? `${parsed.pathname}${parsed.search}${parsed.hash}` : ''
}

export function safeGrafanaUrl(value, origin) {
  const safe = safeHttpUrl(value, origin)
  if (!safe) return ''
  const parsed = new URL(safe)
  const current = new URL(origin)
  const path = parsed.pathname
  const grafanaPath = path === '/' || ['/d/', '/dashboard/', '/explore', '/public/', '/api/'].some(prefix => path.startsWith(prefix))
  const alreadyProxied = parsed.origin === current.origin && path.startsWith('/grafana/')
  const shouldProxy = current.protocol === 'https:' && grafanaPath && !alreadyProxied
    && (parsed.protocol === 'http:' || parsed.origin !== current.origin || value.trim().startsWith('/'))
  if (shouldProxy) {
    const proxied = new URL(`/grafana${path}`, current.origin)
    proxied.search = parsed.search
    proxied.hash = parsed.hash
    return proxied.toString()
  }
  if (current.protocol === 'https:' && parsed.protocol !== 'https:') return ''
  return parsed.toString()
}

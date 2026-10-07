// Thin API client for the dashboard.
//
// The dashboard always talks to the real, RBAC-protected API: a signed token
// is issued by the development bootstrap endpoint (or by the Telegram WebApp
// login in production) and sent as a Bearer header on every request.

const SESSION_KEY = 'viralai.session'

export function getApiUrl() {
  return (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
}

export function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const session = JSON.parse(raw)
    if (!session?.token || !session?.workspace_id) return null
    return session
  } catch {
    return null
  }
}

export function saveSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem('viralai.lastAnalysis')
  localStorage.removeItem('viralai.accountStats')
}

export function accountStats() {
  try {
    const raw = localStorage.getItem('viralai.accountStats')
    return raw ? JSON.parse(raw) : { average_views: null, best_views: null }
  } catch {
    return { average_views: null, best_views: null }
  }
}

export function saveAccountStats(stats) {
  localStorage.setItem('viralai.accountStats', JSON.stringify(stats))
}

export function lastAnalysis() {
  try {
    const raw = localStorage.getItem('viralai.lastAnalysis')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveLastAnalysis(analysis) {
  localStorage.setItem('viralai.lastAnalysis', JSON.stringify(analysis))
}

export class ApiAuthError extends Error {
  constructor(message) {
    super(message)
    this.name = 'ApiAuthError'
  }
}

export function apiError(response) {
  return response.json().then(
    (body) => {
      const message = body.detail || `Ilova xatosi (${response.status})`
      if (response.status === 401) return new ApiAuthError(message)
      return new Error(message)
    },
    () => new Error(`Ilova xatosi (${response.status})`)
  )
}

let rebootstraping = null
function rebootstrap() {
  if (!rebootstraping) {
    rebootstraping = bootstrapSession({}).finally(() => { rebootstraping = null })
  }
  return rebootstraping
}

export async function api(path, { method = 'GET', body, form, headers = {} } = {}) {
  const attempt = async () => {
    const session = loadSession()
    const requestHeaders = { ...headers }
    if (session?.token) requestHeaders.Authorization = `Bearer ${session.token}`
    if (body !== undefined) requestHeaders['Content-Type'] = 'application/json'

    const response = await fetch(`${getApiUrl()}${path}`, {
      method,
      headers: requestHeaders,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    })
    if (!response.ok) throw await apiError(response)
    if (response.status === 204) return null
    return response.json()
  }

  try {
    return await attempt()
  } catch (error) {
    // The signed token expires after an hour; transparently re-issue it once.
    if (error instanceof ApiAuthError && loadSession()) {
      await rebootstrap()
      return attempt()
    }
    throw error
  }
}

export async function apiDownload(path, filename) {
  const session = loadSession()
  const response = await fetch(`${getApiUrl()}${path}`, {
    headers: session?.token ? { Authorization: `Bearer ${session.token}` } : {},
  })
  if (!response.ok) throw await apiError(response)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 4000)
  return blob
}

/**
 * Development session bootstrap: creates (or reuses) the demo user + workspace
 * and returns a signed token. In production this endpoint answers 410 and the
 * login flow is Telegram WebApp based.
 */
export async function bootstrapSession(profile = {}) {
  const response = await fetch(`${getApiUrl()}/v1/session/bootstrap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
  if (!response.ok) throw await apiError(response)
  const session = await response.json()
  saveSession(session)
  return session
}

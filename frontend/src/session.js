// Client ordering only; server cookie, CSRF and owner checks remain authoritative.
export function createSessionFence() {
  let owner, generation = 0
  return {
    accept(next) { if (owner !== next) { owner = next; generation++ } },
    capture() { return generation },
    current(value) { return value === generation },
  }
}
const fence = createSessionFence()
let csrfToken = ''
let authEnabled = true
export function acceptSession(value) {
  authEnabled = value.enabled !== false
  fence.accept(value.enabled ? value.user?.id || null : 'local-fixture')
  csrfToken = value.csrf_token || ''
}
export const captureSession = () => fence.capture()
export const isCurrentSession = value => fence.current(value)
export function assertCurrentSession(value) {
  if (!fence.current(value)) throw new DOMException('Your account changed.', 'AbortError')
}
export function expireSession(value) {
  if (!fence.current(value)) return
  acceptSession({ enabled: true, user: null })
  window.dispatchEvent(new Event('mra-session-expired'))
}
export async function readSession() {
  const response = await fetch('/api/auth/session', { cache: 'no-store' })
  if (!response.ok) throw new Error('Your workspace is unavailable. Please try again.')
  return response.json()
}
export async function request(path, options = {}) {
  const generation = captureSession()
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (authEnabled && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!csrfToken) throw new Error('Refresh the page to prepare a secure session.')
    headers.set('X-CSRF-Token', csrfToken)
  }
  const response = await fetch(path, { ...options, headers })
  assertCurrentSession(generation)
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/auth/')) expireSession(generation)
    const data = await response.json().catch(() => ({}))
    const detail = data.error || data.detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status}). Please try again.`)
  }
  return response
}
export async function requestJSON(path, options = {}) {
  const generation = captureSession()
  const response = await request(path, options)
  const value = await response.json()
  assertCurrentSession(generation)
  return value
}
export const storageKey = (owner, name) => `mra:${owner}:${name}`
export function removeLegacyPreferences() {
  for (const key of ['mra_session','mra_agents','mra_custom_agents','mra_stage_order','mra_toggles','mra_settings','mra_prompts_v','mra_conversation']) localStorage.removeItem(key)
}

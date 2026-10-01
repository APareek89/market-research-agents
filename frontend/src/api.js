import { request, requestJSON, captureSession, assertCurrentSession, expireSession } from './session.js'

export function sessionId() { return 'signed-in' }

export async function getDefaults() {
  return requestJSON('/api/defaults')
}

export async function getConversations() {
  return requestJSON(`/api/conversations?session_id=${sessionId()}`)
}

export async function getMessages(cid) {
  return requestJSON(`/api/conversations/${cid}/messages`)
}

export async function exportReport(format, title, markdown, diagrams = []) {
  const generation = captureSession()
  const resp = await request('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format, title, markdown, diagrams }),
  })
  if (!resp.ok) throw new Error('Export failed')
  const blob = await resp.blob()
  assertCurrentSession(generation)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'pptx' ? 'agent-council-report.pptx' : 'agent-council-report.pdf'
  a.click()
  URL.revokeObjectURL(url)
}

export async function synthesizePrompt({ agentName, agentRole, currentPrompt, notes, files, settings }) {
  const form = new FormData()
  form.append('agent_name', agentName)
  form.append('agent_role', agentRole)
  form.append('current_prompt', currentPrompt)
  form.append('notes', notes)
  form.append('settings', JSON.stringify(settings || {}))
  for (const f of files) form.append('files', f, f.name)
  const data = await requestJSON('/api/synthesize-prompt', { method: 'POST', body: form })
  return data.prompt
}

// Parse an SSE body, invoking onEvent per data frame (heartbeat comments skipped).
async function readSSE(resp, onEvent, generation) {
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try { while (true) {
    const { done, value } = await reader.read()
    assertCurrentSession(generation)
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop()
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      let event
      try { event = JSON.parse(line.slice(6)) }
      catch { continue /* ignore malformed frame */ }
      if (event.type === 'session_expired') {
        expireSession(generation)
        throw new DOMException('Your session expired.', 'AbortError')
      }
      onEvent(event)
    }
  } } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}

// POST /api/chat as multipart; the server runs the council in a detached
// background task and this stream is just an attached viewer.
export async function streamChat({ message, conversationId, files, config, onEvent, signal }) {
  const generation = captureSession()
  const form = new FormData()
  form.append('message', message)
  form.append('session_id', sessionId())
  form.append('conversation_id', conversationId || '')
  form.append('config', JSON.stringify(config))
  for (const f of files) form.append('files', f, f.name)

  const resp = await request('/api/chat', { method: 'POST', body: form, signal })
  if (!resp.ok || !resp.body) {
    throw new Error(`Server error (${resp.status})`)
  }
  await readSSE(resp, onEvent, generation)
}

export async function getActiveRuns() {
  return requestJSON(`/api/runs/active?session_id=${sessionId()}`)
}

// Re-attach to a conversation's run (e.g. after a page reload); replays all
// events from the start, then live-tails until the run finishes.
export async function attachRun(cid, onEvent, signal) {
  const generation = captureSession()
  const resp = await request(`/api/runs/${cid}/stream`, { signal })
  if (!resp.ok || !resp.body) throw new Error(`Server error (${resp.status})`)
  await readSSE(resp, onEvent, generation)
}

export async function stopRun(cid) {
  await request(`/api/runs/${cid}/stop`, { method: 'POST' })
}

export async function getExamples() { return requestJSON('/api/examples') }
export async function startExample(id) { return requestJSON(`/api/examples/${encodeURIComponent(id)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }) }

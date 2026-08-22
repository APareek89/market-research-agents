export function sessionId() {
  let id = localStorage.getItem('mra_session')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('mra_session', id)
  }
  return id
}

export async function getDefaults() {
  const r = await fetch('/api/defaults')
  return r.json()
}

export async function getConversations() {
  const r = await fetch(`/api/conversations?session_id=${sessionId()}`)
  return r.json()
}

export async function getMessages(cid) {
  const r = await fetch(`/api/conversations/${cid}/messages`)
  return r.json()
}

export async function exportReport(format, title, markdown, diagrams = []) {
  const resp = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format, title, markdown, diagrams }),
  })
  if (!resp.ok) throw new Error('Export failed')
  const blob = await resp.blob()
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
  const resp = await fetch('/api/synthesize-prompt', { method: 'POST', body: form })
  const data = await resp.json()
  if (!resp.ok) throw new Error(data.error || 'Synthesis failed')
  return data.prompt
}

// Parse an SSE body, invoking onEvent per data frame (heartbeat comments skipped).
async function readSSE(resp, onEvent) {
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop()
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)))
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

// POST /api/chat as multipart; the server runs the council in a detached
// background task and this stream is just an attached viewer.
export async function streamChat({ message, conversationId, files, config, onEvent, signal }) {
  const form = new FormData()
  form.append('message', message)
  form.append('session_id', sessionId())
  form.append('conversation_id', conversationId || '')
  form.append('config', JSON.stringify(config))
  for (const f of files) form.append('files', f, f.name)

  const resp = await fetch('/api/chat', { method: 'POST', body: form, signal })
  if (!resp.ok || !resp.body) {
    throw new Error(`Server error (${resp.status})`)
  }
  await readSSE(resp, onEvent)
}

export async function getActiveRuns() {
  const r = await fetch(`/api/runs/active?session_id=${sessionId()}`)
  return r.json()
}

// Re-attach to a conversation's run (e.g. after a page reload); replays all
// events from the start, then live-tails until the run finishes.
export async function attachRun(cid, onEvent, signal) {
  const resp = await fetch(`/api/runs/${cid}/stream`, { signal })
  if (!resp.ok || !resp.body) throw new Error(`Server error (${resp.status})`)
  await readSSE(resp, onEvent)
}

export async function stopRun(cid) {
  await fetch(`/api/runs/${cid}/stop`, { method: 'POST' })
}

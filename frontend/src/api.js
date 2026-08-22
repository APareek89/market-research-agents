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

export async function exportReport(format, title, markdown) {
  const resp = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format, title, markdown }),
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

// POST /api/chat as multipart, parse SSE stream, invoke onEvent per event.
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

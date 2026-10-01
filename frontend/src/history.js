// Restore the server's saved trace, rather than inventing a new execution.
export function savedConversationRuns(conversationId, messages) {
  let lastInput = ''
  return messages.flatMap(message => {
    if (message.role === 'user') { lastInput = message.content || ''; return [] }
    const trace = message.trace?.steps
    if (message.role !== 'assistant' || !message.id || !Array.isArray(trace)) return []
    const steps = trace.filter(step => step.node !== 'user')
    if (!steps.length) return []
    const date = new Date(message.created_at)
    return [{
      id: `saved:${conversationId}:${message.id}`, conversationId,
      input: trace.find(step => step.node === 'user')?.output || lastInput,
      at: Number.isNaN(date.getTime()) ? 'Saved conversation' : date.toLocaleString(),
      status: 'saved', cached: steps.every(step => step.cached === true), steps,
    }]
  }).reverse()
}

export function restoreConversationRuns(existing, conversationId, messages) {
  const saved = savedConversationRuns(conversationId, messages)
  if (!saved.length) return existing
  return [...saved, ...existing.filter(run => run.conversationId !== conversationId || ['running', 'error'].includes(run.status))]
}

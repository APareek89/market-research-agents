import React, { useEffect, useRef, useState } from 'react'
import { streamChat, getConversations, getMessages } from '../api.js'
import { renderMd } from '../md.js'

const ACCEPT = '.pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.json,.png,.jpg,.jpeg,.gif,.webp'
const MAX_BYTES = 15 * 1024 * 1024

export default function ChatTab({ config, agents, toggles, setToggles, onRunComplete, onRunUpdate }) {
  const [messages, setMessages] = useState([]) // {role, content, trace?}
  const [input, setInput] = useState('')
  const [files, setFiles] = useState([])
  const [running, setRunning] = useState(false)
  const [plan, setPlan] = useState(null) // {nodes: [...], doneCount}
  const [error, setError] = useState('')
  const [conversationId, setConversationId] = useState(localStorage.getItem('mra_conversation') || '')
  const [convos, setConvos] = useState([])
  const fileRef = useRef(null)
  const bottomRef = useRef(null)

  useEffect(() => { getConversations().then(setConvos).catch(() => {}) }, [])
  useEffect(() => {
    if (!conversationId) return
    getMessages(conversationId)
      .then((msgs) => setMessages(msgs.map((m) => ({ role: m.role, content: m.content, trace: m.trace }))))
      .catch(() => {})
  }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, plan])

  function pickConversation(cid) {
    setConversationId(cid)
    localStorage.setItem('mra_conversation', cid)
    if (!cid) { setMessages([]); return }
    getMessages(cid).then((msgs) => setMessages(msgs.map((m) => ({ role: m.role, content: m.content, trace: m.trace })))).catch(() => {})
  }

  function addFiles(list) {
    const next = [...files]
    for (const f of list) {
      if (f.size > MAX_BYTES) { setError(`${f.name} is over the 15 MB limit.`); continue }
      next.push(f)
    }
    setFiles(next)
  }

  async function send() {
    if (running || (!input.trim() && files.length === 0)) return
    setError('')
    const userText = input.trim() + (files.length ? `\n📎 ${files.map((f) => f.name).join(', ')}` : '')
    setMessages((m) => [...m, { role: 'user', content: userText }])
    const sendFiles = files
    setInput('')
    setFiles([])
    setRunning(true)
    const runId = crypto.randomUUID()
    const run = { id: runId, at: new Date().toLocaleTimeString(), input: userText, steps: [], status: 'running' }
    onRunUpdate({ ...run })
    try {
      await streamChat({
        message: input.trim(),
        conversationId,
        files: sendFiles,
        config,
        onEvent: (ev) => {
          if (ev.type === 'plan') {
            setPlan({ nodes: ev.nodes, done: 0 })
            if (ev.conversation_id) {
              setConversationId(ev.conversation_id)
              localStorage.setItem('mra_conversation', ev.conversation_id)
            }
          } else if (ev.type === 'node_complete') {
            setPlan((p) => (p ? { ...p, done: p.done + 1 } : p))
            run.steps.push(ev)
            onRunUpdate({ ...run })
          } else if (ev.type === 'final') {
            setMessages((m) => [...m, { role: 'assistant', content: ev.output, trace: { steps: ev.trace } }])
            run.status = 'done'
            run.total = ev.total_elapsed
            run.steps = ev.trace.filter((s) => s.node !== 'user')
            onRunComplete && onRunUpdate({ ...run })
            getConversations().then(setConvos).catch(() => {})
          } else if (ev.type === 'error') {
            setError(ev.message)
            run.status = 'error'
            run.error = ev.message
            onRunUpdate({ ...run })
          }
        },
      })
    } catch (e) {
      setError(String(e.message || e))
      run.status = 'error'
      onRunUpdate({ ...run })
    } finally {
      setRunning(false)
      setPlan(null)
    }
  }

  const activeAgents = [
    agents.intake?.name, agents.analyst?.name,
    toggles.reviewer ? agents.reviewer?.name : null,
    toggles.client ? agents.client?.name : null,
  ].filter(Boolean)

  return (
    <div className="chat-layout">
      <div className="chat-top">
        <div className="convo-row">
          <select value={conversationId} onChange={(e) => pickConversation(e.target.value)}>
            <option value="">＋ New chat</option>
            {convos.map((c) => (
              <option key={c.id} value={c.id}>{c.title || c.id.slice(0, 8)}</option>
            ))}
          </select>
          <div className="toggles">
            <label className={toggles.reviewer ? 'toggle on' : 'toggle'}>
              <input type="checkbox" checked={toggles.reviewer}
                onChange={(e) => setToggles({ ...toggles, reviewer: e.target.checked })} />
              <span className="knob" /> {agents.reviewer?.name || 'Reviewer'} <em>(boss review)</em>
            </label>
            <label className={toggles.client ? 'toggle on' : 'toggle'}>
              <input type="checkbox" checked={toggles.client}
                onChange={(e) => setToggles({ ...toggles, client: e.target.checked })} />
              <span className="knob" /> {agents.client?.name || 'Client'} <em>(client review)</em>
            </label>
          </div>
        </div>
        <div className="crew-line">Active crew: {activeAgents.join(' → ')}</div>
      </div>

      <div className="messages">
        {messages.length === 0 && !running && (
          <div className="empty">
            <h2>Ask the council anything market-research.</h2>
            <p>Attach PDFs, decks-as-docx, spreadsheets, CSVs or screenshots (≤15 MB each), drop in URLs, and toggle the reviewers above to control how many rounds of critique your analysis gets.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-who">{m.role === 'user' ? 'You' : agents.analyst?.name || 'Council'}</div>
            {m.role === 'user'
              ? <div className="msg-body plain">{m.content}</div>
              : <div className="msg-body md" dangerouslySetInnerHTML={renderMd(m.content)} />}
          </div>
        ))}
        {running && plan && (
          <div className="progress">
            {plan.nodes.map((n, i) => (
              <div key={n.node} className={`prog-step ${i < plan.done ? 'done' : i === plan.done ? 'active' : ''}`}>
                <span className="dot" />
                <span className="prog-agent">{n.agent}</span>
                <span className="prog-label">{n.label}</span>
                {i === plan.done && <span className="spinner" />}
              </div>
            ))}
          </div>
        )}
        {running && !plan && <div className="progress"><div className="prog-step active"><span className="dot" /><span className="prog-label">Reading your files…</span><span className="spinner" /></div></div>}
        {error && <div className="error-box">⚠ {error}</div>}
        <div ref={bottomRef} />
      </div>

      <div className="composer">
        {files.length > 0 && (
          <div className="chips">
            {files.map((f, i) => (
              <span key={i} className="chip">
                {f.name}
                <button onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button>
              </span>
            ))}
          </div>
        )}
        <div className="composer-row">
          <button className="attach" title="Attach files" onClick={() => fileRef.current?.click()}>📎</button>
          <input ref={fileRef} type="file" multiple accept={ACCEPT} hidden
            onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          <textarea
            value={input}
            placeholder="e.g. Size the market for AI video watermark removal in SEA — here's our pricing sheet…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            rows={2}
          />
          <button className="send" disabled={running || (!input.trim() && !files.length)} onClick={send}>
            {running ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}

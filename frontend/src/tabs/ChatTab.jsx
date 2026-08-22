import React, { useEffect, useRef, useState } from 'react'
import { streamChat, getConversations, getMessages, exportReport } from '../api.js'
import { renderMd } from '../md.js'

const ACCEPT = '.pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.json,.png,.jpg,.jpeg,.gif,.webp'
const MAX_BYTES = 15 * 1024 * 1024

export default function ChatTab({ config, agents, customAgents, toggles, setToggles, onRunUpdate }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [files, setFiles] = useState([])
  const [running, setRunning] = useState(false)
  const [sentFileCount, setSentFileCount] = useState(0)
  const [plan, setPlan] = useState(null)
  const [error, setError] = useState('')
  const [conversationId, setConversationId] = useState(localStorage.getItem('mra_conversation') || '')
  const [convos, setConvos] = useState([])
  const [exporting, setExporting] = useState('')
  const fileRef = useRef(null)
  const bottomRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => { getConversations().then(setConvos).catch(() => {}) }, [])
  useEffect(() => {
    if (!conversationId) return
    getMessages(conversationId)
      .then((msgs) => setMessages(msgs.map((m) => ({ role: m.role, content: m.content, trace: m.trace }))))
      .catch(() => {})
  }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, plan])

  function pickConversation(cid) {
    if (running) return
    setConversationId(cid)
    localStorage.setItem('mra_conversation', cid)
    setError('')
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

  function stop() {
    abortRef.current?.abort()
  }

  async function send() {
    if (running || (!input.trim() && files.length === 0)) return
    setError('')
    const userText = input.trim() + (files.length ? `\n📎 ${files.map((f) => f.name).join(', ')}` : '')
    setMessages((m) => [...m, { role: 'user', content: userText }])
    const sendFiles = files
    setInput('')
    setFiles([])
    setSentFileCount(sendFiles.length)
    setRunning(true)
    const controller = new AbortController()
    abortRef.current = controller
    const runId = crypto.randomUUID()
    const run = { id: runId, at: new Date().toLocaleTimeString(), input: userText, steps: [], status: 'running' }
    onRunUpdate({ ...run })
    let gotFinal = false
    try {
      await streamChat({
        message: input.trim(),
        conversationId,
        files: sendFiles,
        config,
        signal: controller.signal,
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
            gotFinal = true
            setMessages((m) => [...m, { role: 'assistant', content: ev.output, trace: { steps: ev.trace } }])
            run.status = 'done'
            run.total = ev.total_elapsed
            run.steps = ev.trace.filter((s) => s.node !== 'user')
            onRunUpdate({ ...run })
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
      if (e.name === 'AbortError') {
        run.status = 'stopped'
        onRunUpdate({ ...run })
        const partial = run.steps.length
          ? `⏹ Stopped by you after: ${run.steps.map((s) => `${s.agent} (${s.label})`).join(' → ')}. The last completed step is in the Observability tab.`
          : '⏹ Stopped by you before any agent finished.'
        setMessages((m) => [...m, { role: 'assistant', content: partial }])
        getConversations().then(setConvos).catch(() => {})
      } else if (!gotFinal) {
        setError(String(e.message || e))
        run.status = 'error'
        onRunUpdate({ ...run })
      }
    } finally {
      abortRef.current = null
      setRunning(false)
      setPlan(null)
    }
  }

  async function doExport(fmt, content) {
    setExporting(fmt)
    try {
      const title = (messages.find((m) => m.role === 'user')?.content || 'Market research report').split('\n')[0].slice(0, 120)
      await exportReport(fmt, title, content)
    } catch {
      setError('Export failed — try again.')
    } finally {
      setExporting('')
    }
  }

  const enabledCustom = customAgents.filter((c) => (toggles.custom || {})[c.id])
  const activeAgents = [
    agents.intake?.name, agents.analyst?.name,
    toggles.reviewer ? agents.reviewer?.name : null,
    ...enabledCustom.map((c) => c.name || 'Custom'),
    toggles.client ? agents.client?.name : null,
  ].filter(Boolean)

  return (
    <div className="chat-shell">
      <aside className="convo-sidebar">
        <button className="new-chat" disabled={running} onClick={() => pickConversation('')}>＋ New chat</button>
        <div className="convo-list">
          {convos.map((c) => (
            <button
              key={c.id}
              className={c.id === conversationId ? 'convo-item active' : 'convo-item'}
              disabled={running}
              onClick={() => pickConversation(c.id)}
              title={c.title}
            >
              <span className="convo-title">{c.title || 'Untitled'}</span>
              <span className="convo-date">{(c.created_at || '').slice(0, 10)}</span>
            </button>
          ))}
          {convos.length === 0 && <p className="hint pad">Your past chats will appear here.</p>}
        </div>
      </aside>

      <div className="chat-layout">
        <div className="chat-top">
          <div className="toggles">
            <label className={toggles.reviewer ? 'toggle on' : 'toggle'}>
              <input type="checkbox" checked={toggles.reviewer}
                onChange={(e) => setToggles({ ...toggles, reviewer: e.target.checked })} />
              <span className="knob" /> {agents.reviewer?.name || 'Reviewer'} <em>(boss review)</em>
            </label>
            {customAgents.map((c) => (
              <label key={c.id} className={(toggles.custom || {})[c.id] ? 'toggle on custom' : 'toggle custom'}>
                <input type="checkbox" checked={!!(toggles.custom || {})[c.id]}
                  onChange={(e) => setToggles({ ...toggles, custom: { ...(toggles.custom || {}), [c.id]: e.target.checked } })} />
                <span className="knob" /> {c.name || 'Custom'} <em>({c.mode === 'transformer' ? 'transformer' : 'reviewer'})</em>
              </label>
            ))}
            <label className={toggles.client ? 'toggle on' : 'toggle'}>
              <input type="checkbox" checked={toggles.client}
                onChange={(e) => setToggles({ ...toggles, client: e.target.checked })} />
              <span className="knob" /> {agents.client?.name || 'Client'} <em>(client review)</em>
            </label>
          </div>
          <div className="crew-line">Active crew: {activeAgents.join(' → ')}</div>
        </div>

        <div className="messages">
          {messages.length === 0 && !running && (
            <div className="empty">
              <h2>Ask the council anything market-research.</h2>
              <p>Attach PDFs, docs, spreadsheets, CSVs or screenshots (≤15 MB each), drop in URLs, and toggle the reviewers above to control how many rounds of critique your analysis gets. Export any final report as PDF or PPT.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-who">{m.role === 'user' ? 'You' : agents.analyst?.name || 'Council'}</div>
              {m.role === 'user'
                ? <div className="msg-body plain">{m.content}</div>
                : (
                  <div className="msg-body md-wrap">
                    <div className="md" dangerouslySetInnerHTML={renderMd(m.content)} />
                    {m.content.length > 400 && (
                      <div className="export-bar">
                        <span>Want this report as a file?</span>
                        <button disabled={!!exporting} onClick={() => doExport('pdf', m.content)}>
                          {exporting === 'pdf' ? 'Building…' : '⬇ PDF'}
                        </button>
                        <button disabled={!!exporting} onClick={() => doExport('pptx', m.content)}>
                          {exporting === 'pptx' ? 'Building…' : '⬇ PPT'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
            </div>
          ))}
          {running && plan && (
            <div className="progress">
              {plan.nodes.map((n, i) => (
                <div key={n.node} className={`prog-step ${i < plan.done ? 'done' : i === plan.done ? 'active' : ''}`}>
                  <span className="dot" />
                  <span className="prog-agent">{n.agent}</span>
                  <span className="prog-label">{n.label}</span>
                  {n.model && <span className="prog-model">{n.model.replace('claude-', '')}</span>}
                  {i === plan.done && <span className="spinner" />}
                </div>
              ))}
            </div>
          )}
          {running && !plan && <div className="progress"><div className="prog-step active"><span className="dot" /><span className="prog-label">{sentFileCount > 0 ? 'Reading your files…' : 'Briefing the council…'}</span><span className="spinner" /></div></div>}
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
            {running
              ? <button className="send stop" onClick={stop}>■ Stop</button>
              : <button className="send" disabled={!input.trim() && !files.length} onClick={send}>Send</button>}
          </div>
        </div>
      </div>
    </div>
  )
}

import React, { useEffect, useRef, useState } from 'react'
import { streamChat, getConversations, getMessages, exportReport, getActiveRuns, attachRun, stopRun } from '../api.js'
import { MdContent, renderMermaidPngs } from '../md.jsx'

const ACCEPT = '.pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.json,.png,.jpg,.jpeg,.gif,.webp'
const MAX_BYTES = 15 * 1024 * 1024

/* Multi-thread chat: every conversation has its own message list and (optional)
 * live run. Switching threads or starting a new chat NEVER interrupts a run —
 * streams keep writing to their own conversation's state via stable keys. */
export default function ChatTab({ config, agents, customAgents, toggles, setToggles, onRunUpdate }) {
  const [activeConv, setActiveConv] = useState(localStorage.getItem('mra_conversation') || 'new')
  const [chats, setChats] = useState({})   // convKey -> [{role, content, trace}]
  const [runs, setRuns] = useState({})     // convKey -> {plan, done, status, fileCount, error}
  const [convos, setConvos] = useState([])
  const [input, setInput] = useState('')
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState('')
  const controllers = useRef({})           // convKey -> AbortController (viewer stream only)
  const stopFlags = useRef({})             // convKey -> stop requested before real id known
  const reattached = useRef(false)
  const fileRef = useRef(null)
  const bottomRef = useRef(null)

  const messages = chats[activeConv] || []
  const activeRun = runs[activeConv]
  const running = activeRun?.status === 'running'

  useEffect(() => { getConversations().then(setConvos).catch(() => {}) }, [])
  useEffect(() => {
    if (activeConv === 'new' || activeConv.startsWith('tmp-') || chats[activeConv]) return
    getMessages(activeConv)
      .then((msgs) => setChats((c) => ({ ...c, [activeConv]: msgs.map((m) => ({ role: m.role, content: m.content, trace: m.trace })) })))
      .catch(() => {})
  }, [activeConv])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages.length, activeRun?.done])

  // Runs live server-side now: after a reload, re-attach to any still in flight.
  useEffect(() => {
    if (reattached.current) return
    reattached.current = true
    getActiveRuns()
      .then((list) => (list || []).forEach((r) => reattach(r.conversation_id)))
      .catch(() => {})
  }, [])

  function refetchMessages(cid) {
    getMessages(cid)
      .then((msgs) => setChats((c) => ({ ...c, [cid]: msgs.map((m) => ({ role: m.role, content: m.content, trace: m.trace })) })))
      .catch(() => {})
    getConversations().then(setConvos).catch(() => {})
  }

  function reattach(cid) {
    if (controllers.current[cid]) return // this tab is already streaming it
    const controller = new AbortController()
    controllers.current[cid] = controller
    setRuns((r) => ({ ...r, [cid]: { status: 'running', plan: null, done: 0 } }))
    const run = { id: crypto.randomUUID(), at: new Date().toLocaleTimeString(), input: '(rejoined after reload)', steps: [], status: 'running' }
    onRunUpdate({ ...run })
    attachRun(cid, (ev) => {
      if (ev.type === 'plan') {
        setRuns((r) => ({ ...r, [cid]: { ...(r[cid] || {}), plan: ev.nodes, done: 0, status: 'running' } }))
      } else if (ev.type === 'node_complete') {
        setRuns((r) => ({ ...r, [cid]: { ...(r[cid] || {}), done: ((r[cid] || {}).done || 0) + 1 } }))
        run.steps.push(ev)
        onRunUpdate({ ...run })
      } else if (ev.type === 'final' || ev.type === 'stopped') {
        // Message is already persisted server-side — refetch instead of appending.
        refetchMessages(cid)
        run.status = ev.type === 'final' ? 'done' : 'stopped'
        run.total = ev.total_elapsed
        if (ev.trace) run.steps = ev.trace.filter((s) => s.node !== 'user')
        onRunUpdate({ ...run })
      } else if (ev.type === 'error') {
        setRuns((r) => ({ ...r, [cid]: { ...(r[cid] || {}), error: ev.message } }))
        run.status = 'error'
        run.error = ev.message
        onRunUpdate({ ...run })
      }
    }, controller.signal)
      .catch(() => {})
      .finally(() => {
        delete controllers.current[cid]
        setRuns((r) => ({ ...r, [cid]: { ...(r[cid] || {}), status: 'idle', plan: null } }))
      })
  }

  function pickConversation(key) {
    setActiveConv(key)
    setError('')
    localStorage.setItem('mra_conversation', key === 'new' ? '' : key)
  }

  function newChat() {
    pickConversation('new')
  }

  function addFiles(list) {
    const next = [...files]
    for (const f of list) {
      if (f.size > MAX_BYTES) { setError(`${f.name} is over the 15 MB limit.`); continue }
      next.push(f)
    }
    setFiles(next)
  }

  function renameKey(obj, from, to) {
    if (!(from in obj)) return obj
    const { [from]: val, ...rest } = obj
    return { ...rest, [to]: val }
  }

  function stop() {
    // Runs are detached server-side: stopping is an API call, not a fetch abort.
    if (activeConv !== 'new' && !activeConv.startsWith('tmp-')) {
      stopRun(activeConv).catch(() => {})
    } else {
      // Real id not known yet — flag it; the 'conversation' event fires the stop.
      stopFlags.current[activeConv] = true
    }
  }

  async function send() {
    if (running || (!input.trim() && files.length === 0)) return
    setError('')
    // A brand-new chat gets a temp key until the server assigns the real conversation id.
    let convKey = activeConv
    if (convKey === 'new') {
      convKey = `tmp-${crypto.randomUUID().slice(0, 8)}`
      setActiveConv(convKey)
      setConvos((c) => [{ id: convKey, title: input.trim().slice(0, 60) || 'New research', created_at: new Date().toISOString() }, ...c])
    }
    const serverConvId = convKey.startsWith('tmp-') ? '' : convKey
    const userText = input.trim() + (files.length ? `\n📎 ${files.map((f) => f.name).join(', ')}` : '')
    const sendFiles = files
    const msgText = input.trim()
    setChats((c) => ({ ...c, [convKey]: [...(c[convKey] || []), { role: 'user', content: userText }] }))
    setInput('')
    setFiles([])
    const controller = new AbortController()
    controllers.current[convKey] = controller
    setRuns((r) => ({ ...r, [convKey]: { status: 'running', plan: null, done: 0, fileCount: sendFiles.length } }))

    let key = convKey // may migrate tmp -> real id when the plan event arrives
    const runId = crypto.randomUUID()
    const run = { id: runId, at: new Date().toLocaleTimeString(), input: userText, steps: [], status: 'running' }
    onRunUpdate({ ...run })
    let gotFinal = false
    try {
      await streamChat({
        message: msgText,
        conversationId: serverConvId,
        files: sendFiles,
        config,
        signal: controller.signal,
        onEvent: (ev) => {
          const realId = ev.conversation_id
          if ((ev.type === 'conversation' || ev.type === 'plan') && realId && realId !== key) {
            const oldKey = key
            key = realId
            controllers.current[realId] = controllers.current[oldKey]
            delete controllers.current[oldKey]
            setChats((c) => renameKey(c, oldKey, realId))
            setRuns((r) => renameKey(r, oldKey, realId))
            setConvos((c) => c.map((x) => (x.id === oldKey ? { ...x, id: realId } : x)))
            setActiveConv((cur) => (cur === oldKey ? realId : cur))
            if ((localStorage.getItem('mra_conversation') || '') === '' || localStorage.getItem('mra_conversation') === oldKey) {
              localStorage.setItem('mra_conversation', realId)
            }
            if (stopFlags.current[oldKey]) {
              delete stopFlags.current[oldKey]
              stopRun(realId).catch(() => {})
            }
          }
          if (ev.type === 'plan') {
            setRuns((r) => ({ ...r, [key]: { ...(r[key] || {}), plan: ev.nodes, done: 0, status: 'running' } }))
          } else if (ev.type === 'node_complete') {
            setRuns((r) => ({ ...r, [key]: { ...(r[key] || {}), done: ((r[key] || {}).done || 0) + 1 } }))
            run.steps.push(ev)
            onRunUpdate({ ...run })
          } else if (ev.type === 'final') {
            gotFinal = true
            setChats((c) => ({ ...c, [key]: [...(c[key] || []), { role: 'assistant', content: ev.output, trace: { steps: ev.trace } }] }))
            run.status = 'done'
            run.total = ev.total_elapsed
            run.steps = ev.trace.filter((s) => s.node !== 'user')
            onRunUpdate({ ...run })
            getConversations().then(setConvos).catch(() => {})
          } else if (ev.type === 'stopped') {
            gotFinal = true
            // Server persisted the partial message — pull the canonical thread.
            refetchMessages(key)
            run.status = 'stopped'
            if (ev.trace) run.steps = ev.trace
            onRunUpdate({ ...run })
          } else if (ev.type === 'error') {
            setRuns((r) => ({ ...r, [key]: { ...(r[key] || {}), error: ev.message } }))
            run.status = 'error'
            run.error = ev.message
            onRunUpdate({ ...run })
          }
        },
      })
    } catch (e) {
      // The run itself lives server-side; a dropped viewer stream is not a dead
      // run. Only surface real errors when no terminal event arrived.
      if (e.name !== 'AbortError' && !gotFinal) {
        setRuns((r) => ({ ...r, [key]: { ...(r[key] || {}), error: String(e.message || e) } }))
        run.status = 'error'
        onRunUpdate({ ...run })
      }
    } finally {
      delete controllers.current[key]
      delete stopFlags.current[key]
      setRuns((r) => ({ ...r, [key]: { ...(r[key] || {}), status: 'idle', plan: null } }))
    }
  }

  async function doExport(fmt, content) {
    setExporting(fmt)
    try {
      const title = (messages.find((m) => m.role === 'user')?.content || 'Market research report').split('\n')[0].slice(0, 120)
      const diagrams = await renderMermaidPngs(content)
      await exportReport(fmt, title, content, diagrams)
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

  const anyRunning = Object.values(runs).some((r) => r?.status === 'running')

  return (
    <div className="chat-shell">
      <aside className="convo-sidebar">
        <button className="new-chat" onClick={newChat}>＋ New chat</button>
        <div className="convo-list">
          {convos.map((c) => (
            <button
              key={c.id}
              className={c.id === activeConv ? 'convo-item active' : 'convo-item'}
              onClick={() => pickConversation(c.id)}
              title={c.title}
            >
              <span className="convo-title">
                {runs[c.id]?.status === 'running' && <span className="run-dot" title="running" />}
                {c.title || 'Untitled'}
              </span>
              <span className="convo-date">{(c.created_at || '').slice(0, 10)}</span>
            </button>
          ))}
          {convos.length === 0 && <p className="hint pad">Your past chats will appear here.</p>}
        </div>
        {anyRunning && <p className="hint pad">⚡ Runs keep going even if you switch threads or reload the page.</p>}
      </aside>

      <div className="chat-layout">
        <div className="chat-top">
          <div className="toggles">
            <label className={toggles.reviewer ? 'toggle on' : 'toggle'}>
              <input type="checkbox" checked={toggles.reviewer}
                onChange={(e) => setToggles({ ...toggles, reviewer: e.target.checked })} />
              <span className="knob" /> {agents.reviewer?.expert_mode ? '★ ' : ''}{agents.reviewer?.name || 'Reviewer'} <em>(boss review)</em>
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
              <span className="knob" /> {agents.client?.expert_mode ? '★ ' : ''}{agents.client?.name || 'Client'} <em>(client review)</em>
            </label>
          </div>
          <div className="crew-line">Active crew: {activeAgents.join(' → ')}</div>
        </div>

        <div className="messages">
          {messages.length === 0 && !running && (
            <div className="empty">
              <h2>Ask the council anything market-research.</h2>
              <p>Attach PDFs, docs, spreadsheets, CSVs or screenshots (≤15 MB each), drop in URLs, and toggle the reviewers above to control how many rounds of critique your analysis gets. Reports render tables and diagrams, and export to PDF or PPT.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-who">{m.role === 'user' ? 'You' : agents.analyst?.name || 'Council'}</div>
              {m.role === 'user'
                ? <div className="msg-body plain">{m.content}</div>
                : (
                  <div className="msg-body md-wrap">
                    <MdContent text={m.content} />
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
          {running && activeRun?.plan && (
            <div className="progress">
              {activeRun.plan.map((n, i) => (
                <div key={n.node} className={`prog-step ${i < activeRun.done ? 'done' : i === activeRun.done ? 'active' : ''}`}>
                  <span className="dot" />
                  <span className="prog-agent">{n.agent}</span>
                  <span className="prog-label">{n.label}</span>
                  {n.model && <span className="prog-model">{n.model.replace('claude-', '')}</span>}
                  {i === activeRun.done && <span className="spinner" />}
                </div>
              ))}
            </div>
          )}
          {running && !activeRun?.plan && (
            <div className="progress"><div className="prog-step active"><span className="dot" /><span className="prog-label">{activeRun?.fileCount > 0 ? 'Reading your files…' : 'Briefing the council…'}</span><span className="spinner" /></div></div>
          )}
          {(error || activeRun?.error) && <div className="error-box">⚠ {error || activeRun?.error}</div>}
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
              placeholder={running ? 'This thread is running — open another thread or start a new chat…' : 'e.g. Size the market for AI video watermark removal in SEA — here\'s our pricing sheet…'}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              rows={2}
              disabled={running}
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

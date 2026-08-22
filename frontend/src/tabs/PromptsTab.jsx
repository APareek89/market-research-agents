import React, { useRef, useState } from 'react'
import { synthesizePrompt } from '../api.js'

function ConfigureModal({ agentName, agentRole, currentPrompt, settings, onUse, onClose }) {
  const [notes, setNotes] = useState('')
  const [files, setFiles] = useState([])
  const [result, setResult] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef(null)

  async function generate() {
    setBusy(true)
    setError('')
    try {
      const prompt = await synthesizePrompt({ agentName, agentRole, currentPrompt, notes, files, settings })
      setResult(prompt)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <div className="modal-head">
          <h3>⚙ Configure “{agentName}” with AI</h3>
          <button className="ghost" onClick={onClose}>✕ Close</button>
        </div>
        <p className="hint">Describe the real person this agent should emulate — your boss, your client, a domain expert — and/or upload things they've written (review comments, emails, feedback docs). One agent will synthesize it all into a new system prompt for {agentName}.</p>
        <textarea
          className="modal-notes"
          placeholder={'e.g. "My boss Rahul is a former McKinsey EM. He always asks for the so-what first, hates unsourced numbers, pushes on India-specific distribution reality, and ends every review with exactly 3 must-fix items…"'}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <div className="modal-row">
          <button className="ghost" onClick={() => fileRef.current?.click()}>📎 Upload docs ({files.length})</button>
          <input ref={fileRef} type="file" multiple hidden accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg"
            onChange={(e) => { setFiles([...files, ...e.target.files]); e.target.value = '' }} />
          {files.map((f, i) => (
            <span key={i} className="chip">{f.name}<button onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button></span>
          ))}
          <span style={{ flex: 1 }} />
          <button className="save" disabled={busy || (!notes.trim() && !files.length)} onClick={generate}>
            {busy ? 'Synthesizing…' : result ? 'Regenerate' : 'Generate prompt'}
          </button>
        </div>
        {error && <div className="error-box">⚠ {error}</div>}
        {result && (
          <>
            <label className="editor-label">Generated system prompt — review, then apply</label>
            <textarea className="modal-result" value={result} onChange={(e) => setResult(e.target.value)} spellCheck={false} />
            <div className="modal-row">
              <span style={{ flex: 1 }} />
              <button className="save" onClick={() => onUse(result)}>Use this prompt</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const ORDER = [
  ['intake', 'Agent 0'],
  ['analyst', 'Agent 1'],
  ['reviewer', 'Agent 2'],
  ['client', 'Agent 3'],
]

const CUSTOM_TEMPLATE = `<Define the role of this agent — e.g. "You are Devraj, a channel-strategy expert who reviews market research from a go-to-market lens.">

<What it receives: the user's ask, the intake brief, and the current analysis. State what it should focus on — e.g. pricing realism, India-specific distribution, compliance, brand voice.>

<List 3-6 concrete instructions, e.g.:
- Evaluate whether the channel strategy would survive contact with Indian B2B buyers.
- Flag any claim that lacks a source.
- Give max 5 numbered, actionable fixes.>

<Define the output format — e.g. "VERDICT / TOP ISSUES / FIXES". If this agent is a Reviewer, it should give feedback (the analyst revises after it). If it is a Transformer, its output REPLACES the analysis — e.g. "Rewrite the analysis as a 1-page executive memo.">`

function StagePipeline({ agents, customAgents, stageOrder, setStageOrder, toggles }) {
  // Stage keys shown between Astra-draft and the end: reviewer, custom ids, client.
  const known = ['reviewer', ...customAgents.map((c) => String(c.id)), 'client']
  const order = [
    ...stageOrder.filter((k) => known.includes(k)),
    ...known.filter((k) => !stageOrder.includes(k)),
  ]

  function nameOf(key) {
    if (key === 'reviewer') return agents.reviewer?.name || 'Reviewer'
    if (key === 'client') return agents.client?.name || 'Client'
    const c = customAgents.find((x) => String(x.id) === key)
    return c ? (c.name || 'Custom') : key
  }
  function enabledOf(key) {
    if (key === 'reviewer') return toggles.reviewer
    if (key === 'client') return toggles.client
    return !!(toggles.custom || {})[key]
  }
  function move(idx, dir) {
    const next = [...order]
    const j = idx + dir
    if (j < 0 || j >= next.length) return
    ;[next[idx], next[j]] = [next[j], next[idx]]
    setStageOrder(next)
  }

  return (
    <div className="pipeline">
      <div className="pipeline-title">Workflow sequence <span className="hint-inline">— review stages run in this order between the draft and the final analysis; use ◀ ▶ to reorder. Greyed = toggled off in Chat.</span></div>
      <div className="pipeline-bar">
        <span className="pipe-node fixed">{agents.intake?.name || 'Intake'}</span>
        <span className="pipe-arrow">→</span>
        <span className="pipe-node fixed">{agents.analyst?.name || 'Analyst'} draft</span>
        {order.map((key, i) => (
          <React.Fragment key={key}>
            <span className="pipe-arrow">→</span>
            <span className={enabledOf(key) ? 'pipe-node stage' : 'pipe-node stage off'}>
              <button className="pipe-move" title="Move earlier" onClick={() => move(i, -1)}>◀</button>
              {nameOf(key)}
              <button className="pipe-move" title="Move later" onClick={() => move(i, 1)}>▶</button>
            </span>
          </React.Fragment>
        ))}
        <span className="pipe-arrow">→</span>
        <span className="pipe-node fixed">{agents.analyst?.name || 'Analyst'} final</span>
      </div>
    </div>
  )
}

export default function PromptsTab({ agents, defaults, setAgents, customAgents, setCustomAgents, stageOrder, setStageOrder, toggles, setToggles, models, maxCustom, settings }) {
  const [active, setActive] = useState('analyst') // core key or custom id
  const [drafts, setDrafts] = useState({})
  const [configuring, setConfiguring] = useState(false)

  const isCustom = !['intake', 'analyst', 'reviewer', 'client'].includes(active)
  const customAgent = isCustom ? customAgents.find((c) => String(c.id) === active) : null
  const saved = isCustom
    ? (customAgent || { name: '', system_prompt: '', model: 'auto', mode: 'reviewer' })
    : (agents[active] || { name: '', system_prompt: '' })
  const draft = drafts[active] || saved
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  function update(field, value) {
    setDrafts({ ...drafts, [active]: { ...draft, [field]: value } })
  }
  function clearDraft(key) {
    setDrafts((d) => { const c = { ...d }; delete c[key]; return c })
  }

  function save() {
    if (isCustom) {
      setCustomAgents(customAgents.map((c) => (String(c.id) === active ? { ...c, ...draft } : c)))
    } else {
      setAgents({ ...agents, [active]: { ...saved, ...draft } })
    }
    clearDraft(active)
  }

  function resetToDefault() {
    if (isCustom) {
      update('system_prompt', CUSTOM_TEMPLATE)
      return
    }
    setAgents({ ...agents, [active]: { ...defaults[active], model: 'auto' } })
    clearDraft(active)
  }

  function addCustom() {
    if (customAgents.length >= maxCustom) return
    const id = crypto.randomUUID().slice(0, 8)
    const agent = { id, name: `My agent ${customAgents.length + 1}`, system_prompt: CUSTOM_TEMPLATE, model: 'auto', mode: 'reviewer' }
    setCustomAgents([...customAgents, agent])
    // slot into the workflow just before the client stage
    const order = [...stageOrder]
    const ci = order.indexOf('client')
    if (ci === -1) order.push(id); else order.splice(ci, 0, id)
    setStageOrder(order)
    setActive(id)
  }

  function deleteCustom(id) {
    setCustomAgents(customAgents.filter((c) => String(c.id) !== id))
    setStageOrder(stageOrder.filter((k) => k !== id))
    const custom = { ...(toggles.custom || {}) }
    delete custom[id]
    setToggles({ ...toggles, custom })
    clearDraft(id)
    if (active === id) setActive('analyst')
  }

  const claudeModels = models.claude || []

  return (
    <div className="prompts-outer">
      <StagePipeline agents={agents} customAgents={customAgents} stageOrder={stageOrder} setStageOrder={setStageOrder} toggles={toggles} />
      <div className="prompts-layout">
        <aside className="agent-list">
          {ORDER.map(([key, tag]) => {
            const d = drafts[key]
            const isDirty = d && JSON.stringify(d) !== JSON.stringify(agents[key] || {})
            return (
              <button key={key} className={active === key ? 'agent-card active' : 'agent-card'} onClick={() => setActive(key)}>
                <span className="agent-tag">{tag}{isDirty ? ' · unsaved' : ''}</span>
                <span className="agent-name">{(agents[key] || {}).name || key}{isDirty ? ' •' : ''}</span>
                <span className="agent-role">{defaults[key]?.role}</span>
              </button>
            )
          })}
          {customAgents.map((c) => {
            const d = drafts[String(c.id)]
            const isDirty = d && JSON.stringify(d) !== JSON.stringify(c)
            return (
              <button key={c.id} className={active === String(c.id) ? 'agent-card active custom' : 'agent-card custom'} onClick={() => setActive(String(c.id))}>
                <span className="agent-tag">Custom{isDirty ? ' · unsaved' : ''}</span>
                <span className="agent-name">{c.name || 'Custom'}{isDirty ? ' •' : ''}</span>
                <span className="agent-role">{c.mode === 'transformer' ? 'Transformer' : 'Reviewer'} · toggle it on in Chat</span>
              </button>
            )
          })}
          {customAgents.length < maxCustom && (
            <button className="add-agent" onClick={addCustom}>＋ Add your own agent ({customAgents.length}/{maxCustom})</button>
          )}
          <p className="hint">Edits apply after you hit Save, live only in this browser, and shape your very next message. Custom agents appear as toggles in Chat once saved.</p>
        </aside>
        <section className="prompt-editor">
          <div className="editor-head">
            <label>
              Agent name
              <input value={draft.name} onChange={(e) => update('name', e.target.value)} />
            </label>
            <label>
              Model
              <select value={draft.model || 'auto'} onChange={(e) => update('model', e.target.value)}>
                <option value="auto">Auto (recommended)</option>
                {claudeModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            {isCustom && (
              <label>
                Mode
                <select value={draft.mode || 'reviewer'} onChange={(e) => update('mode', e.target.value)}>
                  <option value="reviewer">Reviewer — gives feedback, analyst revises</option>
                  <option value="transformer">Transformer — its output replaces the analysis</option>
                </select>
              </label>
            )}
            <button className="ghost configure" onClick={() => setConfiguring(true)}>⚙ Configure with AI</button>
            <button className="save" disabled={!dirty} onClick={save}>
              {dirty ? 'Save changes' : 'Saved'}
            </button>
            {dirty && <button className="ghost" onClick={() => clearDraft(active)}>Discard edits</button>}
            <button className="ghost" onClick={resetToDefault}>{isCustom ? 'Insert template' : 'Reset to default'}</button>
            {isCustom && <button className="ghost danger" onClick={() => deleteCustom(active)}>Delete agent</button>}
          </div>
          <label className="editor-label">
            System prompt — {isCustom ? `${draft.name || 'Custom agent'} (yours)` : defaults[active]?.role}
            {dirty && <span className="unsaved-tag"> · unsaved changes</span>}
          </label>
          <textarea
            className="prompt-area"
            value={draft.system_prompt}
            onChange={(e) => update('system_prompt', e.target.value)}
            placeholder={CUSTOM_TEMPLATE}
            spellCheck={false}
          />
          {isCustom && <p className="hint">Model note: with an OpenAI or HF key in Settings, all agents run on that provider's chosen model. Per-agent models apply on Claude.</p>}
        </section>
      </div>
      {configuring && (
        <ConfigureModal
          agentName={draft.name || 'this agent'}
          agentRole={isCustom ? `${draft.mode === 'transformer' ? 'Transformer' : 'Reviewer'} (custom agent)` : defaults[active]?.role}
          currentPrompt={draft.system_prompt}
          settings={settings}
          onUse={(prompt) => { update('system_prompt', prompt); setConfiguring(false) }}
          onClose={() => setConfiguring(false)}
        />
      )}
    </div>
  )
}

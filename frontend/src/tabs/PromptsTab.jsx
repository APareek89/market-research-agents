import React, { useState } from 'react'

const ORDER = [
  ['intake', 'Agent 0'],
  ['analyst', 'Agent 1'],
  ['reviewer', 'Agent 2'],
  ['client', 'Agent 3'],
]

export default function PromptsTab({ agents, defaults, setAgents }) {
  const [active, setActive] = useState('analyst')
  const [drafts, setDrafts] = useState({}) // key -> {name, system_prompt} while editing

  const agent = agents[active] || { name: '', system_prompt: '' }
  const draft = drafts[active] || agent
  const dirty = draft.name !== agent.name || draft.system_prompt !== agent.system_prompt

  function update(field, value) {
    setDrafts({ ...drafts, [active]: { ...draft, [field]: value } })
  }

  function clearDraft(key) {
    setDrafts((d) => { const c = { ...d }; delete c[key]; return c })
  }

  function save() {
    setAgents({ ...agents, [active]: { ...agent, name: draft.name, system_prompt: draft.system_prompt } })
    clearDraft(active)
  }

  function resetToDefault() {
    setAgents({ ...agents, [active]: { ...defaults[active] } })
    clearDraft(active)
  }

  return (
    <div className="prompts-layout">
      <aside className="agent-list">
        {ORDER.map(([key, tag]) => {
          const d = drafts[key]
          const isDirty = d && (d.name !== (agents[key] || {}).name || d.system_prompt !== (agents[key] || {}).system_prompt)
          return (
            <button key={key} className={active === key ? 'agent-card active' : 'agent-card'} onClick={() => setActive(key)}>
              <span className="agent-tag">{tag}{isDirty ? ' · unsaved' : ''}</span>
              <span className="agent-name">{(agents[key] || {}).name || key}{isDirty ? ' •' : ''}</span>
              <span className="agent-role">{defaults[key]?.role}</span>
            </button>
          )
        })}
        <p className="hint">Edits apply after you hit Save, live only in this browser, and shape your very next message. Other visitors keep the defaults.</p>
      </aside>
      <section className="prompt-editor">
        <div className="editor-head">
          <label>
            Agent name
            <input value={draft.name} onChange={(e) => update('name', e.target.value)} />
          </label>
          <button className="save" disabled={!dirty} onClick={save}>
            {dirty ? 'Save changes' : 'Saved'}
          </button>
          {dirty && <button className="ghost" onClick={() => clearDraft(active)}>Discard edits</button>}
          <button className="ghost" onClick={resetToDefault}>Reset to default</button>
        </div>
        <label className="editor-label">
          System prompt — {defaults[active]?.role}
          {dirty && <span className="unsaved-tag"> · unsaved changes</span>}
        </label>
        <textarea
          className="prompt-area"
          value={draft.system_prompt}
          onChange={(e) => update('system_prompt', e.target.value)}
          spellCheck={false}
        />
      </section>
    </div>
  )
}

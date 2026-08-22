import React, { useState } from 'react'

const ORDER = [
  ['intake', 'Agent 0'],
  ['analyst', 'Agent 1'],
  ['reviewer', 'Agent 2'],
  ['client', 'Agent 3'],
]

export default function PromptsTab({ agents, defaults, setAgents }) {
  const [active, setActive] = useState('analyst')
  const agent = agents[active] || { name: '', role: '', system_prompt: '' }

  function update(field, value) {
    setAgents({ ...agents, [active]: { ...agent, [field]: value } })
  }

  return (
    <div className="prompts-layout">
      <aside className="agent-list">
        {ORDER.map(([key, tag]) => (
          <button key={key} className={active === key ? 'agent-card active' : 'agent-card'} onClick={() => setActive(key)}>
            <span className="agent-tag">{tag}</span>
            <span className="agent-name">{agents[key]?.name || key}</span>
            <span className="agent-role">{defaults[key]?.role}</span>
          </button>
        ))}
        <p className="hint">Edits save automatically in this browser and apply to your very next message. Other visitors keep the defaults.</p>
      </aside>
      <section className="prompt-editor">
        <div className="editor-head">
          <label>
            Agent name
            <input value={agent.name} onChange={(e) => update('name', e.target.value)} />
          </label>
          <button className="ghost" onClick={() => setAgents({ ...agents, [active]: { ...defaults[active] } })}>
            Reset to default
          </button>
        </div>
        <label className="editor-label">System prompt — {defaults[active]?.role}</label>
        <textarea
          className="prompt-area"
          value={agent.system_prompt}
          onChange={(e) => update('system_prompt', e.target.value)}
          spellCheck={false}
        />
      </section>
    </div>
  )
}

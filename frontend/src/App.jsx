import React, { useEffect, useMemo, useState } from 'react'
import ChatTab from './tabs/ChatTab.jsx'
import PromptsTab from './tabs/PromptsTab.jsx'
import ObservabilityTab from './tabs/ObservabilityTab.jsx'
import SettingsTab from './tabs/SettingsTab.jsx'
import { getDefaults } from './api.js'

const TABS = [
  { id: 'chat', label: 'Chat' },
  { id: 'prompts', label: 'Agents & Prompts' },
  { id: 'observability', label: 'Observability' },
  { id: 'settings', label: 'API & Model' },
]

function load(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem(key))
    return v ?? fallback
  } catch {
    return fallback
  }
}

export default function App() {
  const [tab, setTab] = useState('chat')
  const [defaults, setDefaults] = useState(null)
  const [agents, setAgents] = useState(() => load('mra_agents', null))
  const [toggles, setToggles] = useState(() => load('mra_toggles', { reviewer: true, client: true }))
  const [settings, setSettings] = useState(() => load('mra_settings', { provider: 'claude', model: '', api_key: '' }))
  const [runs, setRuns] = useState([]) // observability: this session's runs

  useEffect(() => {
    getDefaults()
      .then((d) => {
        setDefaults(d)
        // Server prompt upgrades replace cached prompts (incl. user edits) once per version bump.
        const seenVersion = localStorage.getItem('mra_prompts_v')
        if (String(d.prompts_version) !== seenVersion) {
          localStorage.setItem('mra_prompts_v', String(d.prompts_version))
          setAgents(d.agents)
        } else {
          setAgents((cur) => cur || d.agents)
        }
        setSettings((cur) => {
          let s = cur.model ? cur : { ...cur, model: d.default_model }
          // One-time migration to the per-agent "auto" default (Claude only).
          if ((s.mv || 0) < 2) s = { ...s, model: s.provider === 'openai' ? s.model : 'auto', mv: 2 }
          return s
        })
      })
      .catch(() => setDefaults({ error: true }))
  }, [])

  useEffect(() => { if (agents) localStorage.setItem('mra_agents', JSON.stringify(agents)) }, [agents])
  useEffect(() => { localStorage.setItem('mra_toggles', JSON.stringify(toggles)) }, [toggles])
  useEffect(() => { localStorage.setItem('mra_settings', JSON.stringify(settings)) }, [settings])

  const config = useMemo(
    () => ({
      agents,
      enable_reviewer: toggles.reviewer,
      enable_client: toggles.client,
      settings,
    }),
    [agents, toggles, settings],
  )

  if (!defaults) return <div className="boot">Loading the council…</div>

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <span className="brand-name">Agent Council</span>
          <span className="brand-sub">market research, sharpened by review</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="content">
        {tab === 'chat' && (
          <ChatTab
            config={config}
            agents={agents || {}}
            toggles={toggles}
            setToggles={setToggles}
            onRunComplete={(run) => setRuns((r) => [run, ...r])}
            onRunUpdate={(run) => setRuns((r) => { const i = r.findIndex((x) => x.id === run.id); if (i === -1) return [run, ...r]; const c = [...r]; c[i] = run; return c })}
          />
        )}
        {tab === 'prompts' && (
          <PromptsTab agents={agents || {}} defaults={defaults.agents} setAgents={setAgents} />
        )}
        {tab === 'observability' && <ObservabilityTab runs={runs} />}
        {tab === 'settings' && (
          <SettingsTab settings={settings} setSettings={setSettings} defaults={defaults} />
        )}
      </main>
    </div>
  )
}

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
  const [customAgents, setCustomAgents] = useState(() => load('mra_custom_agents', []))
  const [stageOrder, setStageOrder] = useState(() => load('mra_stage_order', ['reviewer', 'client']))
  const [toggles, setToggles] = useState(() => load('mra_toggles', { reviewer: true, client: true, custom: {} }))
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
  useEffect(() => { localStorage.setItem('mra_custom_agents', JSON.stringify(customAgents)) }, [customAgents])
  useEffect(() => { localStorage.setItem('mra_stage_order', JSON.stringify(stageOrder)) }, [stageOrder])
  useEffect(() => { localStorage.setItem('mra_toggles', JSON.stringify(toggles)) }, [toggles])
  useEffect(() => { localStorage.setItem('mra_settings', JSON.stringify(settings)) }, [settings])

  const config = useMemo(
    () => ({
      agents,
      custom_agents: customAgents.map((c) => ({ ...c, enabled: !!(toggles.custom || {})[c.id] })),
      stage_order: stageOrder,
      enable_reviewer: toggles.reviewer,
      enable_client: toggles.client,
      settings,
    }),
    [agents, customAgents, stageOrder, toggles, settings],
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
        {/* All tabs stay mounted so a running chat survives tab switches. */}
        <div className={tab === 'chat' ? 'tab-pane' : 'tab-pane hidden'}>
          <ChatTab
            config={config}
            agents={agents || {}}
            customAgents={customAgents}
            toggles={toggles}
            setToggles={setToggles}
            onRunUpdate={(run) => setRuns((r) => { const i = r.findIndex((x) => x.id === run.id); if (i === -1) return [run, ...r]; const c = [...r]; c[i] = run; return c })}
          />
        </div>
        <div className={tab === 'prompts' ? 'tab-pane' : 'tab-pane hidden'}>
          <PromptsTab
            agents={agents || {}}
            defaults={defaults.agents}
            setAgents={setAgents}
            customAgents={customAgents}
            setCustomAgents={setCustomAgents}
            stageOrder={stageOrder}
            setStageOrder={setStageOrder}
            toggles={toggles}
            setToggles={setToggles}
            models={defaults.models || { claude: [] }}
            maxCustom={defaults.max_custom_agents || 3}
            settings={settings}
          />
        </div>
        <div className={tab === 'observability' ? 'tab-pane' : 'tab-pane hidden'}>
          <ObservabilityTab runs={runs} />
        </div>
        <div className={tab === 'settings' ? 'tab-pane' : 'tab-pane hidden'}>
          <SettingsTab settings={settings} setSettings={setSettings} defaults={defaults} />
        </div>
      </main>
    </div>
  )
}

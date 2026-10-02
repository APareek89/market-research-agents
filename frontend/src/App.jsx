import React, { useEffect, useMemo, useState } from 'react'
import ChatTab from './tabs/ChatTab.jsx'
import PromptsTab from './tabs/PromptsTab.jsx'
import ObservabilityTab from './tabs/ObservabilityTab.jsx'
import SettingsTab from './tabs/SettingsTab.jsx'
import { getDefaults } from './api.js'
import AccountGate, { Brand, ThemeButton } from './AccountGate.jsx'
import { storageKey } from './session.js'
import { restoreConversationRuns } from './history.js'
import {loadPreference,readPreference,writePreference} from './preferences.js'

const TABS = [
  { id: 'chat', label: 'Chat' },
  { id: 'prompts', label: 'Agents & Prompts' },
  { id: 'observability', label: 'Observability' },
  { id: 'settings', label: 'API & Model' },
]

export default function App() {
  return <AccountGate>{account => <Workspace key={account.user?.id || 'local-fixture'} account={account} />}</AccountGate>
}

function Workspace({ account }) {
  const owner = account.user?.id || 'local-fixture'
  const pref = name => storageKey(owner, name)
  const [accountError, setAccountError] = useState('')
  const [tab, setTab] = useState('chat')
  const [defaults, setDefaults] = useState(null)
  const [agents, setAgents] = useState(() => loadPreference(pref('agents'), 'agents', null))
  const [customAgents, setCustomAgents] = useState(() => loadPreference(pref('custom_agents'), 'custom_agents', []))
  const [stageOrder, setStageOrder] = useState(() => loadPreference(pref('stage_order'), 'stage_order', ['reviewer', 'client']))
  const [toggles, setToggles] = useState(() => loadPreference(pref('toggles'), 'toggles', { reviewer: true, client: true, custom: {} }))
  const [settings, setSettings] = useState(() => { const saved = loadPreference(pref('settings'), 'settings', {}); return { provider: saved.provider || '', model: saved.model || '', api_key: '' } })
  const [runs, setRuns] = useState([]) // live runs plus traces restored from selected history

  useEffect(() => {
    getDefaults()
      .then((d) => {
        setDefaults(d)
        // Server prompt upgrades replace cached prompts (incl. user edits) once per version bump.
        const seenVersion = readPreference(pref('prompts_v'))
        if (String(d.prompts_version) !== seenVersion) {
          writePreference(pref('prompts_v'), String(d.prompts_version))
          setAgents(d.agents)
        } else {
          setAgents((cur) => cur || d.agents)
        }
        setSettings((cur) => {
          const provider = cur.provider || d.default_provider || 'claude'
          return { ...cur, provider, model: cur.model || (provider === d.default_provider ? d.default_model : provider === 'claude' ? 'auto' : d.models?.[provider]?.[0] || '') }
        })
      })
      .catch(() => setDefaults({ error: true }))
  }, [])

  useEffect(() => { if (agents) writePreference(pref('agents'), JSON.stringify(agents)) }, [agents])
  useEffect(() => { writePreference(pref('custom_agents'), JSON.stringify(customAgents)) }, [customAgents])
  useEffect(() => { writePreference(pref('stage_order'), JSON.stringify(stageOrder)) }, [stageOrder])
  useEffect(() => { writePreference(pref('toggles'), JSON.stringify(toggles)) }, [toggles])
  useEffect(() => { writePreference(pref('settings'), JSON.stringify({ provider: settings.provider, model: settings.model })) }, [settings])

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

  if (!defaults) return <div className="boot" role="status">Loading the council…</div>
  if (defaults.error) return <main className="account-retry"><h1>The council is unavailable.</h1><p>Reload to try again.</p><button className="save" onClick={() => location.reload()}>Reload</button></main>

  return (
    <div className="shell">
      <header className="topbar">
        <Brand />
        <div className="account-actions"><span className="account-email" title={account.user?.email}>{account.user?.email || 'Local fixture'}</span><ThemeButton theme={account.theme} setTheme={account.setTheme} />
          {account.enabled && <button className="ghost" onClick={() => account.signOut().catch(e => setAccountError(e.message))}>Sign out</button>}
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'tab active' : 'tab'} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      {accountError && <p className="error-box" role="alert">{accountError}</p>}
      <main className="content">
        {/* All tabs stay mounted so a running chat survives tab switches. */}
        <div className={tab === 'chat' ? 'tab-pane' : 'tab-pane hidden'}>
          <ChatTab
            owner={owner}
            config={config}
            agents={agents || {}}
            customAgents={customAgents}
            toggles={toggles}
            setToggles={setToggles}
            onRunUpdate={(run) => setRuns((r) => { const i = r.findIndex((x) => x.id === run.id); if (i === -1) return [run, ...r]; const c = [...r]; c[i] = run; return c })}
            onHistoryRestore={(cid, messages) => setRuns(r => restoreConversationRuns(r, cid, messages))}
          />
        </div>
        <div className={tab === 'prompts' ? 'tab-pane' : 'tab-pane hidden'}>
          <PromptsTab
            agents={agents || {}}
            defaults={defaults.agents}
            expertAgents={defaults.expert_agents || {}}
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

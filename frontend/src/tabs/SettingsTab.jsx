import React from 'react'

export default function SettingsTab({ settings, setSettings, defaults }) {
  const models = defaults.models || { claude: [], openai: [] }
  const provider = settings.provider || 'claude'

  function setProvider(p) {
    setSettings({ ...settings, provider: p, model: (models[p] || [])[0] || '' })
  }

  return (
    <div className="settings-layout">
      <h2>API & model</h2>
      <p className="hint">
        By default the app runs on the host's Claude API key. Bring your own key to use OpenAI models
        or to run on your own Claude quota. Keys live only in this browser and are sent with each
        request — the server never stores them.
      </p>

      <div className="field">
        <label>Provider</label>
        <div className="seg">
          <button className={provider === 'claude' ? 'on' : ''} onClick={() => setProvider('claude')}>Claude</button>
          <button className={provider === 'openai' ? 'on' : ''} onClick={() => setProvider('openai')}>OpenAI (GPT)</button>
        </div>
      </div>

      <div className="field">
        <label>Model</label>
        <select value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })}>
          {(models[provider] || []).map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>
          API key {provider === 'claude'
            ? <em>(optional — blank uses the host's default key{defaults.server_key_available ? '' : ' — NOT configured on this server!'})</em>
            : <em>(required for OpenAI)</em>}
        </label>
        <input
          type="password"
          placeholder={provider === 'claude' ? 'sk-ant-… (optional)' : 'sk-…'}
          value={settings.api_key}
          onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
          autoComplete="off"
        />
      </div>

      <div className="field">
        <label>Storage</label>
        <p className="hint">Conversation memory: <code>{defaults.db}</code></p>
      </div>
    </div>
  )
}

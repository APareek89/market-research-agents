import React from 'react'

export default function SettingsTab({ settings, setSettings, defaults }) {
  const models = defaults.models || { claude: [], openai: [], hf: [] }
  const provider = settings.provider || 'claude'

  function setProvider(p) {
    const model = p === 'claude' ? 'auto' : (models[p] || [])[0] || ''
    setSettings({ ...settings, provider: p, model })
  }

  const amd = defaults.agent_model_defaults || {}
  const autoLabel = `Auto — fast mix (${(amd.intake || 'haiku').replace('claude-', '')} intake · ${(amd.analyst || 'sonnet').replace('claude-', '')} analyst · ${(amd.reviewer || 'opus').replace('claude-', '')} reviewers)`

  return (
    <div className="settings-layout">
      <h2>API & model</h2>
      <p className="hint">
        By default the app runs on the host's Claude API key. Bring your own key to use OpenAI or
        Hugging Face models, or to run on your own Claude quota. Keys live only in this browser and
        are sent with each request — the server never stores them.
      </p>

      <div className="field">
        <label>Provider</label>
        <div className="seg">
          <button className={provider === 'claude' ? 'on' : ''} onClick={() => setProvider('claude')}>Claude</button>
          <button className={provider === 'openai' ? 'on' : ''} onClick={() => setProvider('openai')}>OpenAI (GPT)</button>
          <button className={provider === 'hf' ? 'on' : ''} onClick={() => setProvider('hf')}>Hugging Face</button>
        </div>
      </div>

      {provider !== 'hf' && (
        <div className="field">
          <label>Model</label>
          <select value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })}>
            {provider === 'claude' && <option value="auto">{autoLabel}</option>}
            {(models[provider] || []).map((m) => (
              <option key={m} value={m}>{m} (all agents)</option>
            ))}
          </select>
        </div>
      )}

      {provider === 'hf' && (
        <>
          <div className="field">
            <label>Model — popular picks</label>
            <select
              value={(models.hf || []).includes(settings.model) ? settings.model : ''}
              onChange={(e) => e.target.value && setSettings({ ...settings, model: e.target.value })}
            >
              <option value="">— pick a preset or type any id below —</option>
              {(models.hf || []).map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="field">
            <label>…or any Hugging Face model id <em>(served via HF Inference Providers router)</em></label>
            <input
              type="text"
              placeholder="e.g. meta-llama/Llama-3.3-70B-Instruct"
              value={settings.model}
              onChange={(e) => setSettings({ ...settings, model: e.target.value })}
              autoComplete="off"
            />
            <p className="hint">Heads-up: the analyst's web tools need a model with solid function-calling support — the presets above have it. Exotic models may skip research.</p>
          </div>
        </>
      )}

      <div className="field">
        <label>
          {provider === 'hf' ? 'HF token ' : 'API key '}
          {provider === 'claude'
            ? <em>(optional — blank uses the host's default key{defaults.server_key_available ? '' : ' — NOT configured on this server!'})</em>
            : <em>(required — {provider === 'hf' ? 'get one at hf.co/settings/tokens' : 'required for OpenAI'})</em>}
        </label>
        <input
          type="password"
          placeholder={provider === 'claude' ? 'sk-ant-… (optional)' : provider === 'hf' ? 'hf_…' : 'sk-…'}
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

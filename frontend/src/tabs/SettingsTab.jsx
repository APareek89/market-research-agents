import React from 'react'

export default function SettingsTab({ settings, setSettings, defaults }) {
  const models = defaults.models || { claude: [], openai: [], hf: [] }
  const provider = settings.provider || defaults.default_provider || 'claude'
  const hostedDefault = provider === defaults.default_provider && defaults.server_key_available

  function setProvider(p) {
    const model = p === defaults.default_provider ? defaults.default_model : p === 'claude' ? 'auto' : (models[p] || [])[0] || ''
    setSettings({ ...settings, provider: p, model, api_key: '' })
  }

  const amd = defaults.agent_model_defaults || {}
  const autoLabel = `Auto — fast mix (${(amd.intake || 'haiku').replace('claude-', '')} intake · ${(amd.analyst || 'sonnet').replace('claude-', '')} analyst · ${(amd.reviewer || 'opus').replace('claude-', '')} reviewers)`

  return (
    <div className="settings-layout">
      <h2>API & model</h2>
      <p className="hint">
        The configured provider is {defaults.default_provider || 'unavailable'}. Use it when available, or bring your own key. Keys stay only in this signed-in page’s memory and are sent with your research request; they are removed on signout or reload and never saved in browser storage.
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
          <select aria-label="Model" value={settings.model} onChange={(e) => setSettings({ ...settings, model: e.target.value })}>
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
              aria-label="Hugging Face model preset"
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
              aria-label="Hugging Face model ID"
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
          {hostedDefault ? <em>(optional — blank uses the configured provider)</em> : <em>(required for this provider)</em>}
        </label>
        <input
          type="password"
          aria-label="Provider API key"
          placeholder={provider === 'claude' ? 'sk-ant-…' : provider === 'hf' ? 'hf_…' : 'sk-…'}
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

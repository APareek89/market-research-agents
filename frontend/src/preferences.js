// Browser preferences are untrusted and optional. They must never prevent boot
// or restore an API key; authorization and saved conversations stay server-owned.
export function readPreference(key) { try { return localStorage.getItem(key) } catch { return null } }
export function writePreference(key, value) { try { localStorage.setItem(key, value) } catch { /* page state remains usable */ } }
export function removePreference(key) { try { localStorage.removeItem(key) } catch { /* storage may be disabled */ } }
const object = value => value && typeof value === 'object' && !Array.isArray(value)
const text = (value, cap) => typeof value === 'string' && value.length <= cap
const id = value => text(value,64) && /^[A-Za-z0-9_-]+$/.test(value)
const agent = value => object(value) && text(value.name,80) && text(value.system_prompt,12000) && (value.model == null || text(value.model,160)) && (value.expert_mode == null || typeof value.expert_mode === 'boolean')
export function loadPreference(key, kind, fallback) {
  let value; try { value=JSON.parse(readPreference(key)) } catch { return fallback }
  if (kind === 'agents') return object(value) && ['intake','analyst','reviewer','client'].every(k => agent(value[k])) ? Object.fromEntries(['intake','analyst','reviewer','client'].map(k => [k,value[k]])) : fallback
  if (kind === 'custom_agents') return Array.isArray(value) && value.length <= 3 && value.every(c => agent(c) && id(c.id) && !['intake','analyst','reviewer','client'].includes(c.id) && ['reviewer','transformer'].includes(c.mode || 'reviewer')) && new Set(value.map(c=>c.id)).size === value.length ? value : fallback
  if (kind === 'stage_order') return Array.isArray(value) && value.length <= 5 && value.every(id) && new Set(value).size === value.length ? value : fallback
  if (kind === 'toggles') return object(value) && typeof value.reviewer === 'boolean' && typeof value.client === 'boolean' && object(value.custom) && Object.values(value.custom).every(v => typeof v === 'boolean') ? value : fallback
  if (kind === 'settings') return object(value) ? { provider: ['claude','openai','hf'].includes(value.provider) ? value.provider : '', model: text(value.model,160) ? value.model : '' } : fallback
  return fallback
}

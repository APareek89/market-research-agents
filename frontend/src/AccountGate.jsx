import {readPreference,writePreference} from './preferences.js'
import React, { useEffect, useRef, useState } from 'react'
import { ArrowRight, Loader2, Moon, Network, Sun } from 'lucide-react'
import { readSession, acceptSession, request, removeLegacyPreferences } from './session.js'

export function ThemeButton({ theme, setTheme }) {
  return <button className="icon-button" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
    {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
  </button>
}
export function Brand() {
  return <div className="brand"><Network size={22} aria-hidden="true" /><span className="brand-name">Market Research</span><span className="brand-sub">Agent Council</span></div>
}
export default function AccountGate({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [theme, setTheme] = useState(() => readPreference('mra_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  const epoch = useRef(0)
  function apply(value) { acceptSession(value); setSession(value); setError(''); removeLegacyPreferences() }
  async function refresh() {
    const ticket = ++epoch.current
    try { const value = await readSession(); if (ticket === epoch.current) { apply(value); return true } }
    catch (e) { if (ticket === epoch.current) setError(e.message); return false }
    finally { if (ticket === epoch.current) setLoading(false) }
  }
  useEffect(() => {
    document.documentElement.classList.add('lovable-ui')
    document.documentElement.dataset.theme = theme
    writePreference('mra_theme', theme)
    window.dispatchEvent(new Event('mra-theme-change'))
  }, [theme])
  useEffect(() => {
    refresh()
    const expired = () => { epoch.current++; setSession(null); setLoading(true); refresh() }
    window.addEventListener('mra-session-expired', expired)
    window.addEventListener('focus', refresh)
    return () => { epoch.current++; window.removeEventListener('mra-session-expired', expired); window.removeEventListener('focus', refresh) }
  }, [])
  async function signOut() {
    await request('/api/auth/signout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    epoch.current++
    acceptSession({ enabled: true, user: null })
    setSession(null); setLoading(true)
    await refresh()
  }
  if (!loading && session && (!session.enabled || session.user)) return children({ ...session, theme, setTheme, signOut })
  return <div className="account-shell">
    <header className="topbar"><Brand /><ThemeButton theme={theme} setTheme={setTheme} /></header>
    {loading ? <main className="boot" role="status"><Loader2 className="spin" size={24} /><p>Opening your workspace…</p></main>
      : !session ? <main className="account-retry"><h1>Your workspace is unavailable.</h1><p role="alert">{error}</p><button className="save" onClick={() => { setLoading(true); refresh() }}>Try again</button></main>
      : <SignIn onSuccess={refresh} />}
  </div>
}
function SignIn({ onSuccess }) {
  const [signup, setSignup] = useState(false), [email, setEmail] = useState(''), [password, setPassword] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function submit(e) {
    e.preventDefault(); if (busy) return; setBusy(true); setError('')
    try {
      await request(`/api/auth/${signup ? 'signup' : 'signin'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
      if (!await onSuccess()) throw new Error('Signed in, but your workspace could not load. Please try again.')
    } catch (e) { setError(e.message) } finally { setBusy(false); setPassword('') }
  }
  return <main className="account-layout">
    <section className="account-intro"><span className="eyebrow">A council for clearer decisions</span><h1>Research.<br />Review.<br />Decide.</h1><p>Scout frames the question. Astra develops the analysis. Vera and Cleo challenge it before the final report.</p><div className="account-note"><Network size={20} /><span>Try three prepared examples for free, then bring your own question and sources.</span></div></section>
    <section className="account-card"><h2>{signup ? 'Create your workspace' : 'Welcome back'}</h2><p className="hint">{signup ? 'Keep your conversations and research in your own account.' : 'Sign in to continue your research.'}</p>
      <form onSubmit={submit}><label htmlFor="account-email">Email</label><input id="account-email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} disabled={busy} />
        <label htmlFor="account-password">Password</label><input id="account-password" type="password" required minLength={signup ? 12 : undefined} maxLength={72} autoComplete={signup ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
        {signup && <p className="hint">Use at least 12 characters.</p>}{error && <p className="error-box" role="alert">{error}</p>}
        <button className="save" disabled={busy} aria-busy={busy}>{busy ? <Loader2 className="spin" size={16} /> : <ArrowRight size={16} />}{busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button>
      </form><button className="account-switch" disabled={busy} onClick={() => { setSignup(!signup); setError(''); setPassword('') }}>{signup ? 'Already have an account? Sign in' : 'New here? Create an account'}</button><p className="hint account-limit">Email and password only. Google sign-in and email password recovery are not configured.</p>
    </section>
  </main>
}

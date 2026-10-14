import { useState } from 'react'
import Logo from './Logo.jsx'

async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Something went wrong. Please try again.')
  return data.user
}

export default function Auth({ onAuthed, initialMode = 'signin' }) {
  const [mode, setMode] = useState(initialMode)
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const signup = mode === 'signup'
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const run = async (fn) => {
    setBusy(true); setErr(null)
    try { onAuthed(await fn()) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const submit = (e) => {
    e.preventDefault()
    run(() => post(signup ? '/api/auth/signup' : '/api/auth/signin', signup ? form : { email: form.email, password: form.password }))
  }

  return (
    <div className="auth">
      <a className="auth-home" href="https://spyra.si"><Logo size={30} /></a>
      <div className="auth-card">
        <div className="auth-tabs" role="tablist">
          {[['signin', 'Sign in'], ['signup', 'Sign up']].map(([k, label]) => (
            <button key={k} role="tab" aria-selected={mode === k} className={mode === k ? 'on' : ''} type="button"
              onClick={() => { setMode(k); setErr(null) }}>{label}</button>
          ))}
        </div>
        <h1>{signup ? 'Create your account' : 'Welcome back'}</h1>
        <p className="auth-sub">{signup ? 'Free to start. Test your first ad in minutes.' : 'Sign in to test your ads against real competitors.'}</p>

        <form onSubmit={submit}>
          {signup && (
            <label>Name<input autoComplete="name" value={form.name} onChange={set('name')} required minLength={2} placeholder="Your name" /></label>
          )}
          <label>Email<input type="email" autoComplete="email" value={form.email} onChange={set('email')} required placeholder="you@company.com" /></label>
          <label>Password
            <input type="password" autoComplete={signup ? 'new-password' : 'current-password'} value={form.password} onChange={set('password')}
              required minLength={signup ? 8 : 1} placeholder={signup ? 'At least 8 characters' : 'Your password'} />
          </label>
          {err && <div className="auth-err" role="alert">{err}</div>}
          <button className="b-btn primary" disabled={busy}>{busy ? 'Please wait…' : signup ? 'Create account →' : 'Sign in →'}</button>
        </form>

        <div className="auth-or"><span>or</span></div>
        <button className="b-btn demo" type="button" disabled={busy} onClick={() => run(() => post('/api/auth/demo'))}>
          ▶ Try the demo, no sign-up
        </button>
        <p className="auth-switch">
          {signup ? 'Already have an account? ' : 'New to Spyra? '}
          <button type="button" onClick={() => { setMode(signup ? 'signin' : 'signup'); setErr(null) }}>{signup ? 'Sign in' : 'Create one'}</button>
        </p>
      </div>
    </div>
  )
}

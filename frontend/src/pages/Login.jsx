import { useState } from 'react'
import { login } from '../services/api.js'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      onLogin(await login(email, password))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-shell">
      <section className="login-intro">
        <p className="eyebrow">Cybersecurity awareness platform</p>
        <h1>See risk.<br />Build resilience.</h1>
        <p>Turn controlled phishing exercises into clear, measurable learning outcomes.</p>
      </section>
      <section className="login-panel">
        <div className="brand-mark" aria-hidden="true">P</div>
        <p className="eyebrow">Administrator access</p>
        <h2>Welcome to PhishGuard</h2>
        <p className="muted">Sign in to review campaign performance and user awareness.</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
    </main>
  )
}

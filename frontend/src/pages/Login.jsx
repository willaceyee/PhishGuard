import { useState } from 'react'
import ShieldMark from '../components/ShieldMark.jsx'
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
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand"><ShieldMark size={30} /><span>PhishGuard</span></div>
        <h1 id="login-title">Administrator sign in</h1>
        <p className="muted">Review campaign outcomes, coaching priorities, and URL detection.</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="login-note">Authorized awareness simulations only.</p>
      </section>
      <section className="login-visual" aria-hidden="true">
        <div className="login-visual-inner">
          {/* Reserved slot: the future 3D shield replaces the flat mark at this size. */}
          <div className="hero-shield-slot"><ShieldMark size={150} /></div>
          <p>Phishing simulation, awareness training, and URL detection in one workspace.</p>
        </div>
      </section>
    </main>
  )
}

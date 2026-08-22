import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'
import { getDashboardOverview } from './services/api.js'

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('phishguard_token'))
  const [admin, setAdmin] = useState(() => {
    const stored = sessionStorage.getItem('phishguard_admin')
    return stored ? JSON.parse(stored) : null
  })
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(token))

  const handleLogout = () => {
    sessionStorage.removeItem('phishguard_token')
    sessionStorage.removeItem('phishguard_admin')
    setToken(null)
    setAdmin(null)
    setDashboard(null)
  }

  const loadDashboard = async (activeToken = token) => {
    if (!activeToken) return
    setLoading(true)
    setError('')
    try {
      setDashboard(await getDashboardOverview(activeToken))
    } catch (requestError) {
      if (requestError.status === 401) handleLogout()
      else setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    getDashboardOverview(token)
      .then((result) => {
        if (!cancelled) setDashboard(result)
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError.status === 401) {
          sessionStorage.removeItem('phishguard_token')
          sessionStorage.removeItem('phishguard_admin')
          setToken(null)
          setAdmin(null)
          setDashboard(null)
        } else setError(requestError.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [token])

  const handleLogin = (loginResult) => {
    sessionStorage.setItem('phishguard_token', loginResult.access_token)
    sessionStorage.setItem('phishguard_admin', JSON.stringify(loginResult.admin))
    setLoading(true)
    setAdmin(loginResult.admin)
    setToken(loginResult.access_token)
  }

  if (!token) return <Login onLogin={handleLogin} />

  return (
    <Dashboard
      admin={admin}
      data={dashboard}
      error={error}
      loading={loading}
      onLogout={handleLogout}
      onRefresh={() => loadDashboard()}
      token={token}
    />
  )
}

export default App

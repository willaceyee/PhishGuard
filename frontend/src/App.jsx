import { useEffect, useState } from 'react'
import { getBackendHealth } from './services/api.js'

function App() {
  const [message, setMessage] = useState('Checking backend connection...')

  useEffect(() => {
    getBackendHealth()
      .then((data) => setMessage(data.message))
      .catch(() => setMessage('Backend is currently unavailable'))
  }, [])

  return (
    <main className="shell">
      <section className="card">
        <p className="eyebrow">Cybersecurity awareness platform</p>
        <h1>PhishGuard</h1>
        <p className="intro">Simulate phishing campaigns, strengthen awareness, and make risk understandable.</p>
        <div className="status" role="status">
          <span className="status-dot" aria-hidden="true" />
          {message}
        </div>
      </section>
    </main>
  )
}

export default App


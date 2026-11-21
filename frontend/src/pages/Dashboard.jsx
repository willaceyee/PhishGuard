import { useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon.jsx'
import ShieldMark from '../components/ShieldMark.jsx'
import Campaigns from './Campaigns.jsx'
import Detection from './Detection.jsx'
import Overview from './Overview.jsx'
import SendingProfiles from './SendingProfiles.jsx'
import Templates from './Templates.jsx'
import Users from './Users.jsx'

const pages = [
  ['overview', 'Overview', 'overview'],
  ['users', 'Users', 'users'],
  ['templates', 'Templates', 'templates'],
  ['campaigns', 'Campaigns', 'campaigns'],
  ['detection', 'Detection', 'detection'],
  ['sendingProfiles', 'Sending profiles', 'mail'],
]

function initials(name) {
  return (name || 'Administrator').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('')
}

function AccountMenu({ admin, onLogout }) {
  const [open, setOpen] = useState(false)
  const wrapper = useRef(null)
  const toggle = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const close = (event) => { if (!wrapper.current?.contains(event.target)) setOpen(false) }
    const escape = (event) => { if (event.key === 'Escape') { setOpen(false); toggle.current?.focus() } }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', escape) }
  }, [open])

  return (
    <div className="account-menu" ref={wrapper}>
      <button ref={toggle} type="button" className="account-toggle" aria-expanded={open} aria-controls="account-panel" onClick={() => setOpen((value) => !value)}>
        <span className="account-initials" aria-hidden="true">{initials(admin?.name)}</span>
        <span className="sr-only">Account menu</span>
      </button>
      {open && <div className="account-panel" id="account-panel">
        <strong>{admin?.name || 'Administrator'}</strong>
        {admin?.email && <span>{admin.email}</span>}
        <button type="button" className="secondary-button account-signout" onClick={onLogout}><Icon name="signout" size={16} /> Sign out</button>
      </div>}
    </div>
  )
}

export default function Dashboard({ admin, data, error, loading, loadedAt, onLogout, onRefresh, token }) {
  const [activePage, setActivePage] = useState('overview')
  const main = useRef(null)

  const navigate = (page) => {
    setActivePage(page)
    main.current?.focus({ preventScroll: true })
    window.scrollTo?.(0, 0)
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="app-header">
        <div className="app-brand"><ShieldMark size={26} /><span>PhishGuard</span></div>
        <nav className="app-nav" aria-label="Main navigation">
          {pages.map(([page, label, icon]) => (
            <button key={page} type="button" className={`nav-item ${activePage === page ? 'active' : ''}`} aria-current={activePage === page ? 'page' : undefined} onClick={() => navigate(page)}>
              <Icon name={icon} size={17} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <AccountMenu admin={admin} onLogout={onLogout} />
      </header>
      <main className="app-main" id="main-content" ref={main} tabIndex={-1}>
        {activePage === 'overview' && <Overview data={data} error={error} loading={loading} loadedAt={loadedAt} onRefresh={onRefresh} token={token} />}
        {activePage === 'users' && <Users token={token} onDataChange={onRefresh} />}
        {activePage === 'templates' && <Templates token={token} />}
        {activePage === 'campaigns' && <Campaigns token={token} onDataChange={onRefresh} />}
        {activePage === 'detection' && <Detection token={token} />}
        {activePage === 'sendingProfiles' && <SendingProfiles token={token} />}
      </main>
    </div>
  )
}

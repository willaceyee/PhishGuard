const percent = (value) => `${value ?? 0}%`
const quizValue = (value) => (value == null ? 'No results' : `${value}%`)

function MetricCard({ label, value, detail, tone = 'teal' }) {
  return <article className={`metric-card metric-${tone}`}><p>{label}</p><strong>{value}</strong><span>{detail}</span></article>
}

function RateBar({ value }) {
  return <div className="rate-cell"><span>{percent(value)}</span><div className="rate-track" aria-hidden="true"><div className="rate-fill" style={{ width: `${Math.min(value || 0, 100)}%` }} /></div></div>
}

export default function Dashboard({ admin, data, error, loading, onLogout, onRefresh, token }) {
  const [activePage, setActivePage] = useState('overview')
  const summary = data?.summary
  const titles = { overview: 'Awareness at a glance', users: 'User management', templates: 'Email templates', campaigns: 'Simulation campaigns', detection: 'URL detection' }
  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span>P</span> PhishGuard</div>
        <nav aria-label="Main navigation">
          {[['overview', 'Overview'], ['users', 'Users'], ['templates', 'Templates'], ['campaigns', 'Campaigns'], ['detection', 'Detection']].map(([page, label]) => <button key={page} className={`nav-item ${activePage === page ? 'active' : ''}`} onClick={() => setActivePage(page)}>{label}</button>)}
        </nav>
        <div className="sidebar-note"><span className="live-dot" /> Controlled simulation analytics</div>
      </aside>
      <main className="dashboard-main">
        <header className="topbar">
          <div><p className="eyebrow">Administrator workspace</p><h1>{titles[activePage]}</h1></div>
          <div className="admin-actions"><div><strong>{admin?.name || 'Administrator'}</strong><span>{admin?.email}</span></div><button className="ghost-button" onClick={onRefresh} disabled={loading}>Refresh</button><button className="ghost-button" onClick={onLogout}>Sign out</button></div>
        </header>
        {activePage === 'overview' && error && <div className="dashboard-error" role="alert">{error}</div>}
        {activePage === 'overview' && loading && !data && <div className="loading-state">Loading campaign analytics…</div>}
        {activePage === 'overview' && data && <>
          <section className="metric-grid" id="overview" aria-label="Summary metrics">
            <MetricCard label="Campaigns" value={summary.total_campaigns} detail={`${summary.total_recipients} recipient assignments`} />
            <MetricCard label="Click-through rate" value={percent(summary.click_through_rate)} detail={`${summary.unique_clicked} unique clicks`} tone="amber" />
            <MetricCard label="Training complete" value={percent(summary.training_completion_rate)} detail={`${summary.training_completed} completions`} tone="blue" />
            <MetricCard label="Average quiz" value={quizValue(summary.average_quiz_percentage)} detail={`${summary.high_risk_users} high-risk users`} tone="rose" />
          </section>
          <section className="panel" id="campaigns">
            <div className="panel-heading"><div><p className="eyebrow">Campaign performance</p><h2>Engagement and learning</h2></div><span>{data.campaigns.length} campaigns</span></div>
            {data.campaigns.length === 0 ? <p className="empty-state">Create a campaign and assign recipients to begin collecting analytics.</p> : <div className="table-wrap"><table><thead><tr><th>Campaign</th><th>Recipients</th><th>Click rate</th><th>Submission</th><th>Training</th><th>Quiz average</th></tr></thead><tbody>{data.campaigns.map((campaign) => <tr key={campaign.campaign_id}><td><strong>{campaign.campaign_name}</strong><span className="table-subtitle">{campaign.status}</span></td><td>{campaign.recipient_count}</td><td><RateBar value={campaign.click_through_rate} /></td><td>{percent(campaign.submission_rate)}</td><td>{percent(campaign.training_completion_rate)}</td><td>{quizValue(campaign.average_quiz_percentage)}</td></tr>)}</tbody></table></div>}
          </section>
          <section className="panel" id="risk">
            <div className="panel-heading"><div><p className="eyebrow">User risk</p><h2>Prioritized coaching</h2></div><span>Score 0–100</span></div>
            {data.user_risks.length === 0 ? <p className="empty-state">Risk scores appear after users are assigned to campaigns.</p> : <div className="table-wrap"><table><thead><tr><th>User</th><th>Department</th><th>Risk</th><th>Clicked</th><th>Submitted</th><th>Training</th><th>Quiz average</th></tr></thead><tbody>{data.user_risks.map((user) => <tr key={user.user_id}><td><strong>{user.name}</strong><span className="table-subtitle">{user.email}</span></td><td>{user.department || '—'}</td><td><span className={`risk-badge risk-${user.risk_band}`}>{user.risk_score} · {user.risk_band}</span></td><td>{user.clicked_campaigns}/{user.campaigns_assessed}</td><td>{user.submitted_campaigns}/{user.campaigns_assessed}</td><td>{user.completed_training}/{user.campaigns_assessed}</td><td>{quizValue(user.average_quiz_percentage)}</td></tr>)}</tbody></table></div>}
            <p className="method-note">Risk weights: click {data.risk_method.weights.clicked}, simulated submission {data.risk_method.weights.submitted}, incomplete training {data.risk_method.weights.training_incomplete}, and quiz gap up to {data.risk_method.weights.quiz_gap_maximum} points.</p>
          </section>
        </>}
        {activePage === 'users' && <Users token={token} onDataChange={onRefresh} />}
        {activePage === 'templates' && <Templates token={token} />}
        {activePage === 'campaigns' && <Campaigns token={token} onDataChange={onRefresh} />}
        {activePage === 'detection' && <Detection token={token} />}
      </main>
    </div>
  )
}
import { useState } from 'react'
import Campaigns from './Campaigns.jsx'
import Detection from './Detection.jsx'
import Templates from './Templates.jsx'
import Users from './Users.jsx'

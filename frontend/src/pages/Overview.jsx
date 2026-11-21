import { useEffect, useState } from 'react'
import Icon from '../components/Icon.jsx'
import { getCampaignQuizResults } from '../services/api.js'

const BANDS = [
  ['low', 'Low'],
  ['medium', 'Medium'],
  ['high', 'High'],
]
const bandLabel = Object.fromEntries(BANDS)
const COACHING_PREVIEW = 5

const share = (part, whole) => (whole ? Math.round((part / whole) * 100) : null)
const plural = (count, word, pluralWord = `${word}s`) => `${count} ${count === 1 ? word : pluralWord}`

function Kpi({ icon, label, value, total, scope }) {
  return (
    <article className="kpi">
      <span className="kpi-icon"><Icon name={icon} size={26} /></span>
      <div>
        <h2>{label}</h2>
        <p className="kpi-value">{value}{total != null && <span> of {total}</span>}</p>
        <p className="kpi-scope">{scope}</p>
      </div>
    </article>
  )
}

function statusSummary(campaigns) {
  const counts = campaigns.reduce((result, campaign) => ({ ...result, [campaign.status]: (result[campaign.status] || 0) + 1 }), {})
  const text = Object.entries(counts).map(([status, count]) => `${count} ${status}`).join(' · ')
  return text || 'None created yet'
}

function arcPath(cx, cy, outer, inner, start, end) {
  const point = (radius, angle) => [cx + radius * Math.sin(angle), cy - radius * Math.cos(angle)]
  const large = end - start > Math.PI ? 1 : 0
  const [x1, y1] = point(outer, start)
  const [x2, y2] = point(outer, end)
  const [x3, y3] = point(inner, end)
  const [x4, y4] = point(inner, start)
  return `M${x1} ${y1}A${outer} ${outer} 0 ${large} 1 ${x2} ${y2}L${x3} ${y3}A${inner} ${inner} 0 ${large} 0 ${x4} ${y4}Z`
}

function RiskDistribution({ users }) {
  const counts = Object.fromEntries(BANDS.map(([band]) => [band, users.filter((user) => user.risk_band === band).length]))
  const total = users.length
  const size = 180
  const center = size / 2
  const outer = 84
  const inner = 52
  let cursor = 0
  // Drawn clockwise from 12 o'clock as medium, high, low so warning colors read first.
  const segments = [BANDS[1], BANDS[2], BANDS[0]].filter(([band]) => counts[band] > 0).map(([band, label]) => {
    const start = cursor
    cursor += (counts[band] / total) * Math.PI * 2
    return { band, label, start, end: cursor, percent: share(counts[band], total) }
  })

  return (
    <section className="panel risk-panel" aria-labelledby="risk-heading">
      <div className="panel-heading">
        <div><h2 id="risk-heading">Risk distribution</h2><p className="panel-scope">People across all campaigns</p></div>
      </div>
      {total === 0 ? <p className="empty-state">No results. Risk bands appear after recipients are assigned to a campaign.</p> : <>
        <div className="donut-wrap">
          <svg className="donut" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Risk distribution: ${BANDS.map(([band, label]) => `${label} ${counts[band]}`).join(', ')} of ${plural(total, 'person', 'people')}`}>
            {segments.length === 1
              ? <><circle cx={center} cy={center} r={(outer + inner) / 2} className={`donut-ring risk-fill-${segments[0].band}`} strokeWidth={outer - inner} /><text x={center} y={center - outer + (outer - inner) / 2 + 4} className="donut-label">100%</text></>
              : segments.map((segment) => {
                const middle = (segment.start + segment.end) / 2
                const labelRadius = (outer + inner) / 2
                return <g key={segment.band}>
                  <path d={arcPath(center, center, outer, inner, segment.start, segment.end)} className={`donut-segment risk-fill-${segment.band}`}><title>{`${segment.label}: ${counts[segment.band]} (${segment.percent}%)`}</title></path>
                  {segment.end - segment.start > 0.45 && <text x={center + labelRadius * Math.sin(middle)} y={center - labelRadius * Math.cos(middle) + 4} className="donut-label">{segment.percent}%</text>}
                </g>
              })}
            <text x={center} y={center + 4} className="donut-total">{total}</text>
            <text x={center} y={center + 22} className="donut-caption">{total === 1 ? 'person' : 'people'}</text>
          </svg>
        </div>
        <ul className="risk-legend">
          {BANDS.map(([band, label]) => <li key={band}>
            <span className={`swatch risk-fill-${band}`} aria-hidden="true" />
            <span>{label}</span>
            <span className="legend-share">{share(counts[band], total)}%</span>
            <strong>{counts[band]}</strong>
          </li>)}
        </ul>
      </>}
    </section>
  )
}

function axisTicks(max) {
  if (max <= 10) return Array.from({ length: max + 1 }, (_, index) => index)
  const step = Math.ceil(max / 5)
  const ticks = []
  for (let value = 0; value < max; value += step) ticks.push(value)
  return [...ticks, max]
}

function QuizResults({ campaign, token }) {
  const [state, setState] = useState({ campaignId: null, results: null, error: '' })

  useEffect(() => {
    let cancelled = false
    getCampaignQuizResults(token, campaign.campaign_id)
      .then((data) => { if (!cancelled) setState({ campaignId: campaign.campaign_id, results: data.results, error: '' }) })
      .catch((requestError) => { if (!cancelled) setState({ campaignId: campaign.campaign_id, results: null, error: requestError.message }) })
    return () => { cancelled = true }
  }, [campaign.campaign_id, campaign.quiz_responses, token])

  const current = state.campaignId === campaign.campaign_id
  const results = current ? state.results : null
  const shown = results?.slice(0, 8) || []

  return (
    <div className="quiz-strip">
      <div className="quiz-strip-label"><Icon name="quiz" size={22} /><div><h3>Quiz results</h3><span>{campaign.average_quiz_percentage == null ? 'No results' : `${campaign.average_quiz_percentage}% average · ${plural(campaign.quiz_responses, 'response')}`}</span></div></div>
      <div className="quiz-chips" aria-live="polite">
        {!current && <span className="quiz-note">Loading quiz results…</span>}
        {current && state.error && <span className="quiz-note">Quiz scores unavailable: {state.error}</span>}
        {current && results && results.length === 0 && <span className="quiz-note">No results</span>}
        {shown.map((result) => <span className="quiz-chip" key={result.quiz_id} title={`${result.percentage}%`}><Icon name="account" size={16} />{result.score}/{result.total_questions}</span>)}
        {results && results.length > shown.length && <span className="quiz-note">+{results.length - shown.length} more</span>}
      </div>
    </div>
  )
}

function CampaignOutcomes({ campaigns, token }) {
  const [selectedId, setSelectedId] = useState(null)
  const campaign = campaigns.find((item) => item.campaign_id === selectedId) || campaigns[0]

  if (!campaign) {
    return <section className="panel outcomes-panel" aria-labelledby="outcomes-heading">
      <div className="panel-heading"><div><h2 id="outcomes-heading">Campaign outcomes</h2><p className="panel-scope">No campaign selected</p></div></div>
      <p className="empty-state">No campaigns yet. Create one on Campaigns and assign approved recipients to start collecting outcomes.</p>
    </section>
  }

  const max = campaign.recipient_count
  const rows = [
    ['Assigned', campaign.recipient_count, 'assigned'],
    ['Clicked', campaign.unique_clicked, 'outcome'],
    ['Simulated submissions', campaign.unique_submitted, 'outcome'],
    ['Completed training', campaign.training_completed, 'training'],
  ]
  const ticks = axisTicks(max)

  return (
    <section className="panel outcomes-panel" aria-labelledby="outcomes-heading">
      <div className="panel-heading">
        <div><h2 id="outcomes-heading">{campaign.campaign_name}</h2><p className="panel-scope">Campaign outcomes · <span className="status-text">{campaign.status}</span></p></div>
        {campaigns.length > 1 && <div className="campaign-select">
          <label htmlFor="overview-campaign">Campaign</label>
          <select id="overview-campaign" value={campaign.campaign_id} onChange={(event) => setSelectedId(Number(event.target.value))}>
            {campaigns.map((item) => <option key={item.campaign_id} value={item.campaign_id}>{item.campaign_name}</option>)}
          </select>
        </div>}
      </div>
      {max === 0 ? <p className="empty-state">No recipients assigned to this campaign yet.</p> : <>
        <div className="bar-chart" role="img" aria-label={`${campaign.campaign_name}: ${rows.map(([label, value]) => `${label} ${value}`).join(', ')}, out of ${max} recipients`}>
          {rows.map(([label, value, tone]) => {
            const width = (value / max) * 100
            const inside = width >= 80
            const percent = share(value, max)
            return <div className="bar-row" key={label} title={`${label}: ${value} of ${max} recipients (${percent}%)`}>
              <span className="bar-label">{label}</span>
              <div className="bar-track">
                {ticks.map((tick) => <span key={tick} className="bar-gridline" style={{ left: `${(tick / max) * 100}%` }} />)}
                {value > 0 && <span className={`bar-fill bar-${tone}`} style={{ width: `${width}%` }}>{inside && <span className="bar-value inside">{value}</span>}</span>}
                {!inside && <span className="bar-value" style={{ left: `calc(${width}% + ${value > 0 ? 8 : 4}px)` }}>{value}</span>}
              </div>
              <span className="bar-share">{tone === 'assigned' ? '' : `${percent}%`}</span>
            </div>
          })}
          <div className="bar-row bar-axis" aria-hidden="true">
            <span />
            <div className="bar-track">{ticks.map((tick) => <span key={tick} className="bar-tick" style={{ left: `${(tick / max) * 100}%` }}>{tick}</span>)}</div>
            <span />
          </div>
        </div>
        <p className="chart-note">Recipients in this campaign. Outcomes are counted separately; a participant can complete training without clicking or submitting the simulated form.</p>
      </>}
      <QuizResults campaign={campaign} token={token} />
    </section>
  )
}

function CoachingPriorities({ users, method }) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? users : users.slice(0, COACHING_PREVIEW)
  return (
    <section className="panel coaching-panel" aria-labelledby="coaching-heading">
      <div className="panel-heading">
        <div><h2 id="coaching-heading">Coaching priorities</h2><p className="panel-scope">Highest risk score first · all campaigns</p></div>
      </div>
      {users.length === 0 ? <p className="empty-state">No results. Risk scores appear after recipients are assigned to a campaign.</p> : <>
        <ol className="coaching-list">
          {shown.map((user) => <li key={user.user_id} className="coaching-item">
            <div className="coaching-top">
              <span className="coaching-avatar" aria-hidden="true"><Icon name="account" size={20} /></span>
              <div className="coaching-name"><strong>{user.name}</strong><span>{user.department || 'No department'} · {plural(user.campaigns_assessed, 'campaign')}</span></div>
              <span className={`risk-badge risk-${user.risk_band}`}>{bandLabel[user.risk_band]}</span>
            </div>
            <div className="score-row">
              <div className="score-track" aria-hidden="true"><span className="score-fill" style={{ width: `${user.risk_score}%` }} /></div>
              <strong className="score-value">{user.risk_score}</strong>
            </div>
            <span className="score-caption">Risk score (0–100)<span className="sr-only">: {user.risk_score}, {bandLabel[user.risk_band]}</span></span>
          </li>)}
        </ol>
        {users.length > COACHING_PREVIEW && <button type="button" className="text-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Show fewer' : `Show all ${users.length}`}</button>}
        {method && <details className="method-note">
          <summary>How risk scores are calculated</summary>
          <p>Per campaign: click {method.weights.clicked}, simulated submission {method.weights.submitted}, incomplete training {method.weights.training_incomplete}, and quiz gap up to {method.weights.quiz_gap_maximum} points. A person’s score is the mean across their campaigns. High is {method.high_threshold} or more; Medium is {method.medium_threshold}–{method.high_threshold - 1}.</p>
        </details>}
      </>}
    </section>
  )
}

export default function Overview({ data, error, loading, loadedAt, onRefresh, token }) {
  const summary = data?.summary
  const people = data?.user_risks.length ?? 0
  const quizResponses = data?.campaigns.reduce((total, campaign) => total + campaign.quiz_responses, 0) ?? 0

  return (
    <section className="overview-page" aria-labelledby="page-title">
      <div className="page-heading">
        <div>
          <h1 id="page-title">Awareness overview</h1>
          <p className="page-subtitle">All campaigns{loadedAt && <> · Updated <time dateTime={loadedAt.toISOString()}>{loadedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></>}</p>
        </div>
        {onRefresh && <button type="button" className="secondary-button compact" onClick={() => { if (!loading) onRefresh() }} aria-disabled={loading || undefined}><Icon name="refresh" size={16} />{loading ? 'Refreshing…' : 'Refresh'}</button>}
      </div>
      {error && <div className="dashboard-error" role="alert">Unable to load campaign analytics: {error}</div>}
      {loading && !data && <p className="loading-state" role="status">Loading campaign analytics…</p>}
      {data && <>
        <section className="kpi-grid" aria-label="Summary metrics">
          <Kpi icon="campaigns" label="Campaigns" value={summary.total_campaigns} scope={statusSummary(data.campaigns)} />
          <Kpi icon="users" label="Assigned" value={summary.total_recipients} scope={`Recipient assignments · ${plural(people, 'person', 'people')}`} />
          <Kpi icon="cursor" label="Clicked" value={summary.unique_clicked} total={summary.total_recipients} scope="Assignments with a link click" />
          <Kpi icon="training" label="Training complete" value={summary.training_completed} total={summary.total_recipients} scope="Assignments with training complete" />
          <Kpi icon="quiz" label="Average quiz" value={summary.average_quiz_percentage == null ? 'No results' : `${summary.average_quiz_percentage}%`} scope={quizResponses ? `Across ${plural(quizResponses, 'quiz response')}` : 'No quiz responses yet'} />
        </section>
        <div className="overview-grid">
          <RiskDistribution users={data.user_risks} />
          <CampaignOutcomes campaigns={data.campaigns} token={token} />
          <CoachingPriorities users={data.user_risks} method={data.risk_method} />
        </div>
      </>}
    </section>
  )
}

import { useState } from 'react'
import { predictUrl } from '../services/api.js'

const asPercent = (value) => `${Math.round(value * 100)}%`
const signed = (value) => `${value > 0 ? '+' : ''}${value.toFixed(3)}`

export default function Detection({ token }) {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault(); setLoading(true); setError(''); setResult(null)
    try { setResult(await predictUrl(token, url)) } catch (requestError) { setError(requestError.message) } finally { setLoading(false) }
  }

  const factors = result?.top_factors || []
  const largestImpact = Math.max(...factors.map((factor) => Math.abs(factor.impact)), 0.000001)
  const threshold = result?.threshold ?? 0.5

  return <section className="workspace-page detection-page">
    <div className="page-heading"><div><h1>URL detection</h1><p>Analyze URL text offline. PhishGuard does not visit, resolve, or download from the destination.</p></div><span className="count-pill">Random Forest + SHAP</span></div>
    <form className="detection-form" onSubmit={submit}><label htmlFor="detection-url">URL to analyze</label><div><input id="detection-url" type="text" placeholder="https://example.com/account" value={url} onChange={(event) => setUrl(event.target.value)} required /><button className="primary-button" disabled={loading}>{loading ? 'Analyzing…' : 'Analyze URL'}</button></div></form>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    {loading && <p className="loading-state" role="status">Analyzing URL features…</p>}
    {result && <div className="detection-results">
      <article className={`verdict-card verdict-${result.prediction}`} aria-labelledby="verdict-heading">
        <h2 id="verdict-heading">Model prediction</h2>
        <p className="verdict-label">{result.prediction}</p>
        <div className="probability">
          <div className="probability-head"><span>Phishing probability</span><strong>{asPercent(result.phishing_probability)}</strong></div>
          <div className="probability-track" role="img" aria-label={`Phishing probability ${asPercent(result.phishing_probability)}; decision threshold ${asPercent(threshold)}`}>
            <span className="probability-fill" style={{ width: `${result.phishing_probability * 100}%` }} />
            <span className="probability-threshold" style={{ left: `${threshold * 100}%` }} title={`Decision threshold ${asPercent(threshold)}`} />
          </div>
          <div className="probability-scale"><span>0%</span><span>Threshold {asPercent(threshold)}</span><span>100%</span></div>
        </div>
        <p className="verdict-meta">{asPercent(result.confidence)} confidence{result.model_type ? ` · ${result.model_type}` : ''}</p>
      </article>
      <section className="panel" aria-labelledby="factors-heading">
        <div className="panel-heading"><div><h2 id="factors-heading">Top decision factors</h2><p className="panel-scope">SHAP contribution toward the phishing class, largest first</p></div></div>
        <div className="factor-legend" aria-hidden="true"><span><i style={{ background: 'var(--high)' }} />Increases risk</span><span><i style={{ background: 'var(--accent)' }} />Decreases risk</span></div>
        {factors.length === 0 ? <p className="empty-state">No factor explanations were returned.</p> : <div className="factor-list">{factors.map((factor) => {
          const width = (Math.abs(factor.impact) / largestImpact) * 50
          const raises = factor.impact > 0
          return <article className="factor-row" key={factor.feature}>
            <div><strong>{factor.label}</strong><small>Observed value: {String(factor.value)}</small></div>
            <div className="factor-bar" aria-hidden="true"><span className={raises ? 'raises' : 'lowers'} style={{ width: `${width}%` }} /></div>
            <span className={`factor-impact ${raises ? 'impact-risk' : 'impact-safe'}`}>{signed(factor.impact)}<br /><small>{factor.direction}</small></span>
          </article>
        })}</div>}
        <p className="method-note">This result is decision support, not proof that a URL is malicious. The current development model was trained on synthetic pipeline data and requires real-world validation.</p>
      </section>
    </div>}
  </section>
}

import { useState } from 'react'
import { predictUrl } from '../services/api.js'

export default function Detection({ token }) {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault(); setLoading(true); setError(''); setResult(null)
    try { setResult(await predictUrl(token, url)) } catch (requestError) { setError(requestError.message) } finally { setLoading(false) }
  }

  return <section className="workspace-page detection-page">
    <div className="page-heading"><div><p className="eyebrow">Offline lexical analysis</p><h1>URL detection</h1><p>Analyze URL text without visiting, resolving, or downloading from the destination.</p></div><span className="count-pill">Random Forest + SHAP</span></div>
    <form className="detection-form" onSubmit={submit}><label htmlFor="detection-url">URL to analyze</label><div><input id="detection-url" type="text" placeholder="https://example.com/account" value={url} onChange={(event) => setUrl(event.target.value)} required /><button className="primary-button" disabled={loading}>{loading ? 'Analyzing…' : 'Analyze URL'}</button></div></form>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    {result && <div className="detection-results"><article className={`verdict-card verdict-${result.prediction}`}><p>Model prediction</p><h2>{result.prediction}</h2><strong>{Math.round(result.phishing_probability * 100)}% phishing probability</strong><span>{Math.round(result.confidence * 100)}% confidence</span></article><section className="panel"><div className="panel-heading"><div><p className="eyebrow">SHAP explanation</p><h2>Top decision factors</h2></div><span>Model-specific evidence</span></div><div className="factor-list">{result.top_factors.map((factor) => <article key={factor.feature}><div><strong>{factor.label}</strong><small>Observed value: {String(factor.value)}</small></div><span className={factor.impact > 0 ? 'impact-risk' : 'impact-safe'}>{factor.direction}<br /><small>{factor.impact > 0 ? '+' : ''}{factor.impact}</small></span></article>)}</div><p className="method-note">This result is decision support, not proof that a URL is malicious. The current development model was trained on synthetic pipeline data and requires real-world validation.</p></section></div>}
  </section>
}

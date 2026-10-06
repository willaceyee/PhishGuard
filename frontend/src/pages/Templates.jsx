import { useEffect, useState } from 'react'
import {
  createTemplate,
  deleteTemplate,
  listTemplates,
  updateTemplate,
} from '../services/api.js'

const emptyForm = { template_name: '', subject: '', body: '', category: 'credential' }

export default function Templates({ token }) {
  const [templates, setTemplates] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    listTemplates(token)
      .then((data) => { if (!cancelled) setTemplates(data.templates) })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [token])

  const resetForm = () => {
    setForm(emptyForm)
    setEditingId(null)
  }

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      if (editingId !== null) {
        const result = await updateTemplate(token, editingId, form)
        setTemplates((current) => current.map((template) => (
          template.template_id === editingId ? result.template : template
        )))
      } else {
        const result = await createTemplate(token, form)
        setTemplates((current) => [result.template, ...current])
      }
      resetForm()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  const beginEdit = (template) => {
    setEditingId(template.template_id)
    setForm({
      template_name: template.template_name,
      subject: template.subject,
      body: template.body,
      category: template.category || 'credential',
    })
    setError('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const remove = async (template) => {
    if (!window.confirm(`Delete ${template.template_name}?`)) return
    setError('')
    try {
      await deleteTemplate(token, template.template_id)
      setTemplates((current) => current.filter(
        (item) => item.template_id !== template.template_id,
      ))
      if (editingId === template.template_id) resetForm()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  return <section className="workspace-page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">Simulation content</p>
        <h1>Email templates</h1>
        <p>Create and maintain controlled messages without sending them from PhishGuard.</p>
      </div>
      <span className="count-pill">{templates.length} templates</span>
    </div>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    <div className="workspace-grid">
      <form className="form-card" onSubmit={submit}>
        <h2>{editingId === null ? 'New template' : 'Edit template'}</h2>
        <label htmlFor="template-name">Template name</label>
        <input id="template-name" value={form.template_name} onChange={(event) => setForm({ ...form, template_name: event.target.value })} required />
        <label htmlFor="subject">Email subject</label>
        <input id="subject" value={form.subject} onChange={(event) => setForm({ ...form, subject: event.target.value })} required />
        <label htmlFor="category">Category</label>
        <select id="category" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
          <option value="credential">Credential</option>
          <option value="invoice">Invoice</option>
          <option value="document">Document share</option>
          <option value="awareness">Awareness</option>
        </select>
        <label htmlFor="body">Message body</label>
        <textarea id="body" rows="6" value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} required />
        <div className="form-actions">
          <button className="primary-button" disabled={saving}>
            {saving ? 'Saving…' : editingId === null ? 'Save template' : 'Update template'}
          </button>
          {editingId !== null && <button type="button" className="secondary-button" onClick={resetForm} disabled={saving}>Cancel</button>}
        </div>
      </form>
      <div className="list-card">
        <h2>Template library</h2>
        {loading ? <p className="empty-state">Loading templates…</p> : templates.length === 0 ? <p className="empty-state">No templates yet.</p> : <div className="record-list">
          {templates.map((template) => <article className={`template-record ${editingId === template.template_id ? 'selected' : ''}`} key={template.template_id}>
            <div>
              <span className="category-tag">{template.category || 'general'}</span>
              <h3>{template.template_name}</h3>
              <strong>{template.subject}</strong>
              <p>{template.body}</p>
            </div>
            <div className="record-actions">
              <button className="small-button" onClick={() => beginEdit(template)}>Edit</button>
              <button className="danger-link" onClick={() => remove(template)}>Delete</button>
            </div>
          </article>)}
        </div>}
      </div>
    </div>
  </section>
}

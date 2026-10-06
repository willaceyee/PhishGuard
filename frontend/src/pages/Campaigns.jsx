import { useEffect, useState } from 'react'
import {
  assignRecipients,
  createCampaign,
  deleteCampaign,
  getDeliveryPreview,
  listCampaigns,
  listRecipients,
  listTemplates,
  listUsers,
  sendCampaignEmails,
} from '../services/api.js'

export default function Campaigns({ token, onDataChange }) {
  const [campaigns, setCampaigns] = useState([])
  const [users, setUsers] = useState([])
  const [templates, setTemplates] = useState([])
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [recipients, setRecipients] = useState([])
  const [selectedUsers, setSelectedUsers] = useState([])
  const [delivery, setDelivery] = useState(null)
  const [confirmation, setConfirmation] = useState('')
  const [sending, setSending] = useState(false)
  const [form, setForm] = useState({ campaign_name: '', template_id: '', status: 'draft' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([listCampaigns(token), listUsers(token), listTemplates(token)])
      .then(([campaignData, userData, templateData]) => {
        if (!cancelled) {
          setCampaigns(campaignData.campaigns)
          setUsers(userData.users)
          setTemplates(templateData.templates)
        }
      })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [token])

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setNotice('')
    try {
      const result = await createCampaign(token, {
        ...form,
        template_id: Number(form.template_id),
      })
      setCampaigns((current) => [result.campaign, ...current])
      setForm({ campaign_name: '', template_id: '', status: 'draft' })
      onDataChange()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const refreshDelivery = async (campaignId) => {
    const result = await getDeliveryPreview(token, campaignId)
    setDelivery(result.preview)
    setConfirmation('')
  }

  const openRecipients = async (campaign) => {
    setSelectedCampaign(campaign)
    setSelectedUsers([])
    setDelivery(null)
    setError('')
    setNotice('')
    try {
      const [recipientData, previewData] = await Promise.all([
        listRecipients(token, campaign.campaign_id),
        getDeliveryPreview(token, campaign.campaign_id),
      ])
      setRecipients(recipientData.recipients)
      setDelivery(previewData.preview)
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const toggleUser = (userId) => setSelectedUsers((current) => (
    current.includes(userId)
      ? current.filter((id) => id !== userId)
      : [...current, userId]
  ))

  const assign = async () => {
    if (!selectedCampaign || selectedUsers.length === 0) return
    setError('')
    setNotice('')
    try {
      const result = await assignRecipients(
        token,
        selectedCampaign.campaign_id,
        selectedUsers,
      )
      const recipientData = await listRecipients(token, selectedCampaign.campaign_id)
      setRecipients(recipientData.recipients)
      await refreshDelivery(selectedCampaign.campaign_id)
      setSelectedUsers([])
      setNotice(`${result.recipients.length} recipients added; ${result.skipped_existing} already assigned.`)
      onDataChange()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const deliver = async () => {
    if (!selectedCampaign || !delivery) return
    setSending(true)
    setError('')
    setNotice('')
    try {
      const result = await sendCampaignEmails(
        token,
        selectedCampaign.campaign_id,
        confirmation,
      )
      setNotice(`${result.delivered} authorized simulation emails delivered to the local Mailpit inbox.`)
      await refreshDelivery(selectedCampaign.campaign_id)
      onDataChange()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSending(false)
    }
  }

  const remove = async (campaign) => {
    if (!window.confirm(`Delete ${campaign.campaign_name} and its simulation records?`)) return
    try {
      await deleteCampaign(token, campaign.campaign_id)
      setCampaigns((current) => current.filter(
        (item) => item.campaign_id !== campaign.campaign_id,
      ))
      if (selectedCampaign?.campaign_id === campaign.campaign_id) {
        setSelectedCampaign(null)
        setDelivery(null)
      }
      onDataChange()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const copyLink = async (url) => {
    await navigator.clipboard.writeText(url)
    setNotice('Tracking link copied. Share it only within an authorized awareness exercise.')
  }

  return <section className="workspace-page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">Controlled simulation</p>
        <h1>Campaigns</h1>
        <p>Create a campaign, assign allowlisted users, preview delivery, and send only to the local Mailpit test inbox.</p>
      </div>
      <span className="count-pill">{campaigns.length} campaigns</span>
    </div>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    {notice && <div className="success-note" role="status">{notice}</div>}
    <div className="workspace-grid campaigns-grid">
      <form className="form-card" onSubmit={submit}>
        <h2>New campaign</h2>
        <label htmlFor="campaign-name">Campaign name</label>
        <input id="campaign-name" value={form.campaign_name} onChange={(event) => setForm({ ...form, campaign_name: event.target.value })} required />
        <label htmlFor="campaign-template">Email template</label>
        <select id="campaign-template" value={form.template_id} onChange={(event) => setForm({ ...form, template_id: event.target.value })} required>
          <option value="">Choose a template</option>
          {templates.map((template) => <option key={template.template_id} value={template.template_id}>{template.template_name}</option>)}
        </select>
        <label htmlFor="campaign-status">Status</label>
        <select id="campaign-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
          <option value="draft">Draft</option>
          <option value="scheduled">Scheduled</option>
          <option value="active">Active</option>
        </select>
        <button className="primary-button" disabled={templates.length === 0}>Create campaign</button>
        {templates.length === 0 && <small>Create an email template first.</small>}
      </form>
      <div className="list-card">
        <h2>Campaign list</h2>
        {loading ? <p className="empty-state">Loading campaigns…</p> : campaigns.length === 0 ? <p className="empty-state">No campaigns yet.</p> : <div className="record-list">
          {campaigns.map((campaign) => <article className={`campaign-record ${selectedCampaign?.campaign_id === campaign.campaign_id ? 'selected' : ''}`} key={campaign.campaign_id}>
            <div><span className="category-tag">{campaign.status}</span><h3>{campaign.campaign_name}</h3><small>Template #{campaign.template_id}</small></div>
            <div className="record-actions"><button className="small-button" onClick={() => openRecipients(campaign)}>Recipients & delivery</button><button className="danger-link" onClick={() => remove(campaign)}>Delete</button></div>
          </article>)}
        </div>}
      </div>
    </div>
    {selectedCampaign && <section className="panel assignment-panel">
      <div className="panel-heading"><div><p className="eyebrow">Recipient assignment</p><h2>{selectedCampaign.campaign_name}</h2></div><span>{recipients.length} assigned</span></div>
      <div className="assignment-grid">
        <div>
          <h3>Select users</h3>
          <div className="checkbox-list">{users.map((user) => <label key={user.user_id}><input type="checkbox" checked={selectedUsers.includes(user.user_id)} onChange={() => toggleUser(user.user_id)} /> <span><strong>{user.name}</strong><small>{user.email}</small></span></label>)}</div>
          <button className="primary-button" type="button" onClick={assign} disabled={selectedUsers.length === 0}>Assign selected users</button>
        </div>
        <div>
          <h3>Tracking links</h3>
          {recipients.length === 0 ? <p className="empty-state">No recipients assigned.</p> : <div className="link-list">{recipients.map((recipient) => <article key={recipient.recipient_id}><div><strong>{recipient.user.name}</strong><small>{recipient.user.email}</small><code>{recipient.tracking_url}</code></div><button className="small-button" onClick={() => copyLink(recipient.tracking_url)}>Copy link</button></article>)}</div>}
        </div>
      </div>
      {delivery && <div className="delivery-review">
        <div className="panel-heading"><div><p className="eyebrow">Final safety check</p><h2>Email delivery preview</h2></div><span>{delivery.already_delivered} previously delivered</span></div>
        <dl className="delivery-summary"><div><dt>From</dt><dd>{delivery.from}</dd></div><div><dt>Subject</dt><dd>{delivery.subject}</dd></div><div><dt>Allowlisted</dt><dd>{delivery.allowed_recipients.length}</dd></div><div><dt>Blocked</dt><dd>{delivery.blocked_recipients.length}</dd></div></dl>
        {delivery.blocked_recipients.length > 0 && <div className="delivery-warning"><strong>Delivery blocked</strong><p>Approve these recipients for simulation email on the Users page: {delivery.blocked_recipients.map((user) => user.email).join(', ')}</p></div>}
        {!delivery.delivery_enabled && <div className="delivery-warning"><strong>Delivery disabled</strong><p>Enable the local Mailpit configuration before sending.</p></div>}
        {!delivery.public_url_safe && <div className="delivery-warning"><strong>Unsafe public URL</strong><p>Use HTTPS unless the tracking site is localhost.</p></div>}
        <label htmlFor="send-confirmation">Type <strong>{delivery.confirmation_phrase}</strong> to confirm</label>
        <input id="send-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" />
        <button className="primary-button" type="button" onClick={deliver} disabled={sending || confirmation !== delivery.confirmation_phrase || delivery.blocked_recipients.length > 0 || !delivery.delivery_enabled || !delivery.public_url_safe || delivery.allowed_recipients.length === 0}>{sending ? 'Sending…' : 'Send to local Mailpit'}</button>
      </div>}
    </section>}
  </section>
}

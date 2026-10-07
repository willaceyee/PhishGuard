import { useEffect, useRef, useState } from 'react'
import {
  assignRecipients,
  createCampaign,
  deleteCampaign,
  getDeliveryPreview,
  getSendingProfile,
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
  const [profile, setProfile] = useState(null)
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [review, setReview] = useState(null)
  const [reviewRequest, setReviewRequest] = useState(null)
  const activeReviewRequest = useRef(null)
  const [selectedUsers, setSelectedUsers] = useState([])
  const [confirmation, setConfirmation] = useState('')
  const [sending, setSending] = useState(false)
  const [form, setForm] = useState({ campaign_name: '', template_id: '', status: 'draft', sending_profile_id: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([listCampaigns(token), listUsers(token), listTemplates(token), getSendingProfile(token)])
      .then(([campaignData, userData, templateData, profileData]) => {
        if (!cancelled) {
          setCampaigns(campaignData.campaigns)
          setUsers(userData.users)
          setTemplates(templateData.templates)
          setProfile(profileData.profile)
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
        sending_profile_id: form.sending_profile_id ? Number(form.sending_profile_id) : null,
      })
      setCampaigns((current) => [result.campaign, ...current])
      setForm({ campaign_name: '', template_id: '', status: 'draft', sending_profile_id: '' })
      onDataChange()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const beginReview = (campaignId) => {
    const request = { campaignId, generation: (activeReviewRequest.current?.generation || 0) + 1 }
    activeReviewRequest.current = request
    setReviewRequest(request)
    setReview(null)
    setConfirmation('')
    return request
  }

  const refreshDelivery = async (request) => {
    const [recipientData, previewData] = await Promise.all([
      listRecipients(token, request.campaignId),
      getDeliveryPreview(token, request.campaignId),
    ])
    if (activeReviewRequest.current !== request) return
    setReview({ request, recipients: recipientData.recipients, delivery: previewData.preview })
  }

  const openRecipients = async (campaign) => {
    const request = beginReview(campaign.campaign_id)
    setSelectedCampaign(campaign)
    setSelectedUsers([])
    setError('')
    setNotice('')
    try {
      await refreshDelivery(request)
    } catch (requestError) {
      if (activeReviewRequest.current === request) setError(requestError.message)
    }
  }

  const toggleUser = (userId) => setSelectedUsers((current) => (
    current.includes(userId)
      ? current.filter((id) => id !== userId)
      : [...current, userId]
  ))

  const assign = async () => {
    if (!selectedCampaign || selectedUsers.length === 0) return
    const request = beginReview(selectedCampaign.campaign_id)
    setError('')
    setNotice('')
    try {
      const result = await assignRecipients(
        token,
        request.campaignId,
        selectedUsers,
      )
      onDataChange()
      if (activeReviewRequest.current !== request) return
      await refreshDelivery(request)
      if (activeReviewRequest.current !== request) return
      setSelectedUsers([])
      setNotice(`${result.recipients.length} recipients added; ${result.skipped_existing} already assigned.`)
    } catch (requestError) {
      if (activeReviewRequest.current === request) setError(requestError.message)
    }
  }

  const deliver = async () => {
    if (!selectedCampaign || !canSend) return
    let request = activeReviewRequest.current
    if (request !== reviewRequest) return
    setSending(true)
    setError('')
    setNotice('')
    try {
      const result = await sendCampaignEmails(
        token,
        request.campaignId,
        confirmation,
      )
      onDataChange()
      if (activeReviewRequest.current !== request) return
      setNotice(isGmail
        ? `${result.delivered} authorized simulation emails delivered through Gmail.`
        : `${result.delivered} authorized simulation emails delivered to the local Mailpit inbox.`)
      request = beginReview(request.campaignId)
      await refreshDelivery(request)
    } catch (requestError) {
      if (activeReviewRequest.current === request) setError(requestError.message)
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
      if (activeReviewRequest.current?.campaignId === campaign.campaign_id) {
        activeReviewRequest.current = null
        setSelectedCampaign(null)
        setReviewRequest(null)
        setReview(null)
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

  const isCurrentReview = review?.request === reviewRequest && reviewRequest?.campaignId === selectedCampaign?.campaign_id
  const recipients = isCurrentReview ? review.recipients : []
  const delivery = isCurrentReview ? review.delivery : null
  const isGmail = delivery?.delivery_method === 'gmail'
  const campaignLimitExceeded = delivery && (isGmail
    ? delivery.allowed_recipients.length + delivery.blocked_recipients.length
    : recipients.length) > delivery.campaign_recipient_limit
  const hourlyLimitExceeded = delivery && delivery.hourly_delivered_count + delivery.allowed_recipients.length > delivery.hourly_delivery_limit
  const canSend = isCurrentReview && delivery && !sending && Boolean(delivery.confirmation_phrase)
    && confirmation === delivery.confirmation_phrase && delivery.blocked_recipients.length === 0
    && delivery.delivery_enabled && delivery.public_url_safe && delivery.allowed_recipients.length > 0
    && (!isGmail || delivery.profile_ready) && !campaignLimitExceeded && !hourlyLimitExceeded

  return <section className="workspace-page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">Controlled simulation</p>
        <h1>Campaigns</h1>
        <p>Create a campaign, assign approved users, and preview delivery to local Mailpit or an enabled Gmail profile.</p>
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
        <label htmlFor="campaign-delivery">Delivery method</label>
        <select id="campaign-delivery" value={form.sending_profile_id} onChange={(event) => setForm({ ...form, sending_profile_id: event.target.value })}>
          <option value="">Mailpit — local test delivery</option>
          {profile?.enabled && profile.credential_configured && <option value={profile.profile_id}>Gmail — {profile.name} ({profile.from_email})</option>}
        </select>
        {form.sending_profile_id && <div className="delivery-warning real-delivery-warning"><strong>Real email delivery</strong><p>Gmail sends real external email to approved recipients. Review the final safety checks before sending.</p></div>}
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
        <p className="delivery-method">{isGmail ? 'Gmail — real external delivery' : 'Mailpit — local test delivery'}</p>
        {isGmail && <div className="delivery-warning real-delivery-warning"><strong>Real email delivery</strong><p>Gmail sends real external email to approved recipients. Confirm that recipients can reach your public HTTPS deployment before sending.</p></div>}
        <dl className="delivery-summary"><div><dt>From</dt><dd>{delivery.from}</dd></div><div><dt>Subject</dt><dd>{delivery.subject}</dd></div><div><dt>Allowlisted</dt><dd>{delivery.allowed_recipients.length}</dd></div><div><dt>Blocked</dt><dd>{delivery.blocked_recipients.length}</dd></div></dl>
        {isGmail && <dl className="delivery-summary"><div><dt>Campaign limit</dt><dd>{delivery.campaign_recipient_limit} recipients</dd></div><div><dt>Hourly limit</dt><dd>{delivery.hourly_delivery_limit} emails</dd></div><div><dt>Sent in the past hour</dt><dd>{delivery.hourly_delivered_count}</dd></div><div><dt>Gmail profile</dt><dd>{delivery.profile_ready ? 'Ready' : 'Not ready'}</dd></div></dl>}
        {delivery.blocked_recipients.length > 0 && <div className="delivery-warning"><strong>Delivery blocked</strong><p>Approve these recipients for simulation email on the Users page: {delivery.blocked_recipients.map((user) => user.email).join(', ')}</p></div>}
        {!delivery.delivery_enabled && <div className="delivery-warning"><strong>Delivery disabled</strong><p>{isGmail ? 'Enable email delivery in the server configuration before sending.' : 'Enable the local Mailpit configuration before sending.'}</p></div>}
        {isGmail && !delivery.profile_ready && <div className="delivery-warning"><strong>Gmail profile not ready</strong><p>Enable the Gmail profile and complete a successful connection test on the Sending Profiles page.</p></div>}
        {!delivery.public_url_safe && <div className="delivery-warning"><strong>Unsafe public URL</strong><p>{isGmail ? 'Use a public HTTPS URL, outside localhost, loopback, and private networks.' : 'Use HTTPS unless the tracking site is localhost.'}</p></div>}
        {delivery.allowed_recipients.length === 0 && <div className="delivery-warning"><strong>No approved recipients remain</strong><p>Assign approved recipients who have not already received this campaign.</p></div>}
        {campaignLimitExceeded && <div className="delivery-warning"><strong>Campaign limit exceeded</strong><p>Reduce the recipient count to {delivery.campaign_recipient_limit} or fewer before sending.</p></div>}
        {hourlyLimitExceeded && <div className="delivery-warning"><strong>Hourly limit exceeded</strong><p>This send would exceed {delivery.hourly_delivery_limit} successful emails in the rolling hour. Wait for earlier deliveries to leave the window.</p></div>}
        <label htmlFor="send-confirmation">Type <strong>{delivery.confirmation_phrase}</strong> to confirm</label>
        <input id="send-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" />
        <button className="primary-button" type="button" onClick={deliver} disabled={!canSend}>{sending ? 'Sending…' : isGmail ? 'Send real Gmail emails' : 'Send to local Mailpit'}</button>
      </div>}
    </section>}
  </section>
}

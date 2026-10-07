import { useEffect, useState } from 'react'
import { createSendingProfile, deleteSendingProfile, getSendingProfile, testSendingProfile, updateSendingProfile } from '../services/api.js'

const emptyForm = { name: '', from_name: '', from_email: '' }
const errorMessages = {
  invalid_profile: 'Enter a profile name, display name, Gmail address, and Google app password.',
  invalid_gmail_address: 'Enter a valid @gmail.com address.',
  invalid_enabled: 'Unable to change the profile status.',
  sending_profile_exists: 'A Gmail sending profile already exists. Reopen this page to load it.',
  sending_profile_not_found: 'The sending profile was not found. Reopen this page to reload it.',
  sending_profile_in_use: 'This profile is used by a campaign and cannot be deleted.',
  sending_profile_persistence_failed: 'Unable to save the sending profile. Please try again.',
  gmail_sender_not_approved: 'Approve this Gmail address for simulation email in Users before sending a test.',
  gmail_authentication_failed: 'Gmail authentication failed. Check the Google app password.',
  gmail_provider_rejected: 'Gmail rejected the test email. Check the account and try again.',
  gmail_connection_failed: 'Unable to connect to Gmail. Please try again.',
  gmail_credentials_unavailable: 'Gmail credentials are unavailable. Check the app password and server encryption configuration.',
}

function safeError(error) {
  return Object.hasOwn(errorMessages, error?.message) ? errorMessages[error.message] : 'Unable to complete the sending profile request. Please try again.'
}

export default function SendingProfiles({ token }) {
  const [profile, setProfile] = useState(undefined)
  const [form, setForm] = useState(emptyForm)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let cancelled = false
    getSendingProfile(token).then((data) => {
      if (cancelled) return
      setProfile(data.profile)
      if (data.profile) setForm({ name: data.profile.name, from_name: data.profile.from_name, from_email: data.profile.from_email })
    }).catch((requestError) => { if (!cancelled) setError(safeError(requestError)) }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [token])

  const runAction = async (action) => {
    if (pending) return
    if (action === 'delete' && !window.confirm(`Delete ${profile.name}?`)) return
    setPending(action)
    setError('')
    setNotice('')
    try {
      if (action === 'delete') {
        await deleteSendingProfile(token)
        setProfile(null)
        setForm(emptyForm)
        setPassword('')
        setNotice('Profile deleted.')
      } else {
        let result
        if (action === 'create') result = await createSendingProfile(token, { ...form, app_password: password })
        else if (action === 'save') result = await updateSendingProfile(token, form)
        else if (action === 'replace') result = await updateSendingProfile(token, { app_password: password })
        else if (action === 'toggle') result = await updateSendingProfile(token, { enabled: !profile.enabled })
        else result = await testSendingProfile(token)
        if (action === 'create' || action === 'replace') setPassword('')
        setProfile(result.profile)
        if (action === 'create' || action === 'save') setForm({ name: result.profile.name, from_name: result.profile.from_name, from_email: result.profile.from_email })
        if (action === 'create') setNotice('Profile created.')
        else if (action === 'save') setNotice('Metadata saved.')
        else if (action === 'replace') setNotice('App password replaced.')
        else if (action === 'toggle') setNotice(result.profile.enabled ? 'Profile enabled.' : 'Profile disabled.')
        else setNotice(`Test email sent to ${result.profile.from_email}.`)
      }
    } catch (requestError) { setError(safeError(requestError)) } finally { setPending('') }
  }

  return <section className="workspace-page sending-profile-page">
    <div className="page-heading"><div><p className="eyebrow">Gmail delivery</p><h2>Sending profile</h2><p>Configure one Gmail account for approved simulation email. Test emails are sent to the profile’s own approved Gmail address.</p></div>{profile && <span className="count-pill">{profile.enabled ? 'Enabled' : 'Disabled'}</span>}</div>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    {notice && <div className="success-note" role="status">{notice}</div>}
    {loading ? <p className="loading-state">Loading sending profile…</p> : profile !== undefined && <form className="form-card sending-profile-form" onSubmit={(event) => { event.preventDefault(); runAction(profile ? 'save' : 'create') }}>
      {!profile && <p className="muted">No Gmail profile configured.</p>}
      <label htmlFor="profile-name">Profile name</label><input id="profile-name" maxLength={160} value={form.name} disabled={!!pending} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
      <label htmlFor="profile-display-name">Display name</label><input id="profile-display-name" maxLength={120} value={form.from_name} disabled={!!pending} onChange={(event) => setForm({ ...form, from_name: event.target.value })} required />
      <label htmlFor="profile-email">Gmail address</label><input id="profile-email" type="email" value={form.from_email} disabled={!!pending} onChange={(event) => setForm({ ...form, from_email: event.target.value })} required />
      {profile && <p className="credential-indicator">App password: {profile.credential_configured ? 'Configured' : 'Not configured'}</p>}
      <label htmlFor="profile-password">Google app password</label><input id="profile-password" type="password" autoComplete="new-password" value={password} disabled={!!pending} onChange={(event) => setPassword(event.target.value)} required={!profile} />
      {profile && <small>Enter a new app password only when replacing the stored credential. Save metadata does not replace it.</small>}
      <div className="form-actions sending-profile-actions">
        <button className="primary-button" disabled={!!pending}>{profile ? pending === 'save' ? 'Saving…' : 'Save metadata' : pending === 'create' ? 'Creating…' : 'Create profile'}</button>
        {profile && <button className="secondary-button" type="button" disabled={!!pending || !password.trim()} onClick={() => runAction('replace')}>{pending === 'replace' ? 'Replacing…' : 'Replace password'}</button>}
      </div>
      {profile && <div className="sending-profile-actions">
        <button className="small-button" type="button" disabled={!!pending} onClick={() => runAction('test')}>{pending === 'test' ? 'Sending test…' : 'Send test'}</button>
        <button className="small-button" type="button" disabled={!!pending} onClick={() => runAction('toggle')}>{pending === 'toggle' ? profile.enabled ? 'Disabling…' : 'Enabling…' : profile.enabled ? 'Disable' : 'Enable'}</button>
        <button className="danger-link" type="button" disabled={!!pending} onClick={() => runAction('delete')}>{pending === 'delete' ? 'Deleting…' : 'Delete'}</button>
      </div>}
    </form>}
  </section>
}

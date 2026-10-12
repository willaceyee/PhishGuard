import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import SendingProfiles from './SendingProfiles.jsx'
import Dashboard from './Dashboard.jsx'
import { createSendingProfile, deleteSendingProfile, getSendingProfile, listTemplates, listUsers, testSendingProfile, updateSendingProfile } from '../services/api.js'

vi.mock('../services/api.js', () => ({
  getSendingProfile: vi.fn(),
  createSendingProfile: vi.fn(),
  updateSendingProfile: vi.fn(),
  testSendingProfile: vi.fn(),
  deleteSendingProfile: vi.fn(),
  listTemplates: vi.fn(),
  listUsers: vi.fn(),
}))

const profile = {
  profile_id: 1, name: 'Awareness Gmail', provider: 'gmail', from_name: 'Security team',
  from_email: 'security@gmail.com', credential_configured: true, enabled: false,
  last_tested_at: null, last_test_succeeded: false,
  created_at: '2026-10-06T00:00:00+00:00', updated_at: '2026-10-06T00:00:00+00:00',
}
const password = 'abcd efgh ijkl mnop'
const approvedUsers = [
  { user_id: 7, name: 'Approved User', email: 'approved@example.com', simulation_email_approved: true },
  { user_id: 8, name: 'Not Approved', email: 'blocked@example.com', simulation_email_approved: false },
]
const templates = [
  { template_id: 11, template_name: 'Document review', subject: 'Review the document', body: 'Open [INSERT CAMPAIGN TRACKING LINK]' },
  { template_id: 12, template_name: 'Password reset', subject: 'Reset your password', body: 'Reset instructions' },
]

beforeEach(() => {
  vi.resetAllMocks()
  getSendingProfile.mockResolvedValue({ profile })
  listUsers.mockResolvedValue({ users: approvedUsers })
  listTemplates.mockResolvedValue({ templates })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function openProfile() {
  render(<SendingProfiles token="admin-token" />)
  await screen.findByDisplayValue('Awareness Gmail')
}

function selectTestRecipient() {
  fireEvent.change(screen.getByLabelText('Test send to'), { target: { value: '7' } })
}

function selectTestTemplate() {
  fireEvent.change(screen.getByLabelText('Test email template'), { target: { value: '11' } })
}

function enterMetadata() {
  fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Awareness Gmail' } })
  fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Security team' } })
  fireEvent.change(screen.getByLabelText('Gmail address'), { target: { value: 'security@gmail.com' } })
}

describe('Sending Profiles workspace', () => {
  it('waits for loading before allowing an absent profile to be created', async () => {
    let resolve
    getSendingProfile.mockImplementation(() => new Promise((done) => { resolve = done }))
    render(<SendingProfiles token="admin-token" />)
    expect(screen.getByText('Loading sending profile…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create profile' })).not.toBeInTheDocument()
    await act(async () => resolve({ profile: null }))
    expect(screen.getByText('No Gmail profile configured.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create profile' })).toBeEnabled()
    expect(getSendingProfile).toHaveBeenCalledWith('admin-token')
  })

  it('creates the profile and clears the submitted password immediately on success', async () => {
    getSendingProfile.mockResolvedValue({ profile: null })
    createSendingProfile.mockResolvedValue({ profile })
    render(<SendingProfiles token="admin-token" />)
    await screen.findByRole('button', { name: 'Create profile' })
    enterMetadata()
    const input = screen.getByLabelText('Google app password')
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveAttribute('autocomplete', 'new-password')
    fireEvent.change(input, { target: { value: password } })
    fireEvent.click(screen.getByRole('button', { name: 'Create profile' }))
    await screen.findByText('Profile created.')
    expect(createSendingProfile).toHaveBeenCalledWith('admin-token', {
      name: 'Awareness Gmail', from_name: 'Security team', from_email: 'security@gmail.com', app_password: password,
    })
    expect(screen.getByLabelText('Google app password')).toHaveValue('')
    expect(document.body.innerHTML).not.toContain(password)
    expect(screen.getByText('App password: Configured')).toBeInTheDocument()
  })

  it('shows only credential configuration and never populates the password from API data', async () => {
    getSendingProfile.mockResolvedValue({ profile: { ...profile, app_password: 'stored-plaintext', encrypted_app_password: 'stored-ciphertext' } })
    await openProfile()
    expect(screen.getByText('App password: Configured')).toBeInTheDocument()
    expect(screen.getByLabelText('Google app password')).toHaveValue('')
    expect(document.body.innerHTML).not.toContain('stored-plaintext')
    expect(document.body.innerHTML).not.toContain('stored-ciphertext')
  })

  it('shows an unconfigured credential without a stored password', async () => {
    getSendingProfile.mockResolvedValue({ profile: { ...profile, credential_configured: false } })
    await openProfile()
    expect(screen.getByText('App password: Not configured')).toBeInTheDocument()
    expect(screen.getByLabelText('Google app password')).toHaveValue('')
  })

  it('shows not tested when the saved profile has no test timestamp', async () => {
    await openProfile()
    expect(screen.getByText(/Last test:/)).toHaveTextContent('Last test: Not tested')
    expect(document.querySelector('time')).not.toBeInTheDocument()
  })

  it.each([
    [true, 'Succeeded'],
    [false, 'Failed'],
  ])('shows the persisted test result %s and saved timestamp on reopening', async (succeeded, result) => {
    getSendingProfile.mockResolvedValue({ profile: { ...profile, last_test_succeeded: succeeded, last_tested_at: '2026-10-06T03:15:00+00:00' } })
    await openProfile()
    expect(screen.getByText(/Last test:/)).toHaveTextContent(`Last test: ${result}`)
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-10-06T03:15:00+00:00')
    expect(document.querySelector('time')).toHaveTextContent('2026')
    expect(document.querySelector('time')).not.toHaveTextContent('Invalid Date')
  })

  it.each([
    ['offset-free UTC', '2026-10-06T03:15:00', '2026-10-06T03:15:00Z'],
    ['UTC Z', '2026-10-06T03:15:00Z', '2026-10-06T03:15:00Z'],
    ['positive offset', '2026-10-06T11:15:00+08:00', '2026-10-06T11:15:00+08:00'],
    ['negative offset', '2026-10-05T20:15:00-07:00', '2026-10-05T20:15:00-07:00'],
  ])('displays the correct UTC instant for a saved %s timestamp', async (_format, timestamp, expectedDateTime) => {
    getSendingProfile.mockResolvedValue({ profile: { ...profile, last_test_succeeded: true, last_tested_at: timestamp } })
    await openProfile()
    const time = document.querySelector('time')
    expect(time).toHaveTextContent(new Date('2026-10-06T03:15:00Z').toLocaleString())
    expect(time).toHaveAttribute('datetime', expectedDateTime)
  })

  it('saves metadata without including a typed replacement password', async () => {
    updateSendingProfile.mockResolvedValue({ profile: { ...profile, name: 'Updated name' } })
    await openProfile()
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Updated name' } })
    fireEvent.change(screen.getByLabelText('Google app password'), { target: { value: password } })
    fireEvent.click(screen.getByRole('button', { name: 'Save metadata' }))
    await screen.findByText('Metadata saved.')
    expect(updateSendingProfile).toHaveBeenCalledWith('admin-token', {
      name: 'Updated name', from_name: 'Security team', from_email: 'security@gmail.com',
    })
  })

  it('replaces only the password and clears it after success', async () => {
    updateSendingProfile.mockResolvedValue({ profile })
    await openProfile()
    expect(screen.getByRole('button', { name: 'Replace password' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Unsaved name' } })
    fireEvent.change(screen.getByLabelText('Google app password'), { target: { value: password } })
    fireEvent.click(screen.getByRole('button', { name: 'Replace password' }))
    await screen.findByText('App password replaced.')
    expect(updateSendingProfile).toHaveBeenCalledWith('admin-token', { app_password: password })
    expect(screen.getByLabelText('Google app password')).toHaveValue('')
    expect(document.body.innerHTML).not.toContain(password)
    expect(screen.getByLabelText('Profile name')).toHaveValue('Unsaved name')
  })

  it('sends a test email and displays success', async () => {
    testSendingProfile.mockResolvedValue({ profile: { ...profile, last_test_succeeded: true, last_tested_at: '2026-10-07T00:00:00+00:00' } })
    await openProfile()
    expect(screen.getByRole('option', { name: 'Approved User — approved@example.com' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Not Approved/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Test send to'), { target: { value: '7' } })
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Test email sent to approved@example.com.')
    expect(testSendingProfile).toHaveBeenCalledWith('admin-token', 7, 11)
  })

  it('requires an approved test recipient and template before enabling Send test', async () => {
    await openProfile()
    expect(listUsers).toHaveBeenCalledWith('admin-token')
    expect(listTemplates).toHaveBeenCalledWith('admin-token')
    expect(screen.getByLabelText('Test send to')).toHaveValue('')
    expect(screen.getByLabelText('Test email template')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled()
    selectTestRecipient()
    expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled()
    selectTestTemplate()
    expect(screen.getByRole('button', { name: 'Send test' })).toBeEnabled()
  })

  it('keeps profile controls available when approved recipients cannot be loaded', async () => {
    listUsers.mockRejectedValue(new Error('network failed'))
    await openProfile()
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load approved test recipients. Other profile controls are still available.')
    expect(screen.getByRole('button', { name: 'Save metadata' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Enable' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled()
  })

  it('keeps profile controls available when templates cannot be loaded', async () => {
    listTemplates.mockRejectedValue(new Error('network failed'))
    await openProfile()
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load test email templates. Other profile controls are still available.')
    expect(screen.getByRole('button', { name: 'Save metadata' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Enable' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Send test' })).toBeDisabled()
  })

  it('displays a safe provider failure in the dashboard error style', async () => {
    testSendingProfile.mockRejectedValue(new Error('gmail_authentication_failed'))
    await openProfile()
    selectTestRecipient()
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Gmail authentication failed. Check the Google app password.')
    expect(screen.getByRole('alert')).toHaveClass('dashboard-error')
  })

  it('explains when the selected template has an invalid email subject', async () => {
    testSendingProfile.mockRejectedValue(new Error('gmail_test_template_invalid'))
    await openProfile()
    selectTestRecipient()
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The selected template has an invalid email subject.')
  })

  it('refreshes a failed test result instead of retaining the previous successful test', async () => {
    getSendingProfile.mockResolvedValueOnce({ profile: { ...profile, last_test_succeeded: true, last_tested_at: '2026-10-06T03:15:00+00:00' } })
      .mockResolvedValueOnce({ profile: { ...profile, last_test_succeeded: false, last_tested_at: '2026-10-07T03:15:00+00:00' } })
    testSendingProfile.mockRejectedValue(new Error('gmail_authentication_failed'))
    await openProfile()
    expect(screen.getByText(/Last test:/)).toHaveTextContent('Last test: Succeeded')
    selectTestRecipient()
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    await screen.findByRole('alert')
    expect(await screen.findByText(/Last test: Failed/)).toBeInTheDocument()
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-10-07T03:15:00+00:00')
    expect(screen.getByRole('alert')).toHaveTextContent('Gmail authentication failed. Check the Google app password.')
  })

  it('marks test status unavailable when failure refresh fails and restores persisted status after saving', async () => {
    getSendingProfile.mockResolvedValueOnce({ profile: { ...profile, last_test_succeeded: true, last_tested_at: '2026-10-06T03:15:00+00:00' } })
      .mockRejectedValueOnce(new Error('network failed'))
    testSendingProfile.mockRejectedValue(new Error('gmail_authentication_failed'))
    updateSendingProfile.mockResolvedValue({ profile: { ...profile, name: 'Updated name', last_test_succeeded: false, last_tested_at: '2026-10-07T03:15:00+00:00' } })
    await openProfile()
    expect(screen.getByText(/Last test:/)).toHaveTextContent('Last test: Succeeded')
    selectTestRecipient()
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    expect(await screen.findByText('Last test: Unavailable')).toBeInTheDocument()
    expect(screen.getByText(/Last test:/)).not.toHaveTextContent('Succeeded')
    expect(document.querySelector('time')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Gmail authentication failed. Check the Google app password.')
    expect(screen.getByLabelText('Profile name')).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Save metadata' })).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Updated name' } })
    expect(screen.getByText('Last test: Unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save metadata' }))
    await screen.findByText('Metadata saved.')
    expect(screen.getByText(/Last test:/)).toHaveTextContent('Last test: Failed')
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-10-07T03:15:00+00:00')
  })

  it('does not render unexpected error objects or credential-bearing messages', async () => {
    testSendingProfile.mockRejectedValue({ message: `SMTP raw credentials ${password}`, response: { secret: 'stored-ciphertext' } })
    await openProfile()
    selectTestRecipient()
    selectTestTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Send test' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to complete the sending profile request. Please try again.')
    expect(document.body.innerHTML).not.toContain(password)
    expect(document.body.innerHTML).not.toContain('stored-ciphertext')
  })

  it('enables and disables the single profile', async () => {
    updateSendingProfile.mockResolvedValueOnce({ profile: { ...profile, enabled: true } }).mockResolvedValueOnce({ profile })
    await openProfile()
    expect(screen.getByText('Disabled')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Enable' }))
    await screen.findByText('Enabled')
    expect(updateSendingProfile).toHaveBeenNthCalledWith(1, 'admin-token', { enabled: true })
    fireEvent.click(screen.getByRole('button', { name: 'Disable' }))
    await screen.findByText('Disabled')
    expect(updateSendingProfile).toHaveBeenNthCalledWith(2, 'admin-token', { enabled: false })
  })

  it('requires delete confirmation and returns to the empty form after deleting', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    deleteSendingProfile.mockResolvedValue(null)
    await openProfile()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(deleteSendingProfile).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await screen.findByText('No Gmail profile configured.')
    expect(confirm).toHaveBeenCalledWith('Delete Awareness Gmail?')
    expect(deleteSendingProfile).toHaveBeenCalledWith('admin-token')
    expect(screen.getByLabelText('Profile name')).toHaveValue('')
    expect(screen.getByLabelText('Google app password')).toHaveValue('')
  })

  it.each([
    ['Save metadata', 'Saving…', updateSendingProfile],
    ['Replace password', 'Replacing…', updateSendingProfile],
    ['Send test', 'Sending test…', testSendingProfile],
    ['Enable', 'Enabling…', updateSendingProfile],
    ['Delete', 'Deleting…', deleteSendingProfile],
  ])('blocks duplicate and overlapping requests during %s', async (button, pending, api) => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let resolve
    api.mockImplementation(() => new Promise((done) => { resolve = done }))
    await openProfile()
    fireEvent.change(screen.getByLabelText('Google app password'), { target: { value: password } })
    if (button === 'Send test') {
      selectTestRecipient()
      selectTestTemplate()
    }
    fireEvent.click(screen.getByRole('button', { name: button }))
    const pendingButton = screen.getByRole('button', { name: pending })
    expect(pendingButton).toBeDisabled()
    screen.getAllByRole('button').forEach((action) => expect(action).toBeDisabled())
    fireEvent.click(pendingButton)
    expect(api).toHaveBeenCalledTimes(1)
    await act(async () => resolve(button === 'Delete' ? null : { profile }))
  })

  it('blocks duplicate creation while the request is pending', async () => {
    getSendingProfile.mockResolvedValue({ profile: null })
    let resolve
    createSendingProfile.mockImplementation(() => new Promise((done) => { resolve = done }))
    render(<SendingProfiles token="admin-token" />)
    await screen.findByRole('button', { name: 'Create profile' })
    enterMetadata()
    fireEvent.change(screen.getByLabelText('Google app password'), { target: { value: password } })
    fireEvent.click(screen.getByRole('button', { name: 'Create profile' }))
    expect(screen.getByRole('button', { name: 'Creating…' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Creating…' }))
    expect(createSendingProfile).toHaveBeenCalledTimes(1)
    await act(async () => resolve({ profile }))
  })

  it('displays loading errors without offering to create a possibly existing profile', async () => {
    getSendingProfile.mockRejectedValue(new Error('network failed'))
    render(<SendingProfiles token="admin-token" />)
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: 'Create profile' })).not.toBeInTheDocument()
  })

  it('opens Sending Profiles from dashboard navigation', async () => {
    render(<Dashboard token="admin-token" />)
    fireEvent.click(screen.getByRole('button', { name: 'Sending Profiles' }))
    await screen.findByDisplayValue('Awareness Gmail')
    expect(screen.getByRole('heading', { level: 1, name: 'Sending Profiles' })).toBeInTheDocument()
  })
})

describe('sending profile API routes', () => {
  it('uses the single-profile routes with bearer authentication and explicit payloads', async () => {
    const api = await vi.importActual('../services/api.js')
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ profile }) })
    vi.stubGlobal('fetch', fetch)
    await api.getSendingProfile('admin-token')
    await api.createSendingProfile('admin-token', { name: 'Name', app_password: password })
    await api.updateSendingProfile('admin-token', { enabled: true })
    await api.testSendingProfile('admin-token', 7, 11)
    fetch.mockResolvedValueOnce({ ok: true, status: 204 })
    await api.deleteSendingProfile('admin-token')
    expect(fetch.mock.calls).toEqual([
      ['/api/sending-profile', { headers: { Authorization: 'Bearer admin-token' } }],
      ['/api/sending-profile', { method: 'POST', body: JSON.stringify({ name: 'Name', app_password: password }), headers: { Authorization: 'Bearer admin-token', 'Content-Type': 'application/json' } }],
      ['/api/sending-profile', { method: 'PATCH', body: '{"enabled":true}', headers: { Authorization: 'Bearer admin-token', 'Content-Type': 'application/json' } }],
      ['/api/sending-profile/test', { method: 'POST', body: '{"recipient_user_id":7,"template_id":11}', headers: { Authorization: 'Bearer admin-token', 'Content-Type': 'application/json' } }],
      ['/api/sending-profile', { method: 'DELETE', headers: { Authorization: 'Bearer admin-token' } }],
    ])
  })
})

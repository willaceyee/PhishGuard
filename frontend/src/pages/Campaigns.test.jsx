import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Campaigns from './Campaigns.jsx'

const profile = {
  profile_id: 7, name: 'Awareness Gmail', provider: 'gmail', from_name: 'Security team',
  from_email: 'security@gmail.com', credential_configured: true, enabled: true,
  last_tested_at: '2026-10-06T00:00:00+00:00', last_test_succeeded: true,
  created_at: '2026-10-06T00:00:00+00:00', updated_at: '2026-10-06T00:00:00+00:00',
}
const user = { user_id: 1, name: 'Approved user', email: 'approved@example.com', simulation_email_approved: true }
const campaign = { campaign_id: 3, campaign_name: 'Awareness exercise', template_id: 2, status: 'draft', sending_profile_id: 7, delivery_method: 'gmail', sending_profile: profile }
const gmailPreview = {
  delivery_method: 'gmail', real_delivery: true, profile, profile_ready: true,
  delivery_enabled: true, public_url_safe: true, campaign_recipient_limit: 10,
  hourly_delivery_limit: 20, hourly_delivered_count: 4,
  from: 'Security team <security@gmail.com>', subject: '[SECURITY SIMULATION] Awareness',
  allowed_recipients: [user], blocked_recipients: [], already_delivered: 0,
  confirmation_phrase: 'SEND 1 REAL EMAIL',
}
let savedProfile
let preview
let requests

beforeEach(() => {
  savedProfile = profile
  preview = gmailPreview
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (path, options = {}) => {
    requests.push({ path, ...options })
    let body
    if (path === '/api/sending-profile') body = { profile: savedProfile }
    else if (path === '/api/users') body = { users: [user] }
    else if (path === '/api/templates') body = { templates: [{ template_id: 2, template_name: 'Awareness' }] }
    else if (path === '/api/campaigns' && options.method === 'POST') body = { campaign: { ...campaign, ...JSON.parse(options.body) } }
    else if (path === '/api/campaigns') body = { campaigns: [campaign] }
    else if (path === '/api/campaigns/3/recipients') body = { recipients: [] }
    else if (path === '/api/campaigns/3/delivery-preview') body = { preview }
    else if (path === '/api/campaigns/3/send') body = { delivered: 1 }
    else throw new Error(`Unexpected request: ${path}`)
    return { ok: true, status: 200, json: async () => body }
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

async function openCampaigns() {
  render(<Campaigns token="admin-token" onDataChange={vi.fn()} />)
  await screen.findByRole('button', { name: 'Recipients & delivery' })
}

async function openPreview() {
  await openCampaigns()
  fireEvent.click(screen.getByRole('button', { name: 'Recipients & delivery' }))
  await screen.findByRole('heading', { name: 'Email delivery preview' })
}

function confirm(value = preview.confirmation_phrase) {
  fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value } })
}

describe('Campaign delivery selection', () => {
  it('loads the safe profile and creates new campaigns with Mailpit by default', async () => {
    await openCampaigns()
    expect(screen.getByLabelText('Delivery method')).toHaveValue('')
    expect(screen.getByRole('option', { name: /Mailpit.*local test/i })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Campaign name'), { target: { value: 'Local exercise' } })
    fireEvent.change(screen.getByLabelText('Email template'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
    await screen.findByRole('heading', { name: 'Local exercise' })
    const created = requests.find((request) => request.path === '/api/campaigns' && request.method === 'POST')
    expect(JSON.parse(created.body)).toEqual({ campaign_name: 'Local exercise', template_id: 2, status: 'draft', sending_profile_id: null })
    expect(requests.find((request) => request.path === '/api/sending-profile').headers.Authorization).toBe('Bearer admin-token')
  })

  it.each([
    ['missing', null],
    ['disabled', { ...profile, enabled: false }],
    ['without a credential', { ...profile, credential_configured: false }],
  ])('does not offer a %s Gmail profile', async (_state, value) => {
    savedProfile = value
    await openCampaigns()
    expect(screen.queryByRole('option', { name: /Gmail/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Delivery method')).toHaveValue('')
  })

  it('creates a Gmail campaign with the selected profile and resets to Mailpit', async () => {
    await openCampaigns()
    fireEvent.change(screen.getByLabelText('Delivery method'), { target: { value: '7' } })
    expect(screen.getByText(/Gmail sends real external email/i)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Campaign name'), { target: { value: 'Gmail exercise' } })
    fireEvent.change(screen.getByLabelText('Email template'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
    await screen.findByRole('heading', { name: 'Gmail exercise' })
    const created = requests.find((request) => request.path === '/api/campaigns' && request.method === 'POST')
    expect(JSON.parse(created.body)).toEqual({ campaign_name: 'Gmail exercise', template_id: 2, status: 'draft', sending_profile_id: 7 })
    expect(screen.getByLabelText('Delivery method')).toHaveValue('')
  })
})

describe('Gmail delivery preview', () => {
  it('shows real delivery, readiness, both limits and the exact backend confirmation', async () => {
    preview = { ...gmailPreview, allowed_recipients: [user, { ...user, user_id: 2 }], confirmation_phrase: 'SEND 2 REAL EMAILS' }
    await openPreview()
    expect(screen.getByText('Gmail — real external delivery')).toBeInTheDocument()
    expect(screen.getByText(/Gmail sends real external email/i)).toBeInTheDocument()
    expect(screen.getByText('Campaign limit').nextElementSibling).toHaveTextContent('10 recipients')
    expect(screen.getByText('Hourly limit').nextElementSibling).toHaveTextContent('20 emails')
    expect(screen.getByText('Gmail profile').nextElementSibling).toHaveTextContent('Ready')
    expect(screen.getByText('SEND 2 REAL EMAILS')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send real Gmail emails' })
    expect(send).toBeDisabled()
    confirm('SEND 2 REAL EMAILS ')
    expect(send).toBeDisabled()
    confirm('SEND 2 REAL EMAILS')
    expect(send).toBeEnabled()
  })

  it('uses the supplied phrase instead of rebuilding it from recipient counts', async () => {
    preview = { ...gmailPreview, confirmation_phrase: 'SERVER PROVIDED CONFIRMATION' }
    await openPreview()
    expect(screen.getByText('SERVER PROVIDED CONFIRMATION')).toBeInTheDocument()
    confirm('SEND 1 REAL EMAIL')
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeDisabled()
    confirm('SERVER PROVIDED CONFIRMATION')
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeEnabled()
  })

  it.each([
    ['blocked recipients', { blocked_recipients: [{ ...user, email: 'blocked@example.com', simulation_email_approved: false }] }, 'Delivery blocked'],
    ['disabled delivery', { delivery_enabled: false }, 'Delivery disabled'],
    ['an unready profile', { profile_ready: false }, 'Gmail profile not ready'],
    ['an unsafe URL', { public_url_safe: false }, 'Unsafe public URL'],
    ['no remaining approved recipients', { allowed_recipients: [] }, 'No approved recipients remain'],
    ['the campaign limit', { allowed_recipients: Array.from({ length: 11 }, (_, index) => ({ ...user, user_id: index + 1 })) }, 'Campaign limit exceeded'],
    ['the hourly limit', { hourly_delivered_count: 20 }, 'Hourly limit exceeded'],
  ])('disables real delivery for %s even with matching confirmation', async (_reason, changes, warning) => {
    preview = { ...gmailPreview, ...changes }
    await openPreview()
    confirm()
    expect(screen.getByText(warning)).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send real Gmail emails' })
    expect(send).toBeDisabled()
    fireEvent.click(send)
    expect(requests.some((request) => request.path.endsWith('/send'))).toBe(false)
    if (!preview.public_url_safe) expect(screen.getByText(/public HTTPS URL.*localhost.*private/i)).toBeInTheDocument()
  })

  it('allows delivery at the campaign and hourly boundaries', async () => {
    preview = { ...gmailPreview, allowed_recipients: Array.from({ length: 10 }, (_, index) => ({ ...user, user_id: index + 1 })), hourly_delivered_count: 10, confirmation_phrase: 'SEND 10 REAL EMAILS' }
    await openPreview()
    confirm()
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeEnabled()
  })

  it('sends the exact confirmation and reports Gmail delivery without a Mailpit success claim', async () => {
    await openPreview()
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Send real Gmail emails' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 authorized simulation emails delivered through Gmail.')
    await waitFor(() => expect(screen.getByLabelText(/to confirm/)).toHaveValue(''))
    const sent = requests.find((request) => request.path === '/api/campaigns/3/send')
    expect(JSON.parse(sent.body)).toEqual({ confirmation: 'SEND 1 REAL EMAIL' })
  })
})

describe('Mailpit delivery compatibility', () => {
  it('labels local delivery and retains the existing confirmation, button and success notice', async () => {
    preview = { ...gmailPreview, delivery_method: 'mailpit', real_delivery: false, profile: null, profile_ready: true, campaign_recipient_limit: 50, hourly_delivery_limit: 100, confirmation_phrase: 'SEND 1 AUTHORIZED EMAIL' }
    await openPreview()
    expect(screen.getByText('Mailpit — local test delivery', { selector: 'p' })).toBeInTheDocument()
    expect(screen.queryByText(/Gmail sends real external email/i)).not.toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send to local Mailpit' })
    expect(send).toBeDisabled()
    confirm()
    expect(send).toBeEnabled()
    fireEvent.click(send)
    expect(await screen.findByRole('status')).toHaveTextContent('1 authorized simulation emails delivered to the local Mailpit inbox.')
  })
})

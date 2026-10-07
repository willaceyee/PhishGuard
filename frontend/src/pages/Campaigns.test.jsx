import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Campaigns from './Campaigns.jsx'

const profile = {
  profile_id: 7, name: 'Awareness Gmail', provider: 'gmail', from_name: 'Security team',
  from_email: 'security@gmail.com', credential_configured: true, enabled: true,
  last_tested_at: '2026-10-06T00:00:00+00:00', last_test_succeeded: true,
  created_at: '2026-10-06T00:00:00+00:00', updated_at: '2026-10-06T00:00:00+00:00',
}
const user = { user_id: 1, name: 'Approved user', email: 'approved@example.com', simulation_email_approved: true }
const campaign = { campaign_id: 3, campaign_name: 'Awareness exercise', template_id: 2, status: 'draft', sending_profile_id: 7, delivery_method: 'gmail', sending_profile: profile }
const otherCampaign = { ...campaign, campaign_id: 4, campaign_name: 'Second exercise' }
const recipient = { recipient_id: 31, user, tracking_url: 'https://training.example.org/r/first' }
const otherRecipient = { recipient_id: 41, user: { ...user, user_id: 2, name: 'Second user', email: 'second@example.com' }, tracking_url: 'https://training.example.org/r/second' }
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
let savedCampaigns
let deferredRequests

beforeEach(() => {
  savedProfile = profile
  preview = gmailPreview
  requests = []
  savedCampaigns = [campaign]
  deferredRequests = []
  vi.stubGlobal('fetch', vi.fn(async (path, options = {}) => {
    requests.push({ path, ...options })
    const deferredIndex = deferredRequests.findIndex((request) => request.path === path && request.method === (options.method || 'GET'))
    if (deferredIndex !== -1) return deferredRequests.splice(deferredIndex, 1)[0].promise
    let body
    if (path === '/api/sending-profile') body = { profile: savedProfile }
    else if (path === '/api/users') body = { users: [user] }
    else if (path === '/api/templates') body = { templates: [{ template_id: 2, template_name: 'Awareness' }] }
    else if (path === '/api/campaigns' && options.method === 'POST') body = { campaign: { ...campaign, ...JSON.parse(options.body), campaign_id: 8 } }
    else if (path === '/api/campaigns') body = { campaigns: savedCampaigns }
    else if (/^\/api\/campaigns\/[34]\/recipients$/.test(path)) body = options.method === 'POST' ? { recipients: [recipient], skipped_existing: 0 } : { recipients: [] }
    else if (/^\/api\/campaigns\/[34]\/delivery-preview$/.test(path)) body = { preview }
    else if (/^\/api\/campaigns\/[34]\/send$/.test(path)) body = { delivered: 1 }
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
  await screen.findAllByRole('button', { name: 'Recipients & delivery' })
}

function deferResponse(path, method = 'GET') {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  deferredRequests.push({ path, method, promise })
  return (body) => resolve({ ok: true, status: 200, json: async () => body })
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

describe('Campaign review response ordering', () => {
  it('keeps the selected campaign recipients and blocked preview when an earlier campaign resolves last', async () => {
    savedCampaigns = [campaign, otherCampaign]
    const firstRecipients = deferResponse('/api/campaigns/3/recipients')
    const firstPreview = deferResponse('/api/campaigns/3/delivery-preview')
    const secondRecipients = deferResponse('/api/campaigns/4/recipients')
    const secondPreview = deferResponse('/api/campaigns/4/delivery-preview')
    await openCampaigns()
    const open = screen.getAllByRole('button', { name: 'Recipients & delivery' })
    fireEvent.click(open[0])
    fireEvent.click(open[1])
    await act(async () => {
      secondRecipients({ recipients: [otherRecipient] })
      secondPreview({ preview: { ...gmailPreview, profile_ready: false, subject: '[SECURITY SIMULATION] Second' } })
    })
    confirm('SEND 1 REAL EMAIL')
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeDisabled()
    await act(async () => {
      firstRecipients({ recipients: [recipient] })
      firstPreview({ preview: gmailPreview })
    })
    expect(screen.getByText(otherRecipient.tracking_url)).toBeInTheDocument()
    expect(screen.queryByText(recipient.tracking_url)).not.toBeInTheDocument()
    expect(screen.getByText('Gmail profile not ready')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send real Gmail emails' })
    expect(send).toBeDisabled()
    fireEvent.click(send)
    expect(requests.some((request) => request.path.endsWith('/send'))).toBe(false)
  })

  it('clears a previous review while loading and ignores older responses for the same campaign', async () => {
    await openPreview()
    confirm()
    const olderRecipients = deferResponse('/api/campaigns/3/recipients')
    const olderPreview = deferResponse('/api/campaigns/3/delivery-preview')
    const latestRecipients = deferResponse('/api/campaigns/3/recipients')
    const latestPreview = deferResponse('/api/campaigns/3/delivery-preview')
    fireEvent.click(screen.getByRole('button', { name: 'Recipients & delivery' }))
    expect(screen.queryByRole('button', { name: 'Send real Gmail emails' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Recipients & delivery' }))
    await act(async () => {
      latestRecipients({ recipients: [otherRecipient] })
      latestPreview({ preview: { ...gmailPreview, public_url_safe: false } })
    })
    confirm('SEND 1 REAL EMAIL')
    await act(async () => {
      olderRecipients({ recipients: [recipient] })
      olderPreview({ preview: gmailPreview })
    })
    expect(screen.getByText(otherRecipient.tracking_url)).toBeInTheDocument()
    expect(screen.queryByText(recipient.tracking_url)).not.toBeInTheDocument()
    expect(screen.getByText('Unsafe public URL')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeDisabled()
  })

  it.each(['assignment', 'refresh'])('ignores an earlier campaign recipient %s after selecting another campaign', async (stage) => {
    savedCampaigns = [campaign, otherCampaign]
    await openCampaigns()
    const open = screen.getAllByRole('button', { name: 'Recipients & delivery' })
    fireEvent.click(open[0])
    await screen.findByRole('heading', { name: 'Email delivery preview' })
    const assignment = stage === 'assignment' ? deferResponse('/api/campaigns/3/recipients', 'POST') : null
    const oldRecipients = deferResponse('/api/campaigns/3/recipients')
    const oldPreview = deferResponse('/api/campaigns/3/delivery-preview')
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Assign selected users' }))
    if (stage === 'refresh') await waitFor(() => expect(requests.filter((request) => request.path === '/api/campaigns/3/recipients' && !request.method)).toHaveLength(2))
    preview = { ...gmailPreview, profile_ready: false }
    fireEvent.click(open[1])
    await screen.findByText('Gmail profile not ready')
    fireEvent.click(screen.getByRole('checkbox'))
    await act(async () => {
      assignment?.({ recipients: [recipient], skipped_existing: 0 })
      oldRecipients({ recipients: [recipient] })
      oldPreview({ preview: gmailPreview })
    })
    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(screen.queryByText(recipient.tracking_url)).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByText('Gmail profile not ready')).toBeInTheDocument()
    confirm('SEND 1 REAL EMAIL')
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeDisabled()
  })

  it.each(['send', 'refresh'])('keeps the new selection unchanged when an earlier campaign %s completes', async (stage) => {
    savedCampaigns = [campaign, otherCampaign]
    await openCampaigns()
    const open = screen.getAllByRole('button', { name: 'Recipients & delivery' })
    fireEvent.click(open[0])
    await screen.findByRole('heading', { name: 'Email delivery preview' })
    const send = stage === 'send' ? deferResponse('/api/campaigns/3/send', 'POST') : null
    const oldPreview = deferResponse('/api/campaigns/3/delivery-preview')
    confirm('SEND 1 REAL EMAIL')
    fireEvent.click(screen.getByRole('button', { name: 'Send real Gmail emails' }))
    if (stage === 'refresh') await waitFor(() => expect(requests.filter((request) => request.path === '/api/campaigns/3/delivery-preview')).toHaveLength(2))
    preview = { ...gmailPreview, public_url_safe: false, subject: '[SECURITY SIMULATION] Second' }
    fireEvent.click(open[1])
    await screen.findByText('Unsafe public URL')
    confirm('SEND 1 REAL EMAIL')
    await act(async () => {
      send?.({ delivered: 1 })
      oldPreview({ preview: gmailPreview })
    })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByText('[SECURITY SIMULATION] Second')).toBeInTheDocument()
    expect(screen.getByLabelText(/to confirm/)).toHaveValue('SEND 1 REAL EMAIL')
    expect(screen.getByText('Unsafe public URL')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send real Gmail emails' })).toBeDisabled()
  })
})

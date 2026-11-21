import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import Overview from './Overview.jsx'
import { getCampaignQuizResults } from '../services/api.js'

vi.mock('../services/api.js', () => ({ getCampaignQuizResults: vi.fn() }))

const campaign = (overrides) => ({
  campaign_id: 1, campaign_name: 'Quarterly awareness exercise', status: 'completed',
  recipient_count: 3, unique_clicked: 2, unique_submitted: 1, training_started: 3, training_completed: 2,
  click_through_rate: 66.7, submission_rate: 33.3, training_completion_rate: 66.7,
  quiz_responses: 2, average_quiz_percentage: 90, ...overrides,
})

const user = (overrides) => ({
  user_id: 1, name: 'Alex Morgan', email: 'alex@example.test', department: 'Finance', risk_score: 72, risk_band: 'high',
  campaigns_assessed: 1, clicked_campaigns: 1, submitted_campaigns: 1, completed_training: 1, average_quiz_percentage: 80, ...overrides,
})

const data = (overrides = {}) => ({
  summary: {
    total_campaigns: 1, total_users: 3, total_recipients: 3, unique_clicked: 2, unique_submitted: 1,
    click_through_rate: 66.7, submission_rate: 33.3, training_completed: 2, training_completion_rate: 66.7,
    average_quiz_percentage: 90, high_risk_users: 1,
  },
  campaigns: [campaign()],
  user_risks: [
    user(),
    user({ user_id: 2, name: 'Priya Shah', department: 'Operations', risk_score: 55, risk_band: 'medium' }),
    user({ user_id: 3, name: 'Jordan Lee', department: 'Technology', risk_score: 0, risk_band: 'low' }),
  ],
  risk_method: { high_threshold: 60, medium_threshold: 30, weights: { clicked: 25, submitted: 45, training_incomplete: 20, quiz_gap_maximum: 10 } },
  ...overrides,
})

const kpi = (label) => screen.getByRole('heading', { level: 2, name: label }).closest('article')
const barRow = (label) => screen.getByText(label, { selector: '.bar-label' }).closest('.bar-row')

beforeEach(() => {
  getCampaignQuizResults.mockResolvedValue({ results: [
    { quiz_id: 1, score: 4, total_questions: 5, percentage: 80 },
    { quiz_id: 2, score: 5, total_questions: 5, percentage: 100 },
  ] })
})
afterEach(() => { cleanup(); vi.resetAllMocks() })

describe('Awareness overview', () => {
  it('shows summary counts with denominators and scope labels', async () => {
    render(<Overview data={data()} token="t" />)
    expect(kpi('Campaigns')).toHaveTextContent('1')
    expect(kpi('Campaigns')).toHaveTextContent('1 completed')
    expect(kpi('Assigned')).toHaveTextContent('Recipient assignments · 3 people')
    expect(kpi('Clicked')).toHaveTextContent('2 of 3')
    expect(kpi('Training complete')).toHaveTextContent('2 of 3')
    expect(kpi('Average quiz')).toHaveTextContent('90%')
    expect(kpi('Average quiz')).toHaveTextContent('Across 2 quiz responses')
    await screen.findByText('4/5')
  })

  it('distinguishes assignments from people when someone is in several campaigns', async () => {
    const overview = data({ summary: { ...data().summary, total_recipients: 4 } })
    render(<Overview data={overview} token="t" />)
    expect(kpi('Assigned')).toHaveTextContent('4')
    expect(kpi('Assigned')).toHaveTextContent('Recipient assignments · 3 people')
    await screen.findByText('4/5')
  })

  it('draws the selected campaign outcomes on a common count scale', async () => {
    render(<Overview data={data()} token="t" />)
    expect(barRow('Assigned')).toHaveTextContent('3')
    expect(barRow('Clicked')).toHaveTextContent('267%')
    expect(barRow('Simulated submissions')).toHaveTextContent('133%')
    expect(barRow('Completed training')).toHaveTextContent('267%')
    expect(screen.getByRole('img', { name: /Assigned 3, Clicked 2, Simulated submissions 1, Completed training 2, out of 3 recipients/ })).toBeInTheDocument()
    expect(await screen.findByText('5/5')).toBeInTheDocument()
    expect(getCampaignQuizResults).toHaveBeenCalledWith('t', 1)
  })

  it('lists coaching priorities by risk score with band labels', async () => {
    render(<Overview data={data()} token="t" />)
    const list = screen.getByRole('heading', { name: 'Coaching priorities' }).closest('section').querySelector('ol')
    const names = within(list).getAllByRole('listitem').map((item) => item.querySelector('strong').textContent)
    expect(names).toEqual(['Alex Morgan', 'Priya Shah', 'Jordan Lee'])
    expect(screen.getAllByText('Risk score (0–100)')).toHaveLength(3)
    const alex = screen.getByText('Alex Morgan').closest('li')
    expect(alex).toHaveTextContent('High')
    expect(alex).toHaveTextContent('72')
    await screen.findByText('4/5')
  })

  it('keeps zero values distinct from missing results', async () => {
    getCampaignQuizResults.mockResolvedValue({ results: [] })
    const overview = data({
      summary: { ...data().summary, unique_clicked: 0, training_completed: 0, average_quiz_percentage: null },
      campaigns: [campaign({ unique_clicked: 0, unique_submitted: 0, training_completed: 0, quiz_responses: 0, average_quiz_percentage: null })],
    })
    render(<Overview data={overview} token="t" />)
    expect(kpi('Clicked')).toHaveTextContent('0 of 3')
    expect(kpi('Average quiz')).toHaveTextContent('No results')
    expect(kpi('Average quiz')).toHaveTextContent('No quiz responses yet')
    expect(barRow('Clicked')).toHaveTextContent('00%')
    expect(await screen.findByText('No results', { selector: '.quiz-note' })).toBeInTheDocument()
  })

  it('offers a campaign selector when several campaigns exist', async () => {
    const second = campaign({ campaign_id: 2, campaign_name: 'Invoice exercise', recipient_count: 4, unique_clicked: 1, unique_submitted: 0, training_completed: 3 })
    render(<Overview data={data({ campaigns: [campaign(), second] })} token="t" />)
    await screen.findByText('4/5')
    fireEvent.change(screen.getByLabelText('Campaign'), { target: { value: '2' } })
    expect(screen.getByRole('heading', { name: 'Invoice exercise' })).toBeInTheDocument()
    expect(barRow('Assigned')).toHaveTextContent('4')
    expect(barRow('Completed training')).toHaveTextContent('375%')
    expect(getCampaignQuizResults).toHaveBeenLastCalledWith('t', 2)
  })

  it('shows empty states when there are no campaigns or assignments', () => {
    render(<Overview data={data({ campaigns: [], user_risks: [], summary: { ...data().summary, total_campaigns: 0, total_recipients: 0, unique_clicked: 0, training_completed: 0, average_quiz_percentage: null } })} token="t" />)
    expect(screen.getByText(/No campaigns yet/)).toBeInTheDocument()
    expect(screen.getAllByText(/^No results\./)).toHaveLength(2)
    expect(getCampaignQuizResults).not.toHaveBeenCalled()
  })

  it('reports loading and errors', () => {
    const { rerender } = render(<Overview loading token="t" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading campaign analytics')
    rerender(<Overview error="Server unavailable" token="t" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Server unavailable')
  })
})

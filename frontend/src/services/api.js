async function request(path, { token, ...options } = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(path, { ...options, headers })
  const body = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(body?.error || `Request failed with status ${response.status}`)
    error.status = response.status
    throw error
  }
  return body
}

export function login(email, password) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function getDashboardOverview(token) {
  return request('/api/dashboard/overview', { token })
}

export const listUsers = (token) => request('/api/users', { token })
export const createUser = (token, user) => request('/api/users', { token, method: 'POST', body: JSON.stringify(user) })
export const setUserEmailApproval = (token, userId, approved) => request(`/api/users/${userId}`, { token, method: 'PATCH', body: JSON.stringify({ simulation_email_approved: approved }) })
export const deleteUser = (token, userId) => request(`/api/users/${userId}`, { token, method: 'DELETE' })

export const listTemplates = (token) => request('/api/templates', { token })
export const createTemplate = (token, template) => request('/api/templates', { token, method: 'POST', body: JSON.stringify(template) })
export const updateTemplate = (token, templateId, template) => request(`/api/templates/${templateId}`, { token, method: 'PATCH', body: JSON.stringify(template) })
export const deleteTemplate = (token, templateId) => request(`/api/templates/${templateId}`, { token, method: 'DELETE' })

export const listCampaigns = (token) => request('/api/campaigns', { token })
export const createCampaign = (token, campaign) => request('/api/campaigns', { token, method: 'POST', body: JSON.stringify(campaign) })
export const deleteCampaign = (token, campaignId) => request(`/api/campaigns/${campaignId}`, { token, method: 'DELETE' })
export const assignRecipients = (token, campaignId, userIds) => request(`/api/campaigns/${campaignId}/recipients`, { token, method: 'POST', body: JSON.stringify({ user_ids: userIds }) })
export const listRecipients = (token, campaignId) => request(`/api/campaigns/${campaignId}/recipients`, { token })
export const getDeliveryPreview = (token, campaignId) => request(`/api/campaigns/${campaignId}/delivery-preview`, { token })
export const sendCampaignEmails = (token, campaignId, confirmation) => request(`/api/campaigns/${campaignId}/send`, { token, method: 'POST', body: JSON.stringify({ confirmation }) })

export const predictUrl = (token, url) => request('/api/detection/predict', { token, method: 'POST', body: JSON.stringify({ url }) })

export const getSendingProfile = (token) => request('/api/sending-profile', { token })
export const createSendingProfile = (token, profile) => request('/api/sending-profile', { token, method: 'POST', body: JSON.stringify(profile) })
export const updateSendingProfile = (token, profile) => request('/api/sending-profile', { token, method: 'PATCH', body: JSON.stringify(profile) })
export const testSendingProfile = (token) => request('/api/sending-profile/test', { token, method: 'POST' })
export const deleteSendingProfile = (token) => request('/api/sending-profile', { token, method: 'DELETE' })

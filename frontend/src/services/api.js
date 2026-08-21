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

import { useEffect, useState } from 'react'
import { createUser, deleteUser, listUsers, setUserEmailApproval } from '../services/api.js'

const emptyForm = { name: '', email: '', department: '', role: 'employee' }

export default function Users({ token, onDataChange }) {
  const [users, setUsers] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [updatingApproval, setUpdatingApproval] = useState(null)

  useEffect(() => {
    let cancelled = false
    listUsers(token).then((data) => { if (!cancelled) setUsers(data.users) }).catch((requestError) => { if (!cancelled) setError(requestError.message) }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [token])

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const result = await createUser(token, form)
      setUsers((current) => [result.user, ...current])
      setForm(emptyForm)
      onDataChange()
    } catch (requestError) { setError(requestError.message) } finally { setSaving(false) }
  }

  const remove = async (user) => {
    if (!window.confirm(`Delete ${user.name}?`)) return
    setError('')
    try {
      await deleteUser(token, user.user_id)
      setUsers((current) => current.filter((item) => item.user_id !== user.user_id))
      onDataChange()
    } catch (requestError) { setError(requestError.message) }
  }

  const toggleEmailApproval = async (user) => {
    setUpdatingApproval(user.user_id)
    setError('')
    try {
      const result = await setUserEmailApproval(token, user.user_id, !user.simulation_email_approved)
      setUsers((current) => current.map((item) => item.user_id === user.user_id ? result.user : item))
    } catch (requestError) { setError(requestError.message) } finally { setUpdatingApproval(null) }
  }

  return <section className="workspace-page">
    <div className="page-heading"><div><p className="eyebrow">People directory</p><h1>Users</h1><p>Add employees who can be assigned to controlled awareness campaigns.</p></div><span className="count-pill">{users.length} users</span></div>
    {error && <div className="dashboard-error" role="alert">{error}</div>}
    <div className="workspace-grid">
      <form className="form-card" onSubmit={submit}>
        <h2>Add a user</h2>
        <label htmlFor="user-name">Full name</label><input id="user-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        <label htmlFor="user-email">Email</label><input id="user-email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
        <label htmlFor="department">Department</label><input id="department" value={form.department} onChange={(event) => setForm({ ...form, department: event.target.value })} />
        <label htmlFor="role">Role</label><select id="role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="employee">Employee</option><option value="manager">Manager</option></select>
        <button className="primary-button" disabled={saving}>{saving ? 'Adding…' : 'Add user'}</button>
      </form>
      <div className="list-card">
        <h2>Available users</h2>
        {loading ? <p className="empty-state">Loading users…</p> : users.length === 0 ? <p className="empty-state">No users yet.</p> : <div className="record-list">{users.map((user) => <article className="record" key={user.user_id}><div className="avatar">{user.name.charAt(0).toUpperCase()}</div><div><strong>{user.name}</strong><span>{user.email}</span><small>{user.department || 'No department'} · {user.role}</small><span className={`approval-status ${user.simulation_email_approved ? 'approved' : 'not-approved'}`}>{user.simulation_email_approved ? 'Approved for simulation email' : 'Email approval required'}</span></div><div className="record-actions"><button className="small-button" type="button" disabled={updatingApproval === user.user_id} onClick={() => toggleEmailApproval(user)}>{updatingApproval === user.user_id ? 'Saving…' : user.simulation_email_approved ? 'Revoke email' : 'Approve email'}</button><button className="danger-link" type="button" onClick={() => remove(user)}>Delete</button></div></article>)}</div>}
      </div>
    </div>
  </section>
}

import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plus, RefreshCw, ShieldCheck, Trash2, UserCog, Users as UsersIcon } from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  Card,
  ErrorNote,
  Field,
  Loader,
  Modal,
  PageHeader,
  Pill,
  StatCard,
} from '../components/ui'
import { formatDateTime, timeAgo } from '../lib/format'

const EMPTY = {
  user_id: '',
  name: '',
  password: '',
  role: 'officer',
  designation: '',
  phone: '',
  email: '',
  station: '',
  active: true,
}

export default function Users() {
  const { user: currentUser } = useAuth()
  const toast = useToast()

  const [users, setUsers] = useState([])
  const [summary, setSummary] = useState({})
  const [roles, setRoles] = useState([])
  const [audit, setAudit] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(null)

  const load = useCallback(async () => {
    try {
      const [{ data }, { data: auditData }] = await Promise.all([
        api.get('/api/users'),
        api.get('/api/users/audit/log', { params: { limit: 15 } }),
      ])
      setUsers(data.users)
      setSummary(data.summary)
      setRoles(data.roles)
      setAudit(auditData.entries)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const change = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setForm((current) => ({ ...current, [key]: value }))
  }

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY)
    setFormError('')
    setFormOpen(true)
  }

  const openEdit = (account) => {
    setEditing(account)
    setForm({ ...EMPTY, ...account, password: '' })
    setFormError('')
    setFormOpen(true)
  }

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      if (editing) {
        const payload = { ...form }
        delete payload.user_id
        if (!payload.password) delete payload.password
        await api.put(`/api/users/${editing.user_id}`, payload)
        toast.success(`${editing.user_id} updated`)
      } else {
        await api.post('/api/users', form)
        toast.success(`${form.user_id} created`)
      }
      setFormOpen(false)
      load()
    } catch (requestError) {
      setFormError(apiError(requestError))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    try {
      await api.delete(`/api/users/${confirmDelete.user_id}`)
      toast.success(`${confirmDelete.user_id} deleted`)
      setConfirmDelete(null)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  if (loading) return <Loader label="Loading users..." />

  return (
    <>
      <PageHeader
        title="Users"
        description="Administrator and Traffic Officer accounts for the enforcement portal."
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button type="button" className="btn-primary btn-sm" onClick={openCreate}>
              <Plus size={15} /> Add user
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total accounts" value={summary.total ?? 0} icon={UsersIcon} tone="brand" />
        <StatCard label="Administrators" value={summary.admins ?? 0} icon={ShieldCheck} tone="violet" />
        <StatCard label="Traffic officers" value={summary.officers ?? 0} icon={UserCog} tone="green" />
        <StatCard label="Active" value={summary.active ?? 0} tone="amber" />
      </div>

      <div className="mt-5">
        <Card title="Accounts" bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Name / Designation</th>
                  <th>Contact</th>
                  <th>Role</th>
                  <th>Last login</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((account) => (
                  <tr key={account.user_id}>
                    <td className="font-mono text-sm font-semibold text-slate-800">
                      {account.user_id}
                      {account.user_id === currentUser?.user_id && (
                        <span className="ml-2 text-xs font-normal text-brand-600">you</span>
                      )}
                    </td>
                    <td>
                      <p className="text-slate-800">{account.name}</p>
                      <p className="text-xs text-slate-500">
                        {account.designation || '-'}
                        {account.station ? ` · ${account.station}` : ''}
                      </p>
                    </td>
                    <td className="text-xs">
                      <p className="font-mono text-slate-700">{account.phone || '-'}</p>
                      <p className="text-slate-500">{account.email || '-'}</p>
                    </td>
                    <td>
                      <Pill
                        status={account.role === 'admin' ? 'CHALLAN_ISSUED' : 'APPROVED'}
                        label={account.role_label}
                      />
                    </td>
                    <td className="text-xs text-slate-600">
                      {account.last_login_at ? (
                        <>
                          <p>{formatDateTime(account.last_login_at)}</p>
                          <p className="text-slate-500">{timeAgo(account.last_login_at)}</p>
                        </>
                      ) : (
                        'Never'
                      )}
                    </td>
                    <td>
                      <Pill
                        status={account.active ? 'ONLINE' : 'DISABLED'}
                        label={account.active ? 'Active' : 'Inactive'}
                      />
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          onClick={() => openEdit(account)}
                        >
                          <Pencil size={13} /> Edit
                        </button>
                        {account.user_id !== currentUser?.user_id && (
                          <button
                            type="button"
                            className="btn-danger btn-sm"
                            onClick={() => setConfirmDelete(account)}
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mt-5">
        <Card title="Recent account activity" subtitle="Login and administration audit trail" bodyClass="p-0">
          {audit.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-500">No activity recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((entry) => (
                    <tr key={entry.id}>
                      <td className="whitespace-nowrap text-xs">
                        {formatDateTime(entry.created_at)}
                      </td>
                      <td className="text-xs font-semibold text-slate-700">{entry.action}</td>
                      <td className="font-mono text-xs">{entry.actor}</td>
                      <td className="text-xs text-slate-600">{entry.detail || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? `Edit ${editing.user_id}` : 'Add user'}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setFormOpen(false)}>
              Cancel
            </button>
            <button type="submit" form="user-form" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save user'}
            </button>
          </>
        }
      >
        <form id="user-form" onSubmit={save} className="space-y-4">
          {formError && <ErrorNote message={formError} />}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="User ID" required>
              <input
                className="input font-mono"
                value={form.user_id}
                onChange={change('user_id')}
                disabled={Boolean(editing)}
                placeholder="OFFICER003"
                required
              />
            </Field>
            <Field label="Full name" required>
              <input className="input" value={form.name} onChange={change('name')} required />
            </Field>
            <Field
              label="Password"
              hint={editing ? 'Leave blank to keep the current password.' : 'Minimum 6 characters.'}
              required={!editing}
            >
              <input
                className="input"
                type="password"
                value={form.password}
                onChange={change('password')}
                minLength={6}
                required={!editing}
              />
            </Field>
            <Field label="Role" required>
              <select className="input" value={form.role} onChange={change('role')}>
                {roles.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Designation">
              <input
                className="input"
                value={form.designation}
                onChange={change('designation')}
                placeholder="Traffic Sub-Inspector"
              />
            </Field>
            <Field label="Station">
              <input className="input" value={form.station} onChange={change('station')} />
            </Field>
            <Field label="Mobile number" hint="Used for OTP login and alerts.">
              <input
                className="input font-mono"
                value={form.phone}
                onChange={change('phone')}
                placeholder="9000000004"
              />
            </Field>
            <Field label="Email">
              <input className="input" type="email" value={form.email} onChange={change('email')} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={form.active} onChange={change('active')} />
            Account active
          </label>
        </form>
      </Modal>

      <Modal
        open={Boolean(confirmDelete)}
        onClose={() => setConfirmDelete(null)}
        title={`Delete ${confirmDelete?.user_id}?`}
        size="sm"
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setConfirmDelete(null)}>
              Cancel
            </button>
            <button type="button" className="btn-danger" onClick={remove}>
              <Trash2 size={15} /> Delete user
            </button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          This account will no longer be able to sign in. Records created by this user are kept.
        </p>
      </Modal>
    </>
  )
}

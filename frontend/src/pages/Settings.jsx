import { useCallback, useEffect, useState } from 'react'
import { Database, KeyRound, RefreshCw, Save, SlidersHorizontal } from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  Card,
  ErrorNote,
  Field,
  InfoNote,
  KeyValue,
  Loader,
  PageHeader,
  Pill,
} from '../components/ui'
import { formatDateTime } from '../lib/format'

export default function Settings() {
  const { isAdmin, changePassword } = useAuth()
  const toast = useToast()

  const [data, setData] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordBusy, setPasswordBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data: payload } = await api.get('/api/settings')
      setData(payload)
      setForm(payload.settings)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const change = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setForm((current) => ({ ...current, [key]: value }))
  }

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      await api.put('/api/settings', {
        rto_office_name: form.rto_office_name,
        rto_code: form.rto_code,
        state: form.state,
        contact_number: form.contact_number,
        auto_challan: form.auto_challan,
        detection_interval_seconds: Number(form.detection_interval_seconds),
        detection_cooldown_seconds: Number(form.detection_cooldown_seconds),
        detection_min_confidence: Number(form.detection_min_confidence),
        sms_on_challan: form.sms_on_challan,
        challan_due_days: Number(form.challan_due_days),
      })
      toast.success('Settings saved. Detection changes apply from the next cycle.')
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setSaving(false)
    }
  }

  const submitPassword = async (event) => {
    event.preventDefault()
    setPasswordBusy(true)
    try {
      await changePassword(currentPassword, newPassword)
      toast.success('Your password has been changed')
      setCurrentPassword('')
      setNewPassword('')
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setPasswordBusy(false)
    }
  }

  if (!data && error) return <ErrorNote message={error} />
  if (!data) return <Loader label="Loading settings..." />

  return (
    <>
      <PageHeader
        title="Settings"
        description="RTO identity, enforcement policy and detection behaviour."
        actions={
          <button type="button" className="btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Card title="Operational settings" bodyClass="p-5">
            <form onSubmit={save} className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="RTO office name">
                  <input
                    className="input"
                    value={form.rto_office_name || ''}
                    onChange={change('rto_office_name')}
                    disabled={!isAdmin}
                  />
                </Field>
                <Field label="RTO code">
                  <input
                    className="input"
                    value={form.rto_code || ''}
                    onChange={change('rto_code')}
                    disabled={!isAdmin}
                  />
                </Field>
                <Field label="State">
                  <input
                    className="input"
                    value={form.state || ''}
                    onChange={change('state')}
                    disabled={!isAdmin}
                  />
                </Field>
                <Field label="Public contact number">
                  <input
                    className="input font-mono"
                    value={form.contact_number || ''}
                    onChange={change('contact_number')}
                    disabled={!isAdmin}
                  />
                </Field>
              </div>

              <div className="border-t border-slate-200 pt-5">
                <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <SlidersHorizontal size={16} /> Detection and enforcement
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    label="Detection interval (seconds)"
                    hint="How often every camera frame is analysed."
                  >
                    <input
                      type="number"
                      min="1"
                      max="120"
                      className="input"
                      value={form.detection_interval_seconds ?? 8}
                      onChange={change('detection_interval_seconds')}
                      disabled={!isAdmin}
                    />
                  </Field>
                  <Field
                    label="Global minimum confidence"
                    hint={`${Math.round((form.detection_min_confidence ?? 0.55) * 100)}% - per-violation thresholds are set in Violation Rules.`}
                  >
                    <input
                      type="range"
                      min="0.3"
                      max="0.99"
                      step="0.01"
                      className="w-full"
                      value={form.detection_min_confidence ?? 0.55}
                      onChange={change('detection_min_confidence')}
                      disabled={!isAdmin}
                    />
                  </Field>
                  <Field
                    label="Repeat detection cooldown (seconds)"
                    hint="The same offence on the same camera is not recorded again inside this window."
                  >
                    <input
                      type="number"
                      min="5"
                      max="1800"
                      className="input"
                      value={form.detection_cooldown_seconds ?? 90}
                      onChange={change('detection_cooldown_seconds')}
                      disabled={!isAdmin}
                    />
                  </Field>
                  <Field label="Challan due period (days)">
                    <input
                      type="number"
                      min="1"
                      max="180"
                      className="input"
                      value={form.challan_due_days ?? 30}
                      onChange={change('challan_due_days')}
                      disabled={!isAdmin}
                    />
                  </Field>
                </div>

                <div className="mt-4 flex flex-wrap gap-6">
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={Boolean(form.auto_challan)}
                      onChange={change('auto_challan')}
                      disabled={!isAdmin}
                    />
                    Generate challans automatically from AI detections
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={Boolean(form.sms_on_challan)}
                      onChange={change('sms_on_challan')}
                      disabled={!isAdmin}
                    />
                    Send an SMS notice when a challan is issued
                  </label>
                </div>
              </div>

              {isAdmin ? (
                <div className="flex items-center justify-between gap-3 border-t border-slate-200 pt-4">
                  <p className="text-xs text-slate-500">
                    Last updated {formatDateTime(form.updated_at)}
                    {form.updated_by ? ` by ${form.updated_by}` : ''}
                  </p>
                  <button type="submit" className="btn-primary" disabled={saving}>
                    <Save size={15} /> {saving ? 'Saving...' : 'Save settings'}
                  </button>
                </div>
              ) : (
                <InfoNote tone="slate">
                  Only Administrator accounts can change these settings.
                </InfoNote>
              )}
            </form>
          </Card>

          <div className="mt-5">
            <Card title="Change your password" bodyClass="p-5">
              <form onSubmit={submitPassword} className="grid gap-4 sm:grid-cols-2">
                <Field label="Current password" required>
                  <input
                    className="input"
                    type="password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    required
                  />
                </Field>
                <Field label="New password" hint="Minimum 6 characters." required>
                  <input
                    className="input"
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    minLength={6}
                    required
                  />
                </Field>
                <div className="sm:col-span-2">
                  <button type="submit" className="btn-secondary" disabled={passwordBusy}>
                    <KeyRound size={15} /> {passwordBusy ? 'Updating...' : 'Update password'}
                  </button>
                </div>
              </form>
            </Card>
          </div>
        </div>

        <div className="space-y-5">
          <Card title="System" bodyClass="p-5">
            <KeyValue
              columns={1}
              items={[
                { label: 'Environment', value: data.system.environment },
                {
                  label: 'Database backend',
                  value: (
                    <span className="flex items-center gap-2">
                      {data.system.database_backend === 'mongodb'
                        ? 'MongoDB'
                        : 'Local JSON store'}
                      <Pill
                        status={data.system.database_backend === 'mongodb' ? 'CONNECTED' : 'DEMO'}
                        label={data.system.database_backend}
                      />
                    </span>
                  ),
                },
                { label: 'Database name', value: data.system.database_name },
                {
                  label: 'Detection pipeline',
                  value: `${data.system.pipeline.running ? 'Running' : 'Stopped'} · ${data.system.pipeline.cycles} cycles`,
                },
                {
                  label: 'Auto challan',
                  value: data.system.auto_challan ? 'Enabled' : 'Disabled',
                },
              ]}
            />
            {data.system.database_backend !== 'mongodb' && (
              <div className="mt-3">
                <InfoNote>
                  <span className="flex gap-2">
                    <Database size={15} className="mt-0.5 shrink-0" />
                    Running on the bundled JSON store because MONGO_URI is empty. Add a MongoDB URI
                    to backend/.env and restart to use MongoDB.
                  </span>
                </InfoNote>
              </div>
            )}
          </Card>

          <Card title="Stored records" bodyClass="p-5">
            <ul className="space-y-1.5 text-sm">
              {Object.entries(data.system.collection_counts)
                .filter(([, count]) => count >= 0)
                .map(([name, count]) => (
                  <li key={name} className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs text-slate-600">{name}</span>
                    <span className="font-semibold text-slate-800">{count}</span>
                  </li>
                ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  )
}

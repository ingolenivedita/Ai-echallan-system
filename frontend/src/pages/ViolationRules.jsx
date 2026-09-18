import { useCallback, useEffect, useState } from 'react'
import { Gavel, RefreshCw, RotateCcw, Save } from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, ErrorNote, Field, InfoNote, Loader, PageHeader, Pill } from '../components/ui'
import { currency, formatDateTime } from '../lib/format'

export default function ViolationRules() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [rules, setRules] = useState([])
  const [drafts, setDrafts] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/rules')
      setRules(data.rules)
      setDrafts(
        Object.fromEntries(
          data.rules.map((rule) => [
            rule.code,
            {
              fine_amount: rule.fine_amount,
              min_confidence: rule.min_confidence,
              enabled: rule.enabled,
              auto_challan: rule.auto_challan,
            },
          ]),
        ),
      )
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

  const update = (code, key, value) =>
    setDrafts((current) => ({ ...current, [code]: { ...current[code], [key]: value } }))

  const save = async (rule) => {
    setSaving(rule.code)
    try {
      await api.put(`/api/rules/${rule.code}`, {
        code: rule.code,
        fine_amount: Number(drafts[rule.code].fine_amount),
        min_confidence: Number(drafts[rule.code].min_confidence),
        enabled: drafts[rule.code].enabled,
        auto_challan: drafts[rule.code].auto_challan,
      })
      toast.success(`${rule.label} rule updated`)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setSaving('')
    }
  }

  const resetDefaults = async () => {
    try {
      await api.post('/api/rules/reset-defaults')
      toast.success('Rules reset to statutory defaults')
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  if (loading) return <Loader label="Loading violation rules..." />

  return (
    <>
      <PageHeader
        title="Violation Rules"
        description="Fine amounts, detection thresholds and automatic challan behaviour for each offence."
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            {isAdmin && (
              <button type="button" className="btn-secondary btn-sm" onClick={resetDefaults}>
                <RotateCcw size={14} /> Reset defaults
              </button>
            )}
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="mb-5">
        <InfoNote tone="sky">
          A violation is stored only when the detector&apos;s confidence is at or above the rule
          threshold. A challan is generated automatically when the rule allows it, auto-challan is
          enabled in Settings and a number plate was read.
        </InfoNote>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {rules.map((rule) => {
          const draft = drafts[rule.code] || {}
          return (
            <Card key={rule.code} bodyClass="p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 text-brand-700">
                      <Gavel size={17} />
                    </span>
                    <div>
                      <h3 className="font-semibold text-slate-900">{rule.label}</h3>
                      <p className="font-mono text-xs text-slate-500">{rule.code}</p>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-slate-600">{rule.description}</p>
                  <p className="mt-1 text-xs text-slate-500">{rule.section}</p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <Pill
                    status={rule.enabled ? 'APPROVED' : 'REJECTED'}
                    label={rule.enabled ? 'Enabled' : 'Disabled'}
                  />
                  <span className="text-xs capitalize text-slate-500">{rule.severity}</span>
                </div>
              </div>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="Fine amount (₹)" hint={`Statutory default ${currency(rule.default_fine)}`}>
                  <input
                    type="number"
                    min="0"
                    step="50"
                    className="input"
                    value={draft.fine_amount ?? ''}
                    onChange={(event) => update(rule.code, 'fine_amount', event.target.value)}
                    disabled={!isAdmin}
                  />
                </Field>
                <Field
                  label="Minimum confidence"
                  hint={`Currently ${Math.round((draft.min_confidence ?? 0) * 100)}%`}
                >
                  <input
                    type="range"
                    min="0.3"
                    max="0.99"
                    step="0.01"
                    className="w-full"
                    value={draft.min_confidence ?? 0.6}
                    onChange={(event) =>
                      update(rule.code, 'min_confidence', Number(event.target.value))
                    }
                    disabled={!isAdmin}
                  />
                </Field>
              </div>

              <div className="mt-3 flex flex-wrap gap-5">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.enabled)}
                    onChange={(event) => update(rule.code, 'enabled', event.target.checked)}
                    disabled={!isAdmin}
                  />
                  Detect this violation
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.auto_challan)}
                    onChange={(event) => update(rule.code, 'auto_challan', event.target.checked)}
                    disabled={!isAdmin}
                  />
                  Issue challan automatically
                </label>
              </div>

              <div className="mt-4 flex items-center justify-between gap-3">
                <p className="text-xs text-slate-500">
                  Updated {rule.updated_at ? formatDateTime(rule.updated_at) : 'never'}
                </p>
                {isAdmin && (
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    onClick={() => save(rule)}
                    disabled={saving === rule.code}
                  >
                    <Save size={14} /> {saving === rule.code ? 'Saving...' : 'Save rule'}
                  </button>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {!isAdmin && (
        <div className="mt-4">
          <InfoNote tone="slate">
            Rule changes require an Administrator account.
          </InfoNote>
        </div>
      )}
    </>
  )
}

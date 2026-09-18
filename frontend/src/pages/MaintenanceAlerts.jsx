import { useCallback, useEffect, useState } from 'react'
import { BellRing, CheckCircle2, Eye, RefreshCw, Trash2, Wrench } from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  Card,
  EmptyState,
  ErrorNote,
  Loader,
  PageHeader,
  Pill,
  StatCard,
} from '../components/ui'
import { formatDateTime, timeAgo } from '../lib/format'

const FILTERS = [
  { value: '', label: 'All alerts' },
  { value: 'OPEN', label: 'Open' },
  { value: 'ACKNOWLEDGED', label: 'Acknowledged' },
  { value: 'RESOLVED', label: 'Resolved' },
]

export default function MaintenanceAlerts() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [alerts, setAlerts] = useState([])
  const [summary, setSummary] = useState({})
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/alerts', {
        params: { status: filter || undefined, limit: 100 },
      })
      setAlerts(data.alerts)
      setSummary(data.summary)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    load()
    const timer = setInterval(load, 20000)
    return () => clearInterval(timer)
  }, [load])

  const act = async (alert, action) => {
    try {
      await api.post(`/api/alerts/${alert.id}/${action}`)
      toast.success(`Alert ${action === 'resolve' ? 'resolved' : 'acknowledged'}`)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  const clearResolved = async () => {
    try {
      const { data } = await api.delete('/api/alerts/clear-resolved')
      toast.success(`${data.deleted} resolved alert(s) cleared`)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  if (loading && !alerts.length) return <Loader label="Loading alerts..." />

  return (
    <>
      <PageHeader
        title="Maintenance Alerts"
        description="Raised automatically when a camera stops streaming, and resolved when it returns."
        actions={
          <>
            <select
              className="input w-auto py-1.5 text-xs"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              {FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            {isAdmin && summary.resolved > 0 && (
              <button type="button" className="btn-secondary btn-sm" onClick={clearResolved}>
                <Trash2 size={14} /> Clear resolved
              </button>
            )}
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Open"
          value={summary.open ?? 0}
          icon={BellRing}
          tone={summary.open ? 'red' : 'green'}
        />
        <StatCard label="Acknowledged" value={summary.acknowledged ?? 0} icon={Eye} tone="amber" />
        <StatCard
          label="Resolved"
          value={summary.resolved ?? 0}
          icon={CheckCircle2}
          tone="green"
        />
        <StatCard label="Total raised" value={summary.total ?? 0} icon={Wrench} tone="slate" />
      </div>

      <div className="mt-5">
        <Card title="Alert log" bodyClass="p-0">
          {alerts.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="No alerts"
              description="All cameras are healthy. An alert appears here as soon as a stream drops."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Raised</th>
                    <th>Camera</th>
                    <th>Message</th>
                    <th>Detail</th>
                    <th>Status</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td className="whitespace-nowrap text-xs">
                        <p className="text-slate-800">{formatDateTime(alert.created_at)}</p>
                        <p className="text-slate-500">{timeAgo(alert.created_at)}</p>
                      </td>
                      <td>
                        <p className="font-semibold text-slate-800">{alert.camera_id}</p>
                        <p className="max-w-[12rem] truncate text-xs text-slate-500">
                          {alert.location || alert.camera_name}
                        </p>
                      </td>
                      <td className="max-w-[20rem] text-slate-700">{alert.message}</td>
                      <td className="max-w-[18rem] text-xs text-slate-500">
                        <p className="truncate">{alert.detail || '-'}</p>
                        {alert.reconnect_attempts != null && (
                          <p>{alert.reconnect_attempts} reconnect attempt(s)</p>
                        )}
                        {alert.resolved_at && (
                          <p className="text-emerald-700">
                            Resolved {formatDateTime(alert.resolved_at)}
                          </p>
                        )}
                      </td>
                      <td>
                        <Pill status={alert.status} />
                        <span className="mt-1 block text-xs capitalize text-slate-500">
                          {alert.severity}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-1.5">
                          {alert.status === 'OPEN' && (
                            <button
                              type="button"
                              className="btn-secondary btn-sm"
                              onClick={() => act(alert, 'acknowledge')}
                            >
                              <Eye size={13} /> Acknowledge
                            </button>
                          )}
                          {alert.status !== 'RESOLVED' && (
                            <button
                              type="button"
                              className="btn-secondary btn-sm"
                              onClick={() => act(alert, 'resolve')}
                            >
                              <CheckCircle2 size={13} /> Resolve
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

import { useCallback, useEffect, useState } from 'react'
import {
  Cctv,
  Database,
  Globe,
  Info,
  RefreshCw,
  Server,
  Wifi,
  WifiOff,
} from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useToast } from '../context/ToastContext'
import {
  Card,
  ErrorNote,
  InfoNote,
  KeyValue,
  Loader,
  PageHeader,
  Pill,
  StatCard,
} from '../components/ui'
import { formatDateTime, timeAgo } from '../lib/format'

export default function NetworkStatus() {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/network/status')
      setStatus(data)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 20000)
    return () => clearInterval(timer)
  }, [load])

  const resync = async () => {
    setBusy(true)
    try {
      const { data } = await api.post('/api/network/refresh-cameras')
      const report = data.report
      toast.success(
        `Cameras re-synced · started ${report.started.length}, restarted ${report.restarted.length}, running ${report.running.length}`,
      )
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setBusy(false)
    }
  }

  if (!status && error) return <ErrorNote message={error} />
  if (!status) return <Loader label="Checking network..." />

  return (
    <>
      <PageHeader
        title="Network Status"
        description="Measured connectivity for the backend, database, cameras and outbound internet."
        actions={
          <>
            <span className="text-xs text-slate-500">
              Checked {timeAgo(status.last_checked)}
            </span>
            <button type="button" className="btn-secondary btn-sm" onClick={resync} disabled={busy}>
              <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> Re-sync cameras
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Backend"
          value={status.backend.status}
          hint={`Up ${status.backend.uptime_human}`}
          icon={Server}
          tone="green"
        />
        <StatCard
          label="Database"
          value={status.database.healthy ? 'Healthy' : 'Unavailable'}
          hint={status.database.backend}
          icon={Database}
          tone={status.database.healthy ? 'green' : 'red'}
        />
        <StatCard
          label="Cameras streaming"
          value={`${status.camera_summary.streaming}/${status.camera_summary.total}`}
          hint={`${status.camera_summary.live_reachable}/${status.camera_summary.live_mode} live cameras reachable`}
          icon={Cctv}
          tone={status.camera_summary.streaming === status.camera_summary.total ? 'green' : 'amber'}
        />
        <StatCard
          label="Internet"
          value={status.internet.reachable ? 'Reachable' : 'Unreachable'}
          hint={`${status.internet.probes.filter((probe) => probe.reachable).length}/${status.internet.probes.length} probes ok`}
          icon={status.internet.reachable ? Wifi : WifiOff}
          tone={status.internet.reachable ? 'green' : 'red'}
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Backend process">
          <KeyValue
            items={[
              { label: 'Environment', value: status.backend.environment },
              { label: 'Hostname', value: status.backend.hostname },
              { label: 'Platform', value: status.backend.platform },
              { label: 'Python', value: status.backend.python },
              { label: 'Uptime', value: status.backend.uptime_human },
              { label: 'Server time', value: status.server_time },
              {
                label: 'Detection pipeline',
                value: status.backend.pipeline.running ? 'Running' : 'Stopped',
              },
              {
                label: 'Last detection cycle',
                value: timeAgo(status.backend.pipeline.last_detection_cycle),
              },
            ]}
          />
        </Card>

        <Card title="Database connection">
          <KeyValue
            items={[
              { label: 'Backend', value: status.database.backend },
              { label: 'Database name', value: status.database.database_name },
              { label: 'Connected at', value: formatDateTime(status.database.connected_at) },
              { label: 'Healthy', value: status.database.healthy ? 'Yes' : 'No' },
              status.database.error && { label: 'Note', value: status.database.error },
            ]}
          />
        </Card>
      </div>

      <div className="mt-5">
        <Card title="Camera connectivity" bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Camera</th>
                  <th>Mode</th>
                  <th>Endpoint</th>
                  <th>Network reachability</th>
                  <th>Stream</th>
                  <th>Last frame</th>
                </tr>
              </thead>
              <tbody>
                {status.cameras.map((camera) => (
                  <tr key={camera.camera_id}>
                    <td>
                      <p className="font-semibold text-slate-800">{camera.camera_id}</p>
                      <p className="max-w-[14rem] truncate text-xs text-slate-500">
                        {camera.name} · {camera.location || 'Location not set'}
                      </p>
                    </td>
                    <td>
                      <Pill status={camera.mode} label={camera.mode === 'DEMO' ? 'DEMO' : 'LIVE'} />
                    </td>
                    <td className="font-mono text-xs text-slate-600">
                      {camera.checked_endpoint || camera.ip_address || '-'}
                    </td>
                    <td className="text-xs">
                      {camera.network_check.reachable === null ? (
                        <span className="text-slate-500">{camera.network_check.detail}</span>
                      ) : (
                        <span
                          className={
                            camera.network_check.reachable ? 'text-emerald-700' : 'text-rose-700'
                          }
                        >
                          {camera.network_check.reachable ? 'Reachable' : 'Not reachable'}
                          {camera.network_check.latency_ms != null &&
                            ` · ${camera.network_check.latency_ms} ms`}
                          <span className="block max-w-[18rem] truncate text-slate-500">
                            {camera.network_check.detail}
                          </span>
                        </span>
                      )}
                    </td>
                    <td>
                      <Pill status={camera.stream_status} />
                      <span className="mt-1 block text-xs text-slate-500">
                        {(camera.fps ?? 0).toFixed(1)} FPS
                      </span>
                    </td>
                    <td className="text-xs text-slate-600">
                      {timeAgo(camera.last_frame_at)}
                      {camera.connection_error && (
                        <span className="mt-0.5 block max-w-[16rem] truncate text-rose-600">
                          {camera.connection_error}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Internet probes" bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Result</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {status.internet.probes.map((probe) => (
                  <tr key={probe.url}>
                    <td>
                      <p className="text-slate-800">{probe.name}</p>
                      <p className="max-w-[18rem] truncate font-mono text-xs text-slate-500">
                        {probe.url}
                      </p>
                    </td>
                    <td>
                      <Pill
                        status={probe.reachable ? 'ONLINE' : 'OFFLINE'}
                        label={
                          probe.reachable ? `HTTP ${probe.status_code}` : 'Unreachable'
                        }
                      />
                      {probe.detail && (
                        <p className="mt-1 max-w-[16rem] truncate text-xs text-rose-600">
                          {probe.detail}
                        </p>
                      )}
                    </td>
                    <td className="font-mono text-xs">{probe.latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="What cannot be measured" bodyClass="p-5">
          <div className="space-y-2">
            {status.not_measurable.map((note) => (
              <InfoNote key={note} tone="slate">
                <span className="flex gap-2">
                  <Info size={15} className="mt-0.5 shrink-0" />
                  {note}
                </span>
              </InfoNote>
            ))}
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
            <Globe size={13} /> Values on this page come from real TCP connects, HTTP probes and
            capture-thread counters - nothing is estimated.
          </p>
        </Card>
      </div>
    </>
  )
}

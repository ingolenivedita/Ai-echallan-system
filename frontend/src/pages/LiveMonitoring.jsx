import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Cctv, Gauge, MonitorPlay, RefreshCw, ShieldAlert } from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useToast } from '../context/ToastContext'
import CameraTile from '../components/CameraTile'
import { Card, EmptyState, ErrorNote, InfoNote, Loader, PageHeader, Pill } from '../components/ui'
import { confidencePercent, formatDateTime, timeAgo } from '../lib/format'

const HEALTH_REFRESH_MS = 4000
const FEED_REFRESH_MS = 10000

const LAYOUTS = [
  { value: 2, label: '2 per row' },
  { value: 3, label: '3 per row' },
  { value: 1, label: 'Single' },
]

export default function LiveMonitoring() {
  const toast = useToast()
  const [cameras, setCameras] = useState([])
  const [health, setHealth] = useState({})
  const [pipeline, setPipeline] = useState(null)
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [columns, setColumns] = useState(2)
  const [streamFps, setStreamFps] = useState(8)
  const [detectingId, setDetectingId] = useState('')

  const loadCameras = useCallback(async () => {
    try {
      const { data } = await api.get('/api/cameras')
      setCameras(data.cameras)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/api/cameras/health/all')
      setHealth(Object.fromEntries(data.cameras.map((item) => [item.camera_id, item])))
      setPipeline(data.pipeline)
    } catch {
      /* transient - the tiles keep their own state */
    }
  }, [])

  const loadFeed = useCallback(async () => {
    try {
      const { data } = await api.get('/api/violations', { params: { limit: 8, page: 1 } })
      setRecent(data.violations)
    } catch {
      /* non critical */
    }
  }, [])

  useEffect(() => {
    loadCameras()
    loadHealth()
    loadFeed()
    const healthTimer = setInterval(loadHealth, HEALTH_REFRESH_MS)
    const feedTimer = setInterval(loadFeed, FEED_REFRESH_MS)
    const cameraTimer = setInterval(loadCameras, 30000)
    return () => {
      clearInterval(healthTimer)
      clearInterval(feedTimer)
      clearInterval(cameraTimer)
    }
  }, [loadCameras, loadHealth, loadFeed])

  const detectNow = async (camera) => {
    setDetectingId(camera.camera_id)
    try {
      const { data } = await api.post(`/api/cameras/${camera.camera_id}/detect-now`)
      if (data.violations_recorded > 0) {
        toast.success(`${camera.camera_id}: ${data.message}`)
      } else {
        toast.info(`${camera.camera_id}: ${data.message}`)
      }
      loadFeed()
      loadHealth()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setDetectingId('')
    }
  }

  const enabled = useMemo(() => cameras.filter((camera) => camera.enabled), [cameras])
  const onlineCount = enabled.filter(
    (camera) => (health[camera.camera_id]?.status || camera.health?.status) === 'ONLINE',
  ).length
  const demoCount = cameras.filter((camera) => camera.mode === 'DEMO').length

  const gridClass =
    columns === 1
      ? 'grid-cols-1'
      : columns === 3
        ? 'grid-cols-1 md:grid-cols-2 2xl:grid-cols-3'
        : 'grid-cols-1 xl:grid-cols-2'

  if (loading) return <Loader label="Connecting to cameras..." />

  return (
    <>
      <PageHeader
        title="Live Monitoring"
        description="All enabled cameras stream simultaneously. Each feed runs in its own backend thread."
        actions={
          <>
            <select
              className="input w-auto py-1.5 text-xs"
              value={columns}
              onChange={(event) => setColumns(Number(event.target.value))}
            >
              {LAYOUTS.map((layout) => (
                <option key={layout.value} value={layout.value}>
                  {layout.label}
                </option>
              ))}
            </select>
            <select
              className="input w-auto py-1.5 text-xs"
              value={streamFps}
              onChange={(event) => setStreamFps(Number(event.target.value))}
              title="Stream frame rate"
            >
              {[4, 6, 8, 12, 15].map((value) => (
                <option key={value} value={value}>
                  {value} FPS
                </option>
              ))}
            </select>
            <button type="button" className="btn-secondary btn-sm" onClick={loadCameras}>
              <RefreshCw size={14} /> Refresh
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {demoCount > 0 && (
        <div className="mb-4">
          <InfoNote>
            <strong>{demoCount} camera(s) are in DEMO MODE.</strong> Frames come from the built-in
            synthetic traffic generator or an uploaded video/image, not from a real IP camera. Switch
            a camera to LIVE CAMERA MODE from{' '}
            <Link to="/cameras" className="font-semibold underline">
              Cameras
            </Link>{' '}
            once its RTSP stream is reachable.
          </InfoNote>
        </div>
      )}

      {enabled.length === 0 ? (
        <Card>
          <EmptyState
            icon={Cctv}
            title="No enabled cameras"
            description="Add a camera and enable it to start monitoring."
            action={
              <Link to="/cameras" className="btn-primary btn-sm">
                Go to Cameras
              </Link>
            }
          />
        </Card>
      ) : (
        <div className={`grid gap-5 ${gridClass}`}>
          {enabled.map((camera) => (
            <CameraTile
              key={camera.camera_id}
              camera={camera}
              health={health[camera.camera_id] || camera.health}
              fps={streamFps}
              onDetect={detectNow}
              detecting={detectingId === camera.camera_id}
            />
          ))}

          {/* system status tile completes the monitoring wall */}
          <div className="card flex flex-col">
            <div className="border-b border-slate-200 px-3.5 py-2.5">
              <p className="text-sm font-semibold text-slate-900">System Status</p>
              <p className="text-xs text-slate-500">Capture and detection engine</p>
            </div>

            <div className="grid grid-cols-2 gap-3 p-4">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <MonitorPlay size={13} /> Cameras online
                </p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">
                  {onlineCount}/{enabled.length}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <Gauge size={13} /> Detection cycles
                </p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">
                  {pipeline?.cycles ?? 0}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <ShieldAlert size={13} /> Violations
                </p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">
                  {pipeline?.violations_recorded ?? 0}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <Activity size={13} /> Pipeline
                </p>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {pipeline?.running ? 'Running' : 'Stopped'}
                </p>
                <p className="text-xs text-slate-500">
                  Last cycle {timeAgo(pipeline?.last_detection_cycle)}
                </p>
              </div>
            </div>

            <div className="flex-1 border-t border-slate-200 px-4 py-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Latest detections
              </p>
              {recent.length === 0 ? (
                <p className="text-sm text-slate-500">Nothing detected yet.</p>
              ) : (
                <ul className="space-y-2">
                  {recent.slice(0, 6).map((violation) => (
                    <li
                      key={violation.id}
                      className="flex items-center justify-between gap-2 text-xs"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-slate-800">
                          {violation.violation_label}
                        </span>
                        <span className="block truncate text-slate-500">
                          {violation.camera_id} · {formatDateTime(violation.detected_at)}
                        </span>
                      </span>
                      <span className="shrink-0 font-mono text-slate-600">
                        {confidencePercent(violation.confidence)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {pipeline?.last_error && (
              <p className="border-t border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-800">
                Last pipeline error: {pipeline.last_error}
              </p>
            )}

            <div className="border-t border-slate-200 px-4 py-2.5">
              <Link to="/violations" className="btn-secondary btn-sm w-full">
                Review all violations
              </Link>
            </div>
          </div>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {enabled.map((camera) => {
          const state = health[camera.camera_id] || camera.health || {}
          return (
            <span
              key={camera.camera_id}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1"
            >
              <Pill status={state.status || 'CONNECTING'} />
              {camera.camera_id}
              <span className="text-slate-400">·</span>
              {(state.fps ?? 0).toFixed(1)} FPS
              <span className="text-slate-400">·</span>
              seen {timeAgo(state.last_seen)}
            </span>
          )
        })}
      </div>
    </>
  )
}

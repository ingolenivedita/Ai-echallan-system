import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Camera, RefreshCw, ScanSearch, WifiOff } from 'lucide-react'
import { cameraStreamUrl } from '../lib/api'
import { LiveDot, Pill } from './ui'
import { timeAgo } from '../lib/format'

/**
 * One independent camera feed. The MJPEG <img> reconnects on its own, so a
 * camera going offline never affects the other tiles on the page.
 */
export default function CameraTile({ camera, health, fps = 8, onDetect, detecting }) {
  const [streamKey, setStreamKey] = useState(() => Date.now())
  const [imageFailed, setImageFailed] = useState(false)
  const retryTimer = useRef(null)

  const status = health?.status || camera.status || 'CONNECTING'
  const online = status === 'ONLINE'
  const isDemo = (camera.mode || 'DEMO').toUpperCase() === 'DEMO'

  useEffect(() => {
    if (!imageFailed) return undefined
    retryTimer.current = setTimeout(() => {
      setImageFailed(false)
      setStreamKey(Date.now())
    }, 6000)
    return () => clearTimeout(retryTimer.current)
  }, [imageFailed])

  const reconnect = () => {
    setImageFailed(false)
    setStreamKey(Date.now())
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <LiveDot online={online} />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">
              {camera.camera_id} · {camera.name}
            </p>
            <p className="truncate text-xs text-slate-500">
              {camera.location || 'Location not set'}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Pill status={isDemo ? 'DEMO' : 'LIVE'} label={isDemo ? 'DEMO MODE' : 'LIVE'} />
          <Pill status={status} />
        </div>
      </div>

      <div className="relative aspect-video bg-slate-900">
        {camera.enabled === false ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-slate-400">
            <Camera size={26} />
            <p className="text-sm">Camera disabled</p>
          </div>
        ) : imageFailed ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-slate-300">
            <WifiOff size={26} className="text-rose-400" />
            <p className="text-sm font-medium">Stream unavailable</p>
            <p className="max-w-xs text-xs text-slate-400">
              {health?.connection_error || 'Reconnecting automatically...'}
            </p>
            <button type="button" className="btn-secondary btn-sm mt-1" onClick={reconnect}>
              <RefreshCw size={13} /> Retry now
            </button>
          </div>
        ) : (
          <img
            key={streamKey}
            src={cameraStreamUrl(camera.camera_id, fps)}
            alt={`${camera.camera_id} live stream`}
            className="h-full w-full object-contain"
            onError={() => setImageFailed(true)}
          />
        )}

        {!online && !imageFailed && camera.enabled !== false && (
          <span className="absolute left-2 top-2 flex items-center gap-1 rounded bg-rose-600/90 px-2 py-0.5 text-[11px] font-semibold text-white">
            <AlertTriangle size={12} /> {status}
          </span>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 px-3.5 py-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-slate-500">IP address</dt>
          <dd className="truncate font-mono text-slate-800">{camera.ip_address || '-'}</dd>
        </div>
        <div>
          <dt className="text-slate-500">FPS</dt>
          <dd className="font-medium text-slate-800">{(health?.fps ?? 0).toFixed(1)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Last frame</dt>
          <dd className="text-slate-800">{timeAgo(health?.last_frame_at)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Violations</dt>
          <dd className="font-medium text-slate-800">{health?.violation_count ?? 0}</dd>
        </div>
      </dl>

      {health?.connection_error && (
        <p className="border-t border-rose-100 bg-rose-50 px-3.5 py-2 text-xs text-rose-700">
          {health.connection_error}
        </p>
      )}

      {onDetect && (
        <div className="flex items-center justify-between gap-2 border-t border-slate-200 px-3.5 py-2.5">
          <span className="text-xs text-slate-500">
            {health?.detection_enabled === false
              ? 'Detection disabled for this camera'
              : `Detector: ${health?.source_kind === 'live' ? 'live frames' : 'demo frames'}`}
          </span>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => onDetect(camera)}
            disabled={detecting || !online}
          >
            <ScanSearch size={13} className={detecting ? 'animate-pulse' : ''} /> Detect now
          </button>
        </div>
      )}
    </div>
  )
}

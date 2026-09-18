import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircle2,
  FileImage,
  Filter,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react'
import api, { apiError, evidenceUrl } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import {
  Card,
  EmptyState,
  ErrorNote,
  Field,
  InfoNote,
  KeyValue,
  Loader,
  Modal,
  PageHeader,
  Pagination,
  Pill,
  StatCard,
} from '../components/ui'
import {
  DETECTOR_LABELS,
  confidencePercent,
  formatDateTime,
  humanStatus,
  timeAgo,
} from '../lib/format'

const EMPTY_FILTERS = {
  camera_id: '',
  violation_type: '',
  status: '',
  plate: '',
  date_from: '',
  date_to: '',
}

export default function Violations() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [violations, setViolations] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [stats, setStats] = useState(null)
  const [cameras, setCameras] = useState([])
  const [rules, setRules] = useState([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [selected, setSelected] = useState(null)
  const [reviewing, setReviewing] = useState(false)
  const [remarks, setRemarks] = useState('')
  const [plateOverride, setPlateOverride] = useState('')

  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const [analyzeFile, setAnalyzeFile] = useState(null)
  const [analyzeCamera, setAnalyzeCamera] = useState('')
  const [analyzeRecord, setAnalyzeRecord] = useState(true)
  const [analyzeBusy, setAnalyzeBusy] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState(null)

  const load = useCallback(async () => {
    try {
      const params = { page, limit: 15 }
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value
      })
      const [{ data }, { data: statsData }] = await Promise.all([
        api.get('/api/violations', { params }),
        api.get('/api/violations/stats'),
      ])
      setViolations(data.violations)
      setMeta({ page: data.page, pages: data.pages, total: data.total })
      setStats(statsData)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    } finally {
      setLoading(false)
    }
  }, [filters, page])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.get('/api/cameras').then(({ data }) => setCameras(data.cameras)).catch(() => {})
    api.get('/api/rules').then(({ data }) => setRules(data.rules)).catch(() => {})
  }, [])

  const openDetail = (violation) => {
    setSelected(violation)
    setRemarks(violation.remarks || '')
    setPlateOverride(violation.plate_number || '')
  }

  const review = async (status, issueChallan = false) => {
    setReviewing(true)
    try {
      const { data } = await api.post(
        `/api/violations/${selected.id}/review`,
        { status, remarks, plate_number: plateOverride || null },
        { params: { issue: issueChallan } },
      )
      if (data.challan?.created) {
        toast.success(
          `Challan ${data.challan.challan.challan_number} issued · ${
            data.challan.sms
              ? data.challan.sms.ok
                ? 'SMS sent'
                : data.challan.sms.configured
                  ? 'SMS failed'
                  : 'SMS in demo mode (not sent)'
              : 'no SMS sent'
          }`,
          9000,
        )
      } else {
        toast.success(`Violation marked ${humanStatus(status)}`)
      }
      setSelected(null)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setReviewing(false)
    }
  }

  const remove = async (violation) => {
    try {
      await api.delete(`/api/violations/${violation.id}`)
      toast.success('Violation deleted')
      setSelected(null)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  const runAnalysis = async (event) => {
    event.preventDefault()
    if (!analyzeFile) return
    setAnalyzeBusy(true)
    setAnalyzeResult(null)
    const payload = new FormData()
    payload.append('file', analyzeFile)
    payload.append('camera_id', analyzeCamera)
    payload.append('record', String(analyzeRecord))
    try {
      const { data } = await api.post('/api/violations/analyze-upload', payload, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setAnalyzeResult(data)
      if (data.detections.length) {
        toast.success(`${data.detections.length} violation(s) detected`)
      } else {
        toast.info('No violation detected in this image')
      }
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setAnalyzeBusy(false)
    }
  }

  if (loading && !violations.length) return <Loader label="Loading violations..." />

  return (
    <>
      <PageHeader
        title="Violations"
        description="Every AI detection with its evidence image, ready for officer review."
        actions={
          <>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => setAnalyzeOpen(true)}
            >
              <Upload size={14} /> Analyse an image
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {stats && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Total violations" value={stats.total} icon={ShieldAlert} tone="brand" />
          <StatCard label="Detected today" value={stats.today} tone="amber" icon={ScanSearch} />
          <StatCard
            label="Pending review"
            value={stats.pending_review}
            tone={stats.pending_review ? 'red' : 'green'}
            icon={CheckCircle2}
          />
          <StatCard
            label="Challans issued"
            value={stats.by_status?.CHALLAN_ISSUED ?? 0}
            tone="green"
            icon={FileImage}
          />
        </div>
      )}

      <div className="mt-5">
        <Card title="Filters" bodyClass="p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            <Field label="Camera">
              <select
                className="input"
                value={filters.camera_id}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, camera_id: event.target.value }))
                }}
              >
                <option value="">All cameras</option>
                {cameras.map((camera) => (
                  <option key={camera.camera_id} value={camera.camera_id}>
                    {camera.camera_id} · {camera.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Violation type">
              <select
                className="input"
                value={filters.violation_type}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, violation_type: event.target.value }))
                }}
              >
                <option value="">All types</option>
                {rules.map((rule) => (
                  <option key={rule.code} value={rule.code}>
                    {rule.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select
                className="input"
                value={filters.status}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, status: event.target.value }))
                }}
              >
                <option value="">All statuses</option>
                {['PENDING_REVIEW', 'APPROVED', 'REJECTED', 'CHALLAN_ISSUED'].map((status) => (
                  <option key={status} value={status}>
                    {humanStatus(status)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Number plate">
              <input
                className="input font-mono"
                value={filters.plate}
                placeholder="KA05..."
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, plate: event.target.value }))
                }}
              />
            </Field>
            <Field label="From date">
              <input
                type="date"
                className="input"
                value={filters.date_from}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, date_from: event.target.value }))
                }}
              />
            </Field>
            <Field label="To date">
              <input
                type="date"
                className="input"
                value={filters.date_to}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, date_to: event.target.value }))
                }}
              />
            </Field>
          </div>
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={() => {
                setFilters(EMPTY_FILTERS)
                setPage(1)
              }}
            >
              <Filter size={14} /> Clear filters
            </button>
          </div>
        </Card>
      </div>

      <div className="mt-5">
        <Card title={`Violation records (${meta.total})`} bodyClass="p-0">
          {violations.length === 0 ? (
            <EmptyState
              title="No violations match these filters"
              description="Try widening the date range or clearing the filters."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Evidence</th>
                      <th>Detected</th>
                      <th>Camera</th>
                      <th>Violation</th>
                      <th>Vehicle</th>
                      <th>Detector</th>
                      <th>Status</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {violations.map((violation) => (
                      <tr key={violation.id}>
                        <td>
                          {violation.evidence_image ? (
                            <img
                              src={evidenceUrl(violation.evidence_image)}
                              alt="Evidence"
                              className="h-12 w-20 cursor-pointer rounded border border-slate-200 object-cover"
                              onClick={() => openDetail(violation)}
                              loading="lazy"
                            />
                          ) : (
                            <span className="text-xs text-slate-400">No image</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap">
                          <p className="text-slate-800">{formatDateTime(violation.detected_at)}</p>
                          <p className="text-xs text-slate-500">{timeAgo(violation.detected_at)}</p>
                        </td>
                        <td className="whitespace-nowrap">
                          <p className="font-medium text-slate-800">{violation.camera_id}</p>
                          <p className="max-w-[12rem] truncate text-xs text-slate-500">
                            {violation.location}
                          </p>
                        </td>
                        <td>
                          <p className="font-medium text-slate-800">{violation.violation_label}</p>
                          <p className="text-xs text-slate-500">
                            {confidencePercent(violation.confidence)} confidence
                          </p>
                        </td>
                        <td className="whitespace-nowrap font-mono text-xs">
                          {violation.plate_number || '-'}
                          {violation.plate_source && (
                            <span className="ml-1 text-[10px] uppercase text-slate-400">
                              {violation.plate_source}
                            </span>
                          )}
                        </td>
                        <td className="text-xs">
                          {DETECTOR_LABELS[violation.detector] || violation.detector || '-'}
                          {violation.simulated && (
                            <span className="mt-0.5 block text-[10px] font-semibold uppercase text-amber-600">
                              simulated
                            </span>
                          )}
                        </td>
                        <td>
                          <Pill status={violation.status} />
                          {violation.challan_number && (
                            <p className="mt-1 font-mono text-[10px] text-slate-500">
                              {violation.challan_number}
                            </p>
                          )}
                        </td>
                        <td className="text-right">
                          <button
                            type="button"
                            className="btn-secondary btn-sm"
                            onClick={() => openDetail(violation)}
                          >
                            Review
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={meta.page}
                pages={meta.pages}
                total={meta.total}
                onChange={setPage}
              />
            </>
          )}
        </Card>
      </div>

      {/* ---------------- review modal ---------------- */}
      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `${selected.violation_label} · ${selected.camera_id}` : ''}
        subtitle={selected ? formatDateTime(selected.detected_at) : ''}
        size="lg"
        footer={
          selected && (
            <>
              {isAdmin && (
                <button
                  type="button"
                  className="btn-danger btn-sm mr-auto"
                  onClick={() => remove(selected)}
                >
                  <Trash2 size={14} /> Delete
                </button>
              )}
              <button type="button" className="btn-ghost" onClick={() => setSelected(null)}>
                Close
              </button>
              {selected.status !== 'CHALLAN_ISSUED' && (
                <>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => review('REJECTED')}
                    disabled={reviewing}
                  >
                    <XCircle size={15} /> Reject
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => review('APPROVED')}
                    disabled={reviewing}
                  >
                    <CheckCircle2 size={15} /> Approve only
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => review('APPROVED', true)}
                    disabled={reviewing || !plateOverride}
                    title={!plateOverride ? 'A number plate is required to issue a challan' : ''}
                  >
                    Approve &amp; issue challan
                  </button>
                </>
              )}
            </>
          )
        }
      >
        {selected && (
          <div className="space-y-4">
            {selected.evidence_image ? (
              <a href={evidenceUrl(selected.evidence_image)} target="_blank" rel="noreferrer">
                <img
                  src={evidenceUrl(selected.evidence_image)}
                  alt="Violation evidence"
                  className="w-full rounded-lg border border-slate-200"
                />
              </a>
            ) : (
              <InfoNote tone="slate">No evidence image stored for this record.</InfoNote>
            )}

            {selected.simulated && (
              <InfoNote>
                This detection came from the <strong>demo simulator</strong> on a synthetic camera.
                It demonstrates the workflow but is not a real AI inference. Configure
                GROQ_API_KEY for real AI detection.
              </InfoNote>
            )}

            <KeyValue
              items={[
                { label: 'Violation', value: selected.violation_label },
                { label: 'Confidence', value: confidencePercent(selected.confidence) },
                { label: 'Camera', value: `${selected.camera_id} · ${selected.camera_name || ''}` },
                { label: 'Location', value: selected.location },
                { label: 'Detected at', value: formatDateTime(selected.detected_at) },
                {
                  label: 'Detector',
                  value: DETECTOR_LABELS[selected.detector] || selected.detector,
                },
                { label: 'Plate source', value: selected.plate_source || '-' },
                { label: 'Status', value: humanStatus(selected.status) },
                { label: 'Reason', value: selected.reason || '-' },
                { label: 'Scene', value: selected.scene || '-' },
                selected.challan_number && {
                  label: 'Challan number',
                  value: selected.challan_number,
                },
                selected.reviewed_by && { label: 'Reviewed by', value: selected.reviewed_by },
              ]}
            />

            {selected.status !== 'CHALLAN_ISSUED' && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Number plate"
                  hint="Correct the ANPR reading before issuing the challan."
                >
                  <input
                    className="input font-mono uppercase"
                    value={plateOverride}
                    onChange={(event) => setPlateOverride(event.target.value.toUpperCase())}
                    placeholder="KA05MJ2020"
                  />
                </Field>
                <Field label="Officer remarks">
                  <input
                    className="input"
                    value={remarks}
                    onChange={(event) => setRemarks(event.target.value)}
                    placeholder="Verified on evidence image"
                  />
                </Field>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ---------------- analyse image modal ---------------- */}
      <Modal
        open={analyzeOpen}
        onClose={() => {
          setAnalyzeOpen(false)
          setAnalyzeResult(null)
          setAnalyzeFile(null)
        }}
        title="Analyse an image"
        subtitle="Runs the same detection service used by the live cameras."
        footer={
          <>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                setAnalyzeOpen(false)
                setAnalyzeResult(null)
              }}
            >
              Close
            </button>
            <button
              type="submit"
              form="analyze-form"
              className="btn-primary"
              disabled={analyzeBusy || !analyzeFile}
            >
              <ScanSearch size={15} /> {analyzeBusy ? 'Analysing...' : 'Run detection'}
            </button>
          </>
        }
      >
        <form id="analyze-form" onSubmit={runAnalysis} className="space-y-4">
          <Field label="Traffic image" required>
            <input
              type="file"
              accept="image/*"
              className="input"
              onChange={(event) => setAnalyzeFile(event.target.files?.[0] || null)}
              required
            />
          </Field>
          <Field label="Attribute to camera" hint="Optional - links the record to a camera.">
            <select
              className="input"
              value={analyzeCamera}
              onChange={(event) => setAnalyzeCamera(event.target.value)}
            >
              <option value="">Manual upload (no camera)</option>
              {cameras.map((camera) => (
                <option key={camera.camera_id} value={camera.camera_id}>
                  {camera.camera_id} · {camera.name}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={analyzeRecord}
              onChange={(event) => setAnalyzeRecord(event.target.checked)}
            />
            Save detections as violation records
          </label>

          {analyzeResult && (
            <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3.5">
              <p className="text-sm">
                <strong>Detector:</strong>{' '}
                {DETECTOR_LABELS[analyzeResult.detector] || analyzeResult.detector}
                {analyzeResult.simulated ? ' (simulated)' : ''}
              </p>
              <p className="text-xs text-slate-600">{analyzeResult.notes}</p>
              <p className="text-xs text-slate-600">
                <strong>ANPR:</strong> {analyzeResult.anpr.plate_number || 'no plate read'}{' '}
                {analyzeResult.anpr.configured ? '' : `· ${analyzeResult.anpr.message}`}
              </p>
              {analyzeResult.detections.length === 0 ? (
                <p className="text-sm text-slate-600">No violations detected.</p>
              ) : (
                <ul className="space-y-1.5">
                  {analyzeResult.detections.map((detection, index) => (
                    <li
                      key={`${detection.violation_type}-${index}`}
                      className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <span>{detection.violation_type.replace(/_/g, ' ')}</span>
                      <span className="font-mono text-xs">
                        {confidencePercent(detection.confidence)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {analyzeResult.evidence_image && (
                <img
                  src={evidenceUrl(analyzeResult.evidence_image)}
                  alt="Annotated result"
                  className="w-full rounded border border-slate-200"
                />
              )}
            </div>
          )}
        </form>
      </Modal>
    </>
  )
}

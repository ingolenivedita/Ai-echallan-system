import { useCallback, useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { BrainCircuit, Download, FileSpreadsheet, RefreshCw, Sparkles } from 'lucide-react'
import api, { apiError, downloadUrl } from '../lib/api'
import { useToast } from '../context/ToastContext'
import {
  Card,
  ErrorNote,
  Field,
  InfoNote,
  Loader,
  PageHeader,
  StatCard,
} from '../components/ui'
import { VIOLATION_COLORS, currency, formatDateTime, percent } from '../lib/format'

const RANGES = [
  { value: 7, label: 'Last 7 days' },
  { value: 14, label: 'Last 14 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
]

export default function Reports() {
  const toast = useToast()
  const [report, setReport] = useState(null)
  const [days, setDays] = useState(7)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [error, setError] = useState('')
  const [summary, setSummary] = useState(null)
  const [summarising, setSummarising] = useState(false)

  const params = useCallback(() => {
    const query = { days }
    if (dateFrom && dateTo) {
      query.date_from = dateFrom
      query.date_to = dateTo
    }
    return query
  }, [days, dateFrom, dateTo])

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/reports/overview', { params: params() })
      setReport(data)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    }
  }, [params])

  useEffect(() => {
    load()
  }, [load])

  const generateSummary = async () => {
    setSummarising(true)
    try {
      const { data } = await api.post('/api/reports/ai-summary', null, { params: params() })
      setSummary(data)
      if (!data.configured) {
        toast.warning(data.message, 9000)
      } else if (!data.ok) {
        toast.error(data.message, 9000)
      } else {
        toast.success('AI summary generated')
      }
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setSummarising(false)
    }
  }

  const exportCsv = (kind) => {
    const query = new URLSearchParams(
      Object.entries(params()).map(([key, value]) => [key, String(value)]),
    )
    window.open(downloadUrl(`/api/reports/export/${kind}?${query.toString()}`), '_blank')
  }

  if (!report && error) return <ErrorNote message={error} />
  if (!report) return <Loader label="Building report..." />

  const { totals } = report

  return (
    <>
      <PageHeader
        title="Reports"
        description={`Enforcement summary for ${report.period.from} to ${report.period.to}.`}
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => exportCsv('violations')}
            >
              <Download size={14} /> Violations CSV
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => exportCsv('challans')}
            >
              <FileSpreadsheet size={14} /> Challans CSV
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <Card title="Reporting period" bodyClass="p-4">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <Field label="Quick range">
            <select
              className="input"
              value={days}
              onChange={(event) => {
                setDays(Number(event.target.value))
                setDateFrom('')
                setDateTo('')
              }}
            >
              {RANGES.map((range) => (
                <option key={range.value} value={range.value}>
                  {range.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="From date">
            <input
              type="date"
              className="input"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </Field>
          <Field label="To date">
            <input
              type="date"
              className="input"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </Field>
          <div className="flex items-end">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => {
                setDateFrom('')
                setDateTo('')
              }}
            >
              Use quick range
            </button>
          </div>
        </div>
      </Card>

      <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Violations detected" value={totals.violations} tone="amber" />
        <StatCard
          label="Challans issued"
          value={totals.challans}
          hint={`${percent(totals.challan_conversion_rate)} of violations`}
          tone="brand"
        />
        <StatCard
          label="Amount collected"
          value={currency(totals.collected_amount)}
          hint={`${percent(totals.collection_rate)} collection rate`}
          tone="green"
        />
        <StatCard
          label="Pending amount"
          value={currency(totals.pending_amount)}
          hint={`${totals.pending} unpaid challans`}
          tone="red"
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Daily trend" bodyClass="p-4">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={report.daily} margin={{ top: 8, right: 12, bottom: 4, left: -14 }}>
              <defs>
                <linearGradient id="violationsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#e11d48" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#e11d48" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="challansFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2456c4" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#2456c4" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: '#64748b' }}
                tickFormatter={(value) => value.slice(5)}
              />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area
                type="monotone"
                dataKey="violations"
                name="Violations"
                stroke="#e11d48"
                fill="url(#violationsFill)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="challans"
                name="Challans"
                stroke="#2456c4"
                fill="url(#challansFill)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Fine value by violation type" bodyClass="p-4">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={report.by_type} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: '#64748b' }}
                interval={0}
                tickFormatter={(value) => (value.length > 12 ? `${value.slice(0, 11)}…` : value)}
              />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
                formatter={(value, name) =>
                  name === 'Fine value' ? currency(value) : value
                }
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="amount" name="Fine value" radius={[6, 6, 0, 0]}>
                {report.by_type.map((entry) => (
                  <Cell key={entry.code} fill={VIOLATION_COLORS[entry.code] || '#2456c4'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Camera performance" bodyClass="p-0">
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Camera</th>
                  <th>Mode</th>
                  <th>Violations</th>
                  <th>Challans</th>
                  <th>Fine value</th>
                </tr>
              </thead>
              <tbody>
                {report.by_camera.map((camera) => (
                  <tr key={camera.camera_id}>
                    <td>
                      <p className="font-semibold text-slate-800">{camera.camera_id}</p>
                      <p className="max-w-[14rem] truncate text-xs text-slate-500">
                        {camera.location}
                      </p>
                    </td>
                    <td className="text-xs">{camera.mode}</td>
                    <td>{camera.violations}</td>
                    <td>{camera.challans}</td>
                    <td className="whitespace-nowrap">{currency(camera.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Repeat offenders" subtitle="Vehicles with the most challans in this period" bodyClass="p-0">
          {report.top_offenders.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-500">No challans in this period.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Number plate</th>
                    <th>Challans</th>
                    <th>Total fine</th>
                  </tr>
                </thead>
                <tbody>
                  {report.top_offenders.map((offender) => (
                    <tr key={offender.plate_number}>
                      <td className="font-mono text-sm">{offender.plate_number}</td>
                      <td>{offender.challans}</td>
                      <td>{currency(offender.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-5">
        <Card
          title="AI written briefing"
          subtitle="Generated by the Groq text model from the statistics above"
          actions={
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={generateSummary}
              disabled={summarising}
            >
              <Sparkles size={14} /> {summarising ? 'Generating...' : 'Generate summary'}
            </button>
          }
        >
          {!summary ? (
            <InfoNote tone="slate">
              <span className="flex gap-2">
                <BrainCircuit size={16} className="mt-0.5 shrink-0" />
                Press <strong className="mx-1">Generate summary</strong> to have the Groq model write
                an officer briefing from this report. Requires GROQ_API_KEY in backend/.env.
              </span>
            </InfoNote>
          ) : summary.configured && summary.ok ? (
            <div className="space-y-3">
              <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">
                {summary.summary}
              </p>
              <p className="text-xs text-slate-500">
                Generated for {summary.period.from} to {summary.period.to} ·{' '}
                {formatDateTime(new Date().toISOString().slice(0, 19))}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <InfoNote>{summary.message}</InfoNote>
              <div>
                <p className="label">Statistics that would be sent to the AI model</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
                  {summary.statistics_used.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-5">
        <Card title="Detector breakdown" subtitle="Which detector produced the violations" bodyClass="p-4">
          <div className="flex flex-wrap gap-3">
            {Object.entries(report.detector_split).length === 0 ? (
              <p className="text-sm text-slate-500">No detections in this period.</p>
            ) : (
              Object.entries(report.detector_split).map(([detector, count]) => (
                <div
                  key={detector}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
                >
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {detector.replace(/_/g, ' ')}
                  </p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">{count}</p>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </>
  )
}

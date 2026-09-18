import { useCallback, useEffect, useState } from 'react'
import {
  BrainCircuit,
  CheckCircle2,
  CreditCard,
  Database,
  ExternalLink,
  KeyRound,
  MessageSquare,
  Plug,
  RefreshCw,
  ScanLine,
  Send,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useToast } from '../context/ToastContext'
import {
  Card,
  ErrorNote,
  Field,
  InfoNote,
  Loader,
  Modal,
  PageHeader,
  Pill,
} from '../components/ui'
import { formatDateTime } from '../lib/format'

const ICONS = {
  ai: BrainCircuit,
  anpr: ScanLine,
  sms: MessageSquare,
  payment: CreditCard,
}

export default function ApiConfiguration() {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [testing, setTesting] = useState('')
  const [smsOpen, setSmsOpen] = useState(false)
  const [smsPhone, setSmsPhone] = useState('')
  const [smsMessage, setSmsMessage] = useState(
    'Test SMS from the RTO E-Challan System. Ignore this message.',
  )
  const [smsBusy, setSmsBusy] = useState(false)
  const [logs, setLogs] = useState(null)

  const load = useCallback(async () => {
    try {
      const [{ data }, { data: logData }] = await Promise.all([
        api.get('/api/config/status'),
        api.get('/api/config/sms/logs', { params: { limit: 12 } }),
      ])
      setStatus(data)
      setLogs(logData)
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const test = async (key) => {
    setTesting(key)
    try {
      const { data } = await api.post(`/api/config/test/${key}`)
      if (data.ok) toast.success(`${data.provider}: ${data.message}`)
      else if (!data.configured) toast.warning(`${data.provider}: ${data.message}`, 10000)
      else toast.error(`${data.provider}: ${data.message}`, 10000)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setTesting('')
    }
  }

  const testAll = async () => {
    setTesting('all')
    try {
      await api.post('/api/config/test-all')
      toast.info('All four services tested')
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setTesting('')
    }
  }

  const sendTestSms = async (event) => {
    event.preventDefault()
    setSmsBusy(true)
    try {
      const { data } = await api.post('/api/config/sms/send-test', {
        phone: smsPhone,
        message: smsMessage,
      })
      if (data.ok) toast.success(data.message)
      else if (!data.configured) toast.warning(data.message, 10000)
      else toast.error(data.message, 10000)
      setSmsOpen(false)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setSmsBusy(false)
    }
  }

  if (!status && error) return <ErrorNote message={error} />
  if (!status) return <Loader label="Reading API configuration..." />

  return (
    <>
      <PageHeader
        title="API Configuration"
        description="Status of the four external services. Keys live in backend/.env and are never sent to the browser."
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={testAll}
              disabled={testing === 'all'}
            >
              <Plug size={14} /> {testing === 'all' ? 'Testing...' : 'Test all'}
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="mb-5">
        <InfoNote tone="sky">
          <strong>
            {status.summary.configured} of {status.summary.total} services configured.
          </strong>{' '}
          A missing key never produces a fake response: the related feature reports
          &ldquo;API not configured&rdquo; and falls back to DEMO MODE where that is meaningful.
        </InfoNote>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {status.services.map((service) => {
          const Icon = ICONS[service.key] || KeyRound
          return (
            <Card key={service.key} bodyClass="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span
                    className={`grid h-11 w-11 shrink-0 place-items-center rounded-lg ${
                      service.configured
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    <Icon size={20} />
                  </span>
                  <div>
                    <h3 className="text-base font-semibold text-slate-900">{service.name}</h3>
                    <p className="text-sm text-slate-500">{service.purpose}</p>
                  </div>
                </div>
                <Pill
                  status={service.status}
                  label={service.configured ? 'Connected' : 'Not Connected'}
                />
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3.5 text-xs">
                <div className="col-span-2">
                  <dt className="font-semibold uppercase tracking-wide text-slate-500">
                    Masked key
                  </dt>
                  <dd className="mt-0.5 break-all font-mono text-slate-700">
                    {service.masked_key}
                  </dd>
                </div>
                {Object.entries(service.extra).map(([key, value]) => (
                  <div key={key}>
                    <dt className="font-semibold uppercase tracking-wide text-slate-500">
                      {key.replace(/_/g, ' ')}
                    </dt>
                    <dd className="mt-0.5 break-all font-mono text-slate-700">{String(value)}</dd>
                  </div>
                ))}
                <div className="col-span-2">
                  <dt className="font-semibold uppercase tracking-wide text-slate-500">
                    .env keys
                  </dt>
                  <dd className="mt-0.5 font-mono text-slate-700">
                    {service.env_keys.join(', ')}
                  </dd>
                </div>
              </dl>

              {service.last_test && (
                <div
                  className={`mt-3 rounded-lg border px-3.5 py-2.5 text-sm ${
                    service.last_test.ok
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                      : service.last_test.configured
                        ? 'border-rose-200 bg-rose-50 text-rose-800'
                        : 'border-amber-200 bg-amber-50 text-amber-900'
                  }`}
                >
                  <p className="flex items-center gap-1.5 font-semibold">
                    {service.last_test.ok ? (
                      <CheckCircle2 size={14} />
                    ) : (
                      <XCircle size={14} />
                    )}
                    Last test {formatDateTime(service.last_test.checked_at)}
                    {service.last_test.latency_ms != null &&
                      ` · ${service.last_test.latency_ms} ms`}
                  </p>
                  <p className="mt-0.5">{service.last_test.message}</p>
                </div>
              )}

              <details className="mt-3 rounded-lg border border-slate-200 px-3.5 py-2.5">
                <summary className="cursor-pointer text-sm font-medium text-slate-700">
                  Configuration instructions
                </summary>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-600">
                  {service.instructions.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                <p className="mt-2 text-xs text-slate-500">{service.demo_behaviour}</p>
                <a
                  href={service.docs_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700"
                >
                  Open provider dashboard <ExternalLink size={13} />
                </a>
              </details>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={() => test(service.key)}
                  disabled={testing === service.key}
                >
                  <Plug size={13} />
                  {testing === service.key ? 'Testing...' : 'Test Connection'}
                </button>
                {service.key === 'sms' && (
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    onClick={() => setSmsOpen(true)}
                  >
                    <Send size={13} /> Send test SMS
                  </button>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Card title="Database" bodyClass="p-5">
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700">
              <Database size={20} />
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">
                {status.database.backend === 'mongodb' ? 'MongoDB' : 'Local JSON store'}
              </p>
              <p className="text-sm text-slate-500">
                Database: <span className="font-mono">{status.database.database_name}</span> ·
                URI: <span className="font-mono">{status.database.masked_uri}</span>
              </p>
              <div className="mt-2 flex items-center gap-2">
                <Pill status={status.database.healthy ? 'CONNECTED' : 'NOT_CONNECTED'} />
                {status.database.mongo_uri_configured ? null : <Pill status="DEMO" label="Fallback" />}
              </div>
              {status.database.note && (
                <p className="mt-2 text-xs text-slate-500">{status.database.note}</p>
              )}
              {status.database.error && (
                <p className="mt-1 text-xs text-amber-700">{status.database.error}</p>
              )}
            </div>
          </div>
        </Card>

        <Card title="Authentication" bodyClass="p-5">
          <div className="flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-violet-50 text-violet-700">
              <ShieldCheck size={20} />
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">
                JWT · {status.auth.algorithm} · {status.auth.token_lifetime_minutes} min sessions
              </p>
              <p className="text-sm text-slate-500">
                Secret: <span className="font-mono">{status.auth.masked_secret}</span>
              </p>
              <div className="mt-2">
                <Pill
                  status={status.auth.jwt_configured ? 'CONNECTED' : 'DEMO'}
                  label={status.auth.jwt_configured ? 'JWT_SECRET set' : 'Auto-generated secret'}
                />
              </div>
              {status.auth.note && (
                <p className="mt-2 text-xs text-slate-500">{status.auth.note}</p>
              )}
            </div>
          </div>
        </Card>
      </div>

      {logs && (
        <div className="mt-5">
          <Card
            title="SMS activity"
            subtitle={`${logs.summary.sent} sent · ${logs.summary.failed} failed · ${logs.summary.demo_not_sent} blocked in demo mode`}
            bodyClass="p-0"
          >
            {logs.logs.length === 0 ? (
              <p className="px-5 py-6 text-sm text-slate-500">No SMS attempts yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Phone</th>
                      <th>Purpose</th>
                      <th>Status</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.logs.map((log) => (
                      <tr key={log.id}>
                        <td className="whitespace-nowrap text-xs">
                          {formatDateTime(log.created_at)}
                        </td>
                        <td className="font-mono text-xs">{log.phone}</td>
                        <td className="text-xs">{log.purpose}</td>
                        <td>
                          <Pill status={log.status} />
                        </td>
                        <td className="max-w-md text-xs text-slate-600">{log.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      <p className="mt-4 text-xs text-slate-500">
        Configuration file: <span className="font-mono">{status.env_file}</span> · read at{' '}
        {formatDateTime(status.checked_at)}. Restart the backend after editing the file.
      </p>

      <Modal
        open={smsOpen}
        onClose={() => setSmsOpen(false)}
        title="Send a test SMS"
        subtitle="Uses the configured provider. In demo mode the attempt is logged but not delivered."
        size="sm"
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setSmsOpen(false)}>
              Cancel
            </button>
            <button type="submit" form="sms-form" className="btn-primary" disabled={smsBusy}>
              <Send size={15} /> {smsBusy ? 'Sending...' : 'Send'}
            </button>
          </>
        }
      >
        <form id="sms-form" onSubmit={sendTestSms} className="space-y-4">
          <Field label="Mobile number" required>
            <input
              className="input font-mono"
              value={smsPhone}
              onChange={(event) => setSmsPhone(event.target.value)}
              placeholder="9876543210"
              minLength={10}
              required
            />
          </Field>
          <Field label="Message">
            <textarea
              className="input h-24"
              value={smsMessage}
              onChange={(event) => setSmsMessage(event.target.value)}
            />
          </Field>
        </form>
      </Modal>
    </>
  )
}

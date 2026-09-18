import { useCallback, useEffect, useState } from 'react'
import {
  BadgeIndianRupee,
  Ban,
  CheckCircle2,
  CreditCard,
  Filter,
  Printer,
  ReceiptText,
  RefreshCw,
  Send,
  Wallet,
} from 'lucide-react'
import api, { apiError, evidenceUrl } from '../lib/api'
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
import { currency, formatDate, formatDateTime, humanStatus } from '../lib/format'

const RAZORPAY_SCRIPT = 'https://checkout.razorpay.com/v1/checkout.js'

function loadRazorpay() {
  return new Promise((resolve) => {
    if (window.Razorpay) {
      resolve(true)
      return
    }
    const script = document.createElement('script')
    script.src = RAZORPAY_SCRIPT
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

const EMPTY_FILTERS = { status: '', camera_id: '', plate: '', date_from: '', date_to: '' }

export default function Challans() {
  const toast = useToast()

  const [challans, setChallans] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [stats, setStats] = useState(null)
  const [cameras, setCameras] = useState([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState('')
  const [paymentNote, setPaymentNote] = useState(null)

  const load = useCallback(async () => {
    try {
      const params = { page, limit: 15 }
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value
      })
      const [{ data }, { data: statsData }] = await Promise.all([
        api.get('/api/challans', { params }),
        api.get('/api/challans/stats'),
      ])
      setChallans(data.challans)
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
  }, [])

  const openDetail = async (challan) => {
    setPaymentNote(null)
    try {
      const { data } = await api.get(`/api/challans/${challan.id}`)
      setDetail(data)
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  const resendSms = async () => {
    setBusy('sms')
    try {
      const { data } = await api.post(`/api/challans/${detail.id}/resend-sms`)
      if (data.ok) toast.success(data.message)
      else if (!data.configured) toast.warning(data.message, 9000)
      else toast.error(data.message)
      openDetail(detail)
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setBusy('')
    }
  }

  const changeStatus = async (status) => {
    setBusy('status')
    try {
      await api.patch(`/api/challans/${detail.id}/status`, { status, remarks: '' })
      toast.success(`Challan marked ${humanStatus(status)}`)
      setDetail(null)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setBusy('')
    }
  }

  const payOnline = async () => {
    setBusy('pay')
    setPaymentNote(null)
    try {
      const { data } = await api.post('/api/payments/create-order', { challan_id: detail.id })

      if (!data.configured) {
        setPaymentNote({
          tone: 'amber',
          text: `${data.message} Use "Record offline payment" to complete the demo walkthrough.`,
        })
        return
      }
      if (!data.ok) {
        setPaymentNote({ tone: 'amber', text: data.message })
        return
      }

      const ready = await loadRazorpay()
      if (!ready) {
        setPaymentNote({
          tone: 'amber',
          text: 'Razorpay Checkout script could not be loaded. Check the internet connection.',
        })
        return
      }

      const checkout = new window.Razorpay({
        key: data.data.key_id,
        order_id: data.data.order_id,
        amount: Math.round(Number(data.data.amount) * 100),
        currency: data.data.currency || 'INR',
        name: 'RTO E-Challan Payment',
        description: `${detail.challan_number} · ${detail.violation_label}`,
        prefill: {
          name: detail.owner_name || '',
          contact: detail.owner_phone || '',
        },
        notes: { challan_number: detail.challan_number },
        theme: { color: '#2456c4' },
        handler: async (response) => {
          try {
            const { data: verified } = await api.post('/api/payments/verify', {
              challan_id: detail.id,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            })
            toast.success(`Payment verified for ${verified.challan.challan_number}`)
            setDetail(null)
            load()
          } catch (verifyError) {
            toast.error(apiError(verifyError))
          }
        },
        modal: {
          ondismiss: () => toast.info('Payment window closed'),
        },
      })
      checkout.open()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setBusy('')
    }
  }

  const payOffline = async () => {
    setBusy('offline')
    try {
      const { data } = await api.post(
        '/api/payments/offline',
        { challan_id: detail.id },
        { params: { method: 'CASH_COUNTER', reference: `COUNTER-${Date.now()}` } },
      )
      toast.success(
        `${data.challan.challan_number} marked PAID (${currency(data.challan.amount_paid)})`,
      )
      setDetail(null)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    } finally {
      setBusy('')
    }
  }

  if (loading && !challans.length) return <Loader label="Loading challans..." />

  return (
    <>
      <PageHeader
        title="Challans"
        description="Issued e-challans, payment status and SMS delivery."
        actions={
          <button type="button" className="btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      {stats && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Total challans" value={stats.total} icon={ReceiptText} tone="brand" />
          <StatCard
            label="Pending"
            value={stats.by_status?.PENDING ?? 0}
            hint={currency(stats.pending_amount)}
            tone="amber"
            icon={Wallet}
          />
          <StatCard
            label="Paid"
            value={stats.by_status?.PAID ?? 0}
            hint={currency(stats.collected_amount)}
            tone="green"
            icon={CheckCircle2}
          />
          <StatCard
            label="Total fine value"
            value={currency(stats.total_fine_amount)}
            hint={`${stats.overdue} overdue`}
            tone="violet"
            icon={BadgeIndianRupee}
          />
        </div>
      )}

      <div className="mt-5">
        <Card title="Filters" bodyClass="p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Field label="Status">
              <select
                className="input"
                value={filters.status}
                onChange={(event) => {
                  setPage(1)
                  setFilters((current) => ({ ...current, status: event.target.value }))
                }}
              >
                <option value="">All</option>
                {['PENDING', 'PAID', 'CANCELLED', 'DISPUTED'].map((status) => (
                  <option key={status} value={status}>
                    {humanStatus(status)}
                  </option>
                ))}
              </select>
            </Field>
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
                    {camera.camera_id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Number plate">
              <input
                className="input font-mono"
                value={filters.plate}
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
        <Card title={`Issued challans (${meta.total})`} bodyClass="p-0">
          {challans.length === 0 ? (
            <EmptyState
              icon={ReceiptText}
              title="No challans yet"
              description="Approve a violation with a number plate to generate its e-challan."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Challan</th>
                      <th>Vehicle / Owner</th>
                      <th>Violation</th>
                      <th>Camera</th>
                      <th>Fine</th>
                      <th>SMS</th>
                      <th>Status</th>
                      <th className="text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {challans.map((challan) => (
                      <tr key={challan.id}>
                        <td className="whitespace-nowrap">
                          <p className="font-mono text-xs font-semibold text-slate-800">
                            {challan.challan_number}
                          </p>
                          <p className="text-xs text-slate-500">
                            {formatDateTime(challan.issued_at)}
                          </p>
                        </td>
                        <td>
                          <p className="font-mono text-sm text-slate-800">
                            {challan.plate_number || '-'}
                          </p>
                          <p className="max-w-[12rem] truncate text-xs text-slate-500">
                            {challan.owner_name || 'Owner not in register'}
                            {challan.owner_phone ? ` · ${challan.owner_phone}` : ''}
                          </p>
                        </td>
                        <td>
                          <p className="text-slate-800">{challan.violation_label}</p>
                          <p className="text-xs text-slate-500">{challan.section}</p>
                        </td>
                        <td className="whitespace-nowrap text-xs">
                          <p className="font-medium text-slate-700">{challan.camera_id}</p>
                          <p className="max-w-[11rem] truncate text-slate-500">
                            {challan.location}
                          </p>
                        </td>
                        <td className="whitespace-nowrap font-semibold text-slate-800">
                          {currency(challan.fine_amount)}
                          {challan.overdue && (
                            <span className="mt-0.5 block text-[10px] font-bold uppercase text-rose-600">
                              overdue
                            </span>
                          )}
                        </td>
                        <td>
                          <Pill status={challan.sms_status} />
                        </td>
                        <td>
                          <Pill status={challan.status} />
                        </td>
                        <td className="text-right">
                          <button
                            type="button"
                            className="btn-secondary btn-sm"
                            onClick={() => openDetail(challan)}
                          >
                            Open
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={meta.page} pages={meta.pages} total={meta.total} onChange={setPage} />
            </>
          )}
        </Card>
      </div>

      {/* ---------------- challan detail ---------------- */}
      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail ? `Challan ${detail.challan_number}` : ''}
        subtitle={detail ? `${detail.violation_label} · ${detail.section}` : ''}
        size="lg"
        footer={
          detail && (
            <>
              <button
                type="button"
                className="btn-secondary btn-sm mr-auto"
                onClick={() => window.print()}
              >
                <Printer size={14} /> Print
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={resendSms}
                disabled={busy === 'sms'}
              >
                <Send size={15} /> {busy === 'sms' ? 'Sending...' : 'Resend SMS'}
              </button>
              {detail.status === 'PENDING' && (
                <>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => changeStatus('CANCELLED')}
                    disabled={busy === 'status'}
                  >
                    <Ban size={15} /> Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={payOffline}
                    disabled={busy === 'offline'}
                  >
                    <Wallet size={15} /> Record offline payment
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={payOnline}
                    disabled={busy === 'pay'}
                  >
                    <CreditCard size={15} /> Pay online
                  </button>
                </>
              )}
            </>
          )
        }
      >
        {detail && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Pill status={detail.status} />
              {detail.overdue && <Pill status="OPEN" label="OVERDUE" />}
              {detail.simulated && <Pill status="DEMO" label="SIMULATED DETECTION" />}
              <span className="text-xs text-slate-500">
                Due by {formatDate(detail.due_date)}
              </span>
            </div>

            {paymentNote && <InfoNote tone={paymentNote.tone}>{paymentNote.text}</InfoNote>}

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {detail.office?.rto_office_name} · {detail.office?.rto_code}
              </p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">
                {currency(detail.fine_amount)}
              </p>
              <p className="text-xs text-slate-500">
                {detail.status === 'PAID'
                  ? `Paid ${formatDateTime(detail.paid_at)} via ${detail.paid_via || '-'}`
                  : 'Payable at the RTO counter or online'}
              </p>
            </div>

            <KeyValue
              items={[
                { label: 'Challan number', value: detail.challan_number },
                { label: 'Issued at', value: formatDateTime(detail.issued_at) },
                { label: 'Issued by', value: detail.issued_by },
                { label: 'Vehicle', value: detail.plate_number || '-' },
                { label: 'Owner', value: detail.owner_name || 'Not in register' },
                { label: 'Owner phone', value: detail.owner_phone || 'Not available' },
                { label: 'Violation', value: detail.violation_label },
                { label: 'Legal section', value: detail.section },
                { label: 'Camera', value: `${detail.camera_id} · ${detail.camera_name || ''}` },
                { label: 'Location', value: detail.location },
                { label: 'Detected at', value: formatDateTime(detail.detected_at) },
                { label: 'SMS status', value: `${detail.sms_status} · ${detail.sms_detail || '-'}` },
              ]}
            />

            {detail.evidence_image && (
              <div>
                <p className="label">Evidence</p>
                <a href={evidenceUrl(detail.evidence_image)} target="_blank" rel="noreferrer">
                  <img
                    src={evidenceUrl(detail.evidence_image)}
                    alt="Challan evidence"
                    className="w-full rounded-lg border border-slate-200"
                  />
                </a>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}

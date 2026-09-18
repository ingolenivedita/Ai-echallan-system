import { useCallback, useEffect, useState } from 'react'
import { Car, Pencil, Plus, RefreshCw, Search, Trash2 } from 'lucide-react'
import api, { apiError } from '../lib/api'
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
} from '../components/ui'
import { currency, formatDate, formatDateTime } from '../lib/format'

const EMPTY = {
  plate_number: '',
  owner_name: '',
  owner_phone: '',
  owner_address: '',
  vehicle_type: 'Two Wheeler',
  make_model: '',
  colour: '',
  registration_date: '',
  insurance_valid_till: '',
  puc_valid_till: '',
}

const TYPES = ['Two Wheeler', 'Car', 'Auto Rickshaw', 'Goods Vehicle', 'Bus', 'Other']

export default function Vehicles() {
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [vehicles, setVehicles] = useState([])
  const [meta, setMeta] = useState({ page: 1, pages: 1, total: 0 })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [detail, setDetail] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/vehicles', {
        params: { page, limit: 15, search: search || undefined },
      })
      setVehicles(data.vehicles)
      setMeta({ page: data.page, pages: data.pages, total: data.total })
      setError('')
    } catch (requestError) {
      setError(apiError(requestError))
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  const change = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY)
    setFormError('')
    setFormOpen(true)
  }

  const openEdit = (vehicle) => {
    setEditing(vehicle)
    setForm({ ...EMPTY, ...vehicle })
    setFormError('')
    setFormOpen(true)
  }

  const save = async (event) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      if (editing) {
        await api.put(`/api/vehicles/${editing.plate_number}`, form)
        toast.success(`${editing.plate_number} updated`)
      } else {
        await api.post('/api/vehicles', form)
        toast.success(`${form.plate_number.toUpperCase()} registered`)
      }
      setFormOpen(false)
      load()
    } catch (requestError) {
      setFormError(apiError(requestError))
    } finally {
      setSaving(false)
    }
  }

  const openDetail = async (vehicle) => {
    try {
      const { data } = await api.get(`/api/vehicles/${vehicle.plate_number}`)
      setDetail(data)
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  const remove = async (vehicle) => {
    try {
      await api.delete(`/api/vehicles/${vehicle.plate_number}`)
      toast.success(`${vehicle.plate_number} removed`)
      load()
    } catch (requestError) {
      toast.error(apiError(requestError))
    }
  }

  if (loading && !vehicles.length) return <Loader label="Loading vehicle register..." />

  return (
    <>
      <PageHeader
        title="Vehicles"
        description="Owner details drive challan delivery - a vehicle without a mobile number cannot receive an SMS notice."
        actions={
          <>
            <button type="button" className="btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={14} /> Refresh
            </button>
            <button type="button" className="btn-primary btn-sm" onClick={openCreate}>
              <Plus size={15} /> Add vehicle
            </button>
          </>
        }
      />

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <Card bodyClass="p-4">
        <div className="relative max-w-md">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            className="input pl-9"
            placeholder="Search by number plate, owner name or phone"
            value={search}
            onChange={(event) => {
              setPage(1)
              setSearch(event.target.value)
            }}
          />
        </div>
      </Card>

      <div className="mt-5">
        <Card title={`Vehicle register (${meta.total})`} bodyClass="p-0">
          {vehicles.length === 0 ? (
            <EmptyState
              icon={Car}
              title="No vehicles found"
              description="Vehicles are added automatically when a challan is issued, or manually here."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Number plate</th>
                      <th>Owner</th>
                      <th>Vehicle</th>
                      <th>Violations</th>
                      <th>Fine total</th>
                      <th>Source</th>
                      <th className="text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vehicles.map((vehicle) => (
                      <tr key={vehicle.id}>
                        <td>
                          <button
                            type="button"
                            className="font-mono text-sm font-semibold text-brand-700 hover:underline"
                            onClick={() => openDetail(vehicle)}
                          >
                            {vehicle.plate_number}
                          </button>
                        </td>
                        <td>
                          <p className="text-slate-800">{vehicle.owner_name || '-'}</p>
                          <p className="text-xs text-slate-500">
                            {vehicle.owner_phone || 'No mobile number'}
                          </p>
                        </td>
                        <td className="text-xs">
                          <p className="text-slate-700">{vehicle.vehicle_type}</p>
                          <p className="text-slate-500">
                            {vehicle.make_model || '-'}
                            {vehicle.colour ? ` · ${vehicle.colour}` : ''}
                          </p>
                        </td>
                        <td className="font-medium text-slate-800">
                          {vehicle.violation_count ?? 0}
                        </td>
                        <td className="whitespace-nowrap text-slate-800">
                          {currency(vehicle.total_fine)}
                          <span className="block text-xs text-slate-500">
                            paid {currency(vehicle.total_paid)}
                          </span>
                        </td>
                        <td>
                          <Pill
                            status={vehicle.source === 'MANUAL' ? 'APPROVED' : 'DEMO'}
                            label={vehicle.source === 'AUTO_FROM_DETECTION' ? 'AUTO' : vehicle.source}
                          />
                        </td>
                        <td>
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              className="btn-secondary btn-sm"
                              onClick={() => openEdit(vehicle)}
                            >
                              <Pencil size={13} /> Edit
                            </button>
                            {isAdmin && (
                              <button
                                type="button"
                                className="btn-danger btn-sm"
                                onClick={() => remove(vehicle)}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </div>
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

      {/* ---------------- add / edit ---------------- */}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? `Edit ${editing.plate_number}` : 'Register vehicle'}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setFormOpen(false)}>
              Cancel
            </button>
            <button type="submit" form="vehicle-form" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save vehicle'}
            </button>
          </>
        }
      >
        <form id="vehicle-form" onSubmit={save} className="space-y-4">
          {formError && <ErrorNote message={formError} />}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Number plate" required>
              <input
                className="input font-mono uppercase"
                value={form.plate_number}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    plate_number: event.target.value.toUpperCase(),
                  }))
                }
                disabled={Boolean(editing)}
                placeholder="KA05MJ2020"
                required
              />
            </Field>
            <Field label="Owner name">
              <input className="input" value={form.owner_name} onChange={change('owner_name')} />
            </Field>
            <Field label="Owner mobile" hint="10 digit Indian mobile number for SMS notices.">
              <input
                className="input font-mono"
                value={form.owner_phone}
                onChange={change('owner_phone')}
                placeholder="9000000011"
              />
            </Field>
            <Field label="Vehicle type">
              <select className="input" value={form.vehicle_type} onChange={change('vehicle_type')}>
                {TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Make and model">
              <input className="input" value={form.make_model} onChange={change('make_model')} />
            </Field>
            <Field label="Colour">
              <input className="input" value={form.colour} onChange={change('colour')} />
            </Field>
            <Field label="Registration date">
              <input
                type="date"
                className="input"
                value={form.registration_date}
                onChange={change('registration_date')}
              />
            </Field>
            <Field label="Insurance valid till">
              <input
                type="date"
                className="input"
                value={form.insurance_valid_till}
                onChange={change('insurance_valid_till')}
              />
            </Field>
            <Field label="PUC valid till">
              <input
                type="date"
                className="input"
                value={form.puc_valid_till}
                onChange={change('puc_valid_till')}
              />
            </Field>
          </div>
          <Field label="Owner address">
            <textarea
              className="input h-20"
              value={form.owner_address}
              onChange={change('owner_address')}
            />
          </Field>
        </form>
      </Modal>

      {/* ---------------- detail ---------------- */}
      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail ? detail.plate_number : ''}
        subtitle={detail ? `${detail.vehicle_type} · ${detail.make_model || 'model not recorded'}` : ''}
        size="lg"
      >
        {detail && (
          <div className="space-y-5">
            <KeyValue
              items={[
                { label: 'Owner', value: detail.owner_name || '-' },
                { label: 'Mobile', value: detail.owner_phone || '-' },
                { label: 'Address', value: detail.owner_address || '-' },
                { label: 'Registered on', value: formatDate(detail.registration_date) },
                { label: 'Insurance valid till', value: formatDate(detail.insurance_valid_till) },
                { label: 'PUC valid till', value: formatDate(detail.puc_valid_till) },
                { label: 'Total violations', value: detail.violation_count ?? 0 },
                { label: 'Fine total', value: currency(detail.total_fine) },
              ]}
            />

            {!detail.owner_phone && (
              <InfoNote>
                No mobile number on record - challans for this vehicle cannot be delivered by SMS.
              </InfoNote>
            )}

            <div>
              <p className="label">Challan history ({detail.challans.length})</p>
              {detail.challans.length === 0 ? (
                <p className="text-sm text-slate-500">No challans issued.</p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Challan</th>
                        <th>Violation</th>
                        <th>Issued</th>
                        <th>Fine</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.challans.map((challan) => (
                        <tr key={challan.id}>
                          <td className="font-mono text-xs">{challan.challan_number}</td>
                          <td>{challan.violation_label}</td>
                          <td className="whitespace-nowrap text-xs">
                            {formatDateTime(challan.issued_at)}
                          </td>
                          <td>{currency(challan.fine_amount)}</td>
                          <td>
                            <Pill status={challan.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <p className="label">Violation history ({detail.violations.length})</p>
              {detail.violations.length === 0 ? (
                <p className="text-sm text-slate-500">No violations recorded.</p>
              ) : (
                <ul className="space-y-1.5">
                  {detail.violations.slice(0, 10).map((violation) => (
                    <li
                      key={violation.id}
                      className="flex items-center justify-between rounded border border-slate-200 px-3 py-2 text-sm"
                    >
                      <span>
                        {violation.violation_label}
                        <span className="ml-2 text-xs text-slate-500">
                          {violation.camera_id} · {formatDateTime(violation.detected_at)}
                        </span>
                      </span>
                      <Pill status={violation.status} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

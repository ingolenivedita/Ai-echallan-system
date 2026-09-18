import { AlertCircle, Inbox, Loader2, X } from 'lucide-react'
import { statusPill } from '../lib/format'

export function Card({ title, subtitle, actions, children, className = '', bodyClass = 'p-5' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-700',
    green: 'bg-emerald-50 text-emerald-700',
    red: 'bg-rose-50 text-rose-700',
    amber: 'bg-amber-50 text-amber-700',
    slate: 'bg-slate-100 text-slate-600',
    violet: 'bg-violet-50 text-violet-700',
  }
  return (
    <div className="card flex items-start gap-4 p-4">
      {Icon && (
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-lg ${tones[tone]}`}>
          <Icon size={20} />
        </span>
      )}
      <div className="min-w-0">
        <p className="truncate text-xs font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </p>
        <p className="mt-1 text-2xl font-semibold leading-tight text-slate-900">{value}</p>
        {hint && <p className="mt-0.5 truncate text-xs text-slate-500">{hint}</p>}
      </div>
    </div>
  )
}

export function Pill({ status, label, className = '' }) {
  return (
    <span className={`pill ${statusPill(status)} ${className}`}>
      {label ?? String(status || '-').replace(/_/g, ' ')}
    </span>
  )
}

export function LiveDot({ online }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${
        online ? 'live-dot bg-emerald-500' : 'bg-rose-500'
      }`}
    />
  )
}

export function Loader({ label = 'Loading...', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-2 py-10 text-sm text-slate-500 ${className}`}>
      <Loader2 size={18} className="animate-spin" />
      {label}
    </div>
  )
}

export function EmptyState({ title, description, icon: Icon = Inbox, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-400">
        <Icon size={22} />
      </span>
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      {description && <p className="max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorNote({ message }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-800">
      <AlertCircle size={16} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function InfoNote({ children, tone = 'amber' }) {
  const tones = {
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    sky: 'border-sky-200 bg-sky-50 text-sky-900',
    slate: 'border-slate-200 bg-slate-50 text-slate-600',
  }
  return (
    <div className={`rounded-lg border px-3.5 py-2.5 text-sm ${tones[tone]}`}>{children}</div>
  )
}

export function Field({ label, hint, children, required }) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {required && <span className="ml-0.5 text-rose-500">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export function Modal({ open, title, subtitle, onClose, children, footer, size = 'md' }) {
  if (!open) return null
  const widths = { sm: 'max-w-md', md: 'max-w-2xl', lg: 'max-w-4xl', xl: 'max-w-6xl' }
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:p-8">
      <div className={`w-full ${widths[size]} rounded-xl bg-white shadow-2xl`}>
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{title}</h3>
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 px-5 py-3.5">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}

export function Pagination({ page, pages, total, onChange }) {
  if (!total) return null
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm text-slate-600">
      <span>
        Page <strong>{page}</strong> of <strong>{pages}</strong> · {total} record
        {total === 1 ? '' : 's'}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function KeyValue({ items, columns = 2 }) {
  return (
    <dl
      className={`grid gap-x-6 gap-y-3 ${
        columns === 1 ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2'
      }`}
    >
      {items
        .filter((item) => item)
        .map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {item.label}
            </dt>
            <dd className="mt-0.5 break-words text-sm text-slate-800">{item.value ?? '-'}</dd>
          </div>
        ))}
    </dl>
  )
}

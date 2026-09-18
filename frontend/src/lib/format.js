// The backend stores timestamps as naive ISO strings in UTC.
export function parseUtc(value) {
  if (!value) return null
  const normalised = /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const date = new Date(normalised)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value) {
  const date = parseUtc(value)
  if (!date) return '-'
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function formatTime(value) {
  const date = parseUtc(value)
  if (!date) return '-'
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatDate(value) {
  if (!value) return '-'
  const date = parseUtc(value.length === 10 ? `${value}T00:00:00` : value)
  if (!date) return value
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function timeAgo(value) {
  const date = parseUtc(value)
  if (!date) return 'never'
  const seconds = Math.max(Math.floor((Date.now() - date.getTime()) / 1000), 0)
  if (seconds < 10) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function currency(amount) {
  const value = Number(amount || 0)
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export function percent(value) {
  return `${Number(value || 0).toFixed(1)}%`
}

export function confidencePercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

export const VIOLATION_COLORS = {
  NO_HELMET: '#e11d48',
  TRIPLE_RIDING: '#f59e0b',
  WRONG_SIDE_DRIVING: '#7c3aed',
  PROHIBITED_CONTAINER: '#0f766e',
}

export const CHART_COLORS = ['#2456c4', '#f59e0b', '#0f766e', '#e11d48', '#7c3aed', '#0ea5e9']

export function statusPill(status) {
  const map = {
    ONLINE: 'bg-emerald-100 text-emerald-700',
    OFFLINE: 'bg-rose-100 text-rose-700',
    CONNECTING: 'bg-amber-100 text-amber-700',
    DISABLED: 'bg-slate-200 text-slate-600',
    PENDING: 'bg-amber-100 text-amber-700',
    PAID: 'bg-emerald-100 text-emerald-700',
    CANCELLED: 'bg-slate-200 text-slate-600',
    DISPUTED: 'bg-orange-100 text-orange-700',
    PENDING_REVIEW: 'bg-amber-100 text-amber-700',
    APPROVED: 'bg-sky-100 text-sky-700',
    REJECTED: 'bg-slate-200 text-slate-600',
    CHALLAN_ISSUED: 'bg-brand-100 text-brand-700',
    OPEN: 'bg-rose-100 text-rose-700',
    ACKNOWLEDGED: 'bg-amber-100 text-amber-700',
    RESOLVED: 'bg-emerald-100 text-emerald-700',
    SENT: 'bg-emerald-100 text-emerald-700',
    FAILED: 'bg-rose-100 text-rose-700',
    DEMO_NOT_SENT: 'bg-amber-100 text-amber-700',
    NOT_SENT: 'bg-slate-200 text-slate-600',
    CONNECTED: 'bg-emerald-100 text-emerald-700',
    NOT_CONNECTED: 'bg-rose-100 text-rose-700',
    LIVE: 'bg-emerald-100 text-emerald-700',
    DEMO: 'bg-amber-100 text-amber-800',
  }
  return map[status] || 'bg-slate-200 text-slate-600'
}

export function humanStatus(status) {
  if (!status) return '-'
  return String(status)
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export const DETECTOR_LABELS = {
  GROQ_VISION: 'Groq AI Vision',
  OPENCV_HEURISTIC: 'OpenCV Heuristic',
  DEMO_SIMULATOR: 'Demo Simulator',
  OFFICER_MANUAL: 'Officer Manual',
}

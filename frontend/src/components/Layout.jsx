import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3,
  BellRing,
  Car,
  Cctv,
  Gavel,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  MonitorPlay,
  Network,
  ReceiptText,
  Settings as SettingsIcon,
  ShieldAlert,
  Users as UsersIcon,
  Wrench,
  X,
} from 'lucide-react'
import api from '../lib/api'
import { useAuth } from '../context/AuthContext'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/live', label: 'Live Monitoring', icon: MonitorPlay },
  { to: '/cameras', label: 'Cameras', icon: Cctv },
  { to: '/violations', label: 'Violations', icon: ShieldAlert },
  { to: '/challans', label: 'Challans', icon: ReceiptText },
  { to: '/vehicles', label: 'Vehicles', icon: Car },
  { to: '/reports', label: 'Reports', icon: BarChart3 },
  { to: '/api-configuration', label: 'API Configuration', icon: KeyRound, adminOnly: true },
  { to: '/network', label: 'Network Status', icon: Network },
  { to: '/alerts', label: 'Maintenance Alerts', icon: Wrench, badge: 'alerts' },
  { to: '/rules', label: 'Violation Rules', icon: Gavel },
  { to: '/users', label: 'Users', icon: UsersIcon, adminOnly: true },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return (
    <span className="hidden font-mono text-xs text-slate-500 sm:inline">
      {now.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })}
    </span>
  )
}

export default function Layout() {
  const { user, isAdmin, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [office, setOffice] = useState({ rto_office_name: 'Regional Transport Office', rto_code: '' })
  const [openAlerts, setOpenAlerts] = useState(0)

  useEffect(() => setMenuOpen(false), [location.pathname])

  useEffect(() => {
    let cancelled = false
    api
      .get('/api/settings')
      .then(({ data }) => !cancelled && setOffice(data.settings))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = () =>
      api
        .get('/api/alerts', { params: { status: 'OPEN', limit: 1 } })
        .then(({ data }) => !cancelled && setOpenAlerts(data.summary.open))
        .catch(() => {})
    load()
    const timer = setInterval(load, 30000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const items = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)

  return (
    <div className="flex min-h-screen bg-slate-100">
      {/* ---------------- sidebar ---------------- */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-navy-900 transition-transform lg:static lg:translate-x-0 ${
          menuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">
            RTO
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">E-Challan System</p>
            <p className="truncate text-xs text-slate-400">AI Camera Enforcement</p>
          </div>
          <button
            type="button"
            className="ml-auto text-slate-400 lg:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {items.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
              }
            >
              <Icon size={17} className="shrink-0" />
              <span className="flex-1 truncate">{label}</span>
              {badge === 'alerts' && openAlerts > 0 && (
                <span className="rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {openAlerts}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/10 px-5 py-3">
          <p className="truncate text-xs text-slate-400">{office.rto_office_name}</p>
          <p className="text-xs text-slate-500">{office.rto_code}</p>
        </div>
      </aside>

      {menuOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
          onClick={() => setMenuOpen(false)}
          aria-hidden
        />
      )}

      {/* ---------------- main ---------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <button
            type="button"
            className="btn-ghost btn-sm lg:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-900">
              {office.rto_office_name}
              {office.rto_code ? ` · ${office.rto_code}` : ''}
            </p>
            <p className="truncate text-xs text-slate-500">
              AI Driven Camera Detected RTO E-Challan System
            </p>
          </div>

          <Clock />

          <Link
            to="/alerts"
            className="relative rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
            title="Maintenance alerts"
          >
            <BellRing size={18} />
            {openAlerts > 0 && (
              <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
                {openAlerts}
              </span>
            )}
          </Link>

          <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
              {(user?.name || '?').slice(0, 1).toUpperCase()}
            </span>
            <div className="hidden min-w-0 sm:block">
              <p className="truncate text-sm font-medium text-slate-800">{user?.name}</p>
              <p className="truncate text-xs text-slate-500">
                {user?.role_label} · {user?.user_id}
              </p>
            </div>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={logout}
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-4 sm:p-6">
          <Outlet />
        </main>

        <footer className="border-t border-slate-200 bg-white px-6 py-3 text-xs text-slate-500">
          AI Driven Camera Detected RTO E-Challan System · Final year project build ·
          Signed in as {user?.user_id}
        </footer>
      </div>
    </div>
  )
}

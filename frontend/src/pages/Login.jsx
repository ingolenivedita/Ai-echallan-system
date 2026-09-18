import { useEffect, useState } from 'react'
import {
  ArrowLeft,
  BadgeCheck,
  Camera,
  KeyRound,
  Loader2,
  LockKeyhole,
  ScanLine,
  ShieldCheck,
  Smartphone,
  UserRound,
} from 'lucide-react'
import api, { apiError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { ErrorNote, Field, InfoNote } from '../components/ui'

const ROLES = [
  { value: '', label: 'Any role' },
  { value: 'admin', label: 'Administrator' },
  { value: 'officer', label: 'Traffic Officer' },
]

const HIGHLIGHTS = [
  { icon: Camera, title: 'Multi camera monitoring', text: 'Two or three IP cameras processed at the same time, each independently.' },
  { icon: ScanLine, title: 'AI violation detection', text: 'No helmet, triple riding, wrong side driving and prohibited containers.' },
  { icon: BadgeCheck, title: 'Automatic e-challan', text: 'ANPR number plate reading, challan generation, SMS notice and online payment.' },
]

export default function Login() {
  const { login, requestOtp, verifyOtp, forgotPassword, resetPassword } = useAuth()
  const toast = useToast()

  const [mode, setMode] = useState('password')
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('')
  const [otp, setOtp] = useState('')
  const [otpInfo, setOtpInfo] = useState(null)
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [demoAccounts, setDemoAccounts] = useState([])

  useEffect(() => {
    api
      .get('/api/auth/demo-credentials')
      .then(({ data }) => setDemoAccounts(data.accounts || []))
      .catch(() => setDemoAccounts([]))
  }, [])

  const run = async (action, successMessage) => {
    setBusy(true)
    setError('')
    try {
      const result = await action()
      if (successMessage) toast.success(successMessage)
      return result
    } catch (requestError) {
      setError(apiError(requestError))
      return null
    } finally {
      setBusy(false)
    }
  }

  const submitPassword = (event) => {
    event.preventDefault()
    run(() => login({ userId: userId.trim(), password, role }), 'Signed in successfully')
  }

  const submitOtpRequest = (event) => {
    event.preventDefault()
    run(async () => {
      const info = await requestOtp(userId.trim())
      setOtpInfo(info)
      if (info.demo_otp) {
        toast.warning(`SMS API not configured - demo OTP is ${info.demo_otp}`, 12000)
      } else if (info.sent) {
        toast.success(info.message)
      } else {
        toast.error(info.message)
      }
      return info
    })
  }

  const submitOtpVerify = (event) => {
    event.preventDefault()
    run(() => verifyOtp(userId.trim(), otp.trim()), 'Signed in with OTP')
  }

  const submitForgot = (event) => {
    event.preventDefault()
    run(async () => {
      const info = await forgotPassword(userId.trim())
      if (info.reset_token) {
        setResetToken(info.reset_token)
        toast.info('Development build: reset token filled in automatically.')
      } else {
        toast.info(info.message)
      }
      return info
    })
  }

  const submitReset = (event) => {
    event.preventDefault()
    run(async () => {
      await resetPassword(resetToken.trim(), newPassword)
      toast.success('Password updated. Please sign in.')
      setMode('password')
      setPassword('')
      setNewPassword('')
      setResetToken('')
    })
  }

  const useDemo = (account) => {
    setMode('password')
    setUserId(account.user_id)
    setPassword(account.password)
    setRole(account.role)
    setError('')
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* ----------------- branding ----------------- */}
      <div className="relative hidden flex-col justify-between bg-navy-900 px-12 py-12 text-white lg:flex">
        <div>
          <div className="flex items-center gap-3">
            <span className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600 font-bold">
              RTO
            </span>
            <div>
              <p className="text-lg font-semibold leading-tight">Regional Transport Office</p>
              <p className="text-sm text-slate-400">Traffic Enforcement Portal</p>
            </div>
          </div>

          <h1 className="mt-14 max-w-xl text-3xl font-semibold leading-snug">
            AI Driven Camera Detected
            <span className="block text-brand-400">RTO E-Challan System</span>
          </h1>
          <p className="mt-4 max-w-lg text-sm leading-relaxed text-slate-300">
            Automated traffic violation detection from live IP cameras, with number plate
            recognition, e-challan generation, SMS notices and online fine payment.
          </p>

          <ul className="mt-10 space-y-5">
            {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/10">
                  <Icon size={18} />
                </span>
                <div>
                  <p className="text-sm font-semibold">{title}</p>
                  <p className="max-w-md text-sm text-slate-400">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-slate-500">
          Authorised personnel only. All actions are logged and audited.
        </p>
      </div>

      {/* ----------------- form ----------------- */}
      <div className="flex items-center justify-center bg-slate-100 px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600 font-bold text-white">
              RTO
            </span>
            <div>
              <p className="font-semibold text-slate-900">RTO E-Challan System</p>
              <p className="text-xs text-slate-500">AI Camera Enforcement Portal</p>
            </div>
          </div>

          <div className="card p-6 sm:p-7">
            <div className="mb-5">
              <h2 className="text-lg font-semibold text-slate-900">
                {mode === 'password' && 'Officer sign in'}
                {mode === 'otp' && 'Sign in with OTP'}
                {mode === 'forgot' && 'Reset your password'}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                {mode === 'password' && 'Enter your RTO User ID and password to continue.'}
                {mode === 'otp' && 'A one time password is sent to your registered mobile number.'}
                {mode === 'forgot' && 'We will verify your User ID and issue a reset token.'}
              </p>
            </div>

            {error && <div className="mb-4"><ErrorNote message={error} /></div>}

            {/* ---------- password login ---------- */}
            {mode === 'password' && (
              <form onSubmit={submitPassword} className="space-y-4">
                <Field label="User ID" required>
                  <div className="relative">
                    <UserRound
                      size={16}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />
                    <input
                      className="input pl-9"
                      value={userId}
                      onChange={(event) => setUserId(event.target.value)}
                      placeholder="ADMIN001"
                      autoComplete="username"
                      required
                    />
                  </div>
                </Field>

                <Field label="Password" required>
                  <div className="relative">
                    <LockKeyhole
                      size={16}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />
                    <input
                      className="input pl-9"
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="••••••••"
                      autoComplete="current-password"
                      required
                    />
                  </div>
                </Field>

                <Field label="Role">
                  <select
                    className="input"
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                  >
                    {ROLES.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <button type="submit" className="btn-primary w-full" disabled={busy}>
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
                  Login
                </button>

                <div className="flex items-center justify-between pt-1 text-sm">
                  <button
                    type="button"
                    className="font-medium text-brand-600 hover:text-brand-700"
                    onClick={() => {
                      setMode('otp')
                      setError('')
                    }}
                  >
                    <Smartphone size={14} className="mr-1 inline" />
                    OTP Login
                  </button>
                  <button
                    type="button"
                    className="font-medium text-slate-500 hover:text-slate-700"
                    onClick={() => {
                      setMode('forgot')
                      setError('')
                    }}
                  >
                    Forgot Password?
                  </button>
                </div>
              </form>
            )}

            {/* ---------- otp login ---------- */}
            {mode === 'otp' && (
              <div className="space-y-4">
                <form onSubmit={submitOtpRequest} className="space-y-4">
                  <Field label="User ID" required>
                    <input
                      className="input"
                      value={userId}
                      onChange={(event) => setUserId(event.target.value)}
                      placeholder="OFFICER001"
                      required
                    />
                  </Field>
                  <button type="submit" className="btn-secondary w-full" disabled={busy}>
                    {busy ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
                    {otpInfo ? 'Resend OTP' : 'Send OTP'}
                  </button>
                </form>

                {otpInfo && (
                  <>
                    <InfoNote tone={otpInfo.demo_mode ? 'amber' : 'sky'}>
                      {otpInfo.demo_mode ? (
                        <>
                          <strong>SMS API not configured.</strong> The OTP could not be delivered,
                          so it is shown here for the demo:{' '}
                          <span className="font-mono font-bold">{otpInfo.demo_otp}</span>
                        </>
                      ) : (
                        <>OTP sent to {otpInfo.masked_phone}. Valid for {otpInfo.valid_for_minutes} minutes.</>
                      )}
                    </InfoNote>

                    <form onSubmit={submitOtpVerify} className="space-y-4">
                      <Field label="Enter OTP" required>
                        <input
                          className="input text-center font-mono text-lg tracking-[0.4em]"
                          value={otp}
                          onChange={(event) => setOtp(event.target.value.replace(/\D/g, ''))}
                          maxLength={6}
                          placeholder="000000"
                          required
                        />
                      </Field>
                      <button type="submit" className="btn-primary w-full" disabled={busy}>
                        {busy ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
                        Verify and sign in
                      </button>
                    </form>
                  </>
                )}

                <button
                  type="button"
                  className="btn-ghost btn-sm w-full"
                  onClick={() => {
                    setMode('password')
                    setOtpInfo(null)
                    setError('')
                  }}
                >
                  <ArrowLeft size={14} /> Back to password login
                </button>
              </div>
            )}

            {/* ---------- forgot password ---------- */}
            {mode === 'forgot' && (
              <div className="space-y-4">
                <form onSubmit={submitForgot} className="space-y-4">
                  <Field label="User ID" required>
                    <input
                      className="input"
                      value={userId}
                      onChange={(event) => setUserId(event.target.value)}
                      placeholder="OFFICER001"
                      required
                    />
                  </Field>
                  <button type="submit" className="btn-secondary w-full" disabled={busy}>
                    {busy ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
                    Request reset token
                  </button>
                </form>

                <form onSubmit={submitReset} className="space-y-4">
                  <Field
                    label="Reset token"
                    hint="Development builds fill this in automatically."
                    required
                  >
                    <textarea
                      className="input h-20 font-mono text-xs"
                      value={resetToken}
                      onChange={(event) => setResetToken(event.target.value)}
                      required
                    />
                  </Field>
                  <Field label="New password" hint="Minimum 6 characters." required>
                    <input
                      className="input"
                      type="password"
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      minLength={6}
                      required
                    />
                  </Field>
                  <button type="submit" className="btn-primary w-full" disabled={busy}>
                    Set new password
                  </button>
                </form>

                <button
                  type="button"
                  className="btn-ghost btn-sm w-full"
                  onClick={() => {
                    setMode('password')
                    setError('')
                  }}
                >
                  <ArrowLeft size={14} /> Back to password login
                </button>
              </div>
            )}
          </div>

          {/* ---------- demo credentials ---------- */}
          {demoAccounts.length > 0 && (
            <div className="card mt-4 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Demo credentials (development build)
              </p>
              <div className="mt-3 space-y-2">
                {demoAccounts.map((account) => (
                  <button
                    key={account.user_id}
                    type="button"
                    onClick={() => useDemo(account)}
                    className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2 text-left transition hover:border-brand-300 hover:bg-brand-50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-800">
                        {account.user_id}
                        <span className="ml-2 font-mono text-xs text-slate-500">
                          {account.password}
                        </span>
                      </span>
                      <span className="block truncate text-xs text-slate-500">
                        {account.name} · {account.role_label}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-semibold text-brand-600">Use</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

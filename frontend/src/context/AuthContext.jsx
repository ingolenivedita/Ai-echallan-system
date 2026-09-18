import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api, { tokenStore } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => tokenStore.getUser())
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))

  const applySession = useCallback((data) => {
    tokenStore.set(data.access_token)
    tokenStore.setUser(data.user)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  // Validate a stored token on first paint so a stale session cannot linger.
  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false)
      return
    }
    let cancelled = false
    api
      .get('/api/auth/me')
      .then(({ data }) => {
        if (cancelled) return
        tokenStore.setUser(data)
        setUser(data)
      })
      .catch(() => {
        if (!cancelled) logout()
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [logout])

  useEffect(() => {
    const handler = () => logout()
    window.addEventListener('rto:session-expired', handler)
    return () => window.removeEventListener('rto:session-expired', handler)
  }, [logout])

  const value = useMemo(
    () => ({
      user,
      loading,
      isAdmin: user?.role === 'admin',
      isAuthenticated: Boolean(user),
      async login({ userId, password, role }) {
        const { data } = await api.post('/api/auth/login', {
          user_id: userId,
          password,
          role: role || null,
        })
        return applySession(data)
      },
      async requestOtp(userId) {
        const { data } = await api.post('/api/auth/otp/request', { user_id: userId })
        return data
      },
      async verifyOtp(userId, otp) {
        const { data } = await api.post('/api/auth/otp/verify', { user_id: userId, otp })
        return applySession(data)
      },
      async forgotPassword(userId) {
        const { data } = await api.post('/api/auth/forgot-password', { user_id: userId })
        return data
      },
      async resetPassword(token, newPassword) {
        const { data } = await api.post('/api/auth/reset-password', {
          token,
          new_password: newPassword,
        })
        return data
      },
      async changePassword(currentPassword, newPassword) {
        const { data } = await api.post('/api/auth/change-password', {
          current_password: currentPassword,
          new_password: newPassword,
        })
        return data
      },
      logout,
    }),
    [user, loading, applySession, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

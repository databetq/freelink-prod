import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authService, takeAuthReturnPath } from '@/services/auth/authService'
import { SESSION_ENDED_EVENT } from '@/services/api/apiClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authError, setAuthError] = useState(null)

  useEffect(() => {
    if (!user?.id) return undefined
    const sessionEnded = () => {
      setUser(null)
      setAuthError({
        code: 'SESSION_ENDED',
        message: 'เซสชันนี้ใช้ไม่ได้แล้ว กรุณาเข้าสู่ระบบใหม่',
      })
    }
    window.addEventListener(SESSION_ENDED_EVENT, sessionEnded)
    return () => window.removeEventListener(SESSION_ENDED_EVENT, sessionEnded)
  }, [user?.id])

  useEffect(() => {
    const controller = new AbortController()
    async function loadUser() {
      try {
        const currentUser = await authService.fetchCurrentUser({ signal: controller.signal })
        if (controller.signal.aborted) return
        setUser(currentUser)
        const returnTo = takeAuthReturnPath(currentUser)
        if (returnTo) navigate(returnTo, { replace: true })
      } catch (error) {
        if (!controller.signal.aborted && error.status !== 401) setAuthError(error)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    loadUser()
    return () => controller.abort()
    // Restore the cookie session once on mount, including after the OAuth redirect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const signOut = useCallback(async () => {
    await authService.signOut()
    setUser(null)
  }, [])

  const signInAdmin = useCallback(async (username, password) => {
    const currentUser = await authService.signInAdmin(username, password)
    setAuthError(null)
    setUser(currentUser)
  }, [])

  const signInPassword = useCallback(async (email, password) => {
    const currentUser = await authService.signInPassword(email, password)
    setAuthError(null)
    setUser(currentUser)
  }, [])

  const registerPassword = useCallback(async (account) => {
    const currentUser = await authService.registerPassword(account)
    setAuthError(null)
    setUser(currentUser)
  }, [])

  const updateUser = useCallback((patch) => {
    setUser((current) => current && { ...current, ...patch })
  }, [])

  const value = useMemo(() => ({
    user,
    isAuthenticated: Boolean(user),
    role: user?.role || null,
    profileId: user?.profileId || null,
    loading,
    authError,
    signInWithGoogle: authService.signInWithGoogle,
    signInAdmin,
    signInPassword,
    registerPassword,
    signOut,
    updateUser,
  }), [user, loading, authError, signOut, signInAdmin, signInPassword, registerPassword, updateUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}

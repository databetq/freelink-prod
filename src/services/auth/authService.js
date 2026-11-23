import { authApi } from '@/services/api/authService'

const RETURN_KEY = 'freelink.auth.returnTo'

export function dashboardForRole(role) {
  if (role === 'admin') return '/admin'
  return role === 'client' ? '/client/dashboard' : '/freelancer/dashboard'
}

export function resolveAuthReturnPath(user, path) {
  const fallback = dashboardForRole(user.role)
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return fallback
  const url = new URL(path, window.location.origin)
  const [section] = url.pathname.split('/').filter(Boolean)
  if (['client', 'freelancer', 'admin'].includes(section) && section !== user.role) return fallback
  return url.origin === window.location.origin ? path : fallback
}

export function takeAuthReturnPath(user) {
  const path = window.sessionStorage.getItem(RETURN_KEY)
  window.sessionStorage.removeItem(RETURN_KEY)
  return path === null ? null : resolveAuthReturnPath(user, path)
}

export const authService = {
  fetchCurrentUser: authApi.fetchCurrentUser,
  signInAdmin: authApi.signInAdmin,
  signInPassword: authApi.signInPassword,
  registerPassword: authApi.registerPassword,
  signOut: authApi.signOut,

  signInWithGoogle(role, returnTo = '') {
    const url = authApi.getGoogleAuthUrl(role)
    window.sessionStorage.setItem(RETURN_KEY, returnTo)
    window.location.assign(url)
  },
}

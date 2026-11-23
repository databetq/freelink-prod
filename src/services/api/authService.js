import { appConfig } from '@/config/appConfig'
import { advanceSessionVersion, apiClient, assertApiConfigured } from './apiClient'
import { endpoints } from './endpoints'

async function startSession(path, credentials) {
  assertApiConfigured()
  await apiClient.post(path, credentials)
  advanceSessionVersion()
  return authApi.fetchCurrentUser()
}

export const authApi = {
  signInAdmin: (username, password) => startSession('/auth/admin/login', { username, password }),
  signInPassword: (email, password) => startSession('/auth/login', { email, password }),
  registerPassword: (account) => startSession('/auth/register', account),

  async fetchCurrentUser({ signal } = {}) {
    assertApiConfigured()
    const { data } = await apiClient.get(endpoints.auth.me, { signal })
    return data
  },

  async signOut() {
    assertApiConfigured()
    await apiClient.post(endpoints.auth.logout)
    advanceSessionVersion()
  },

  async listWarnings() {
    assertApiConfigured()
    const { data } = await apiClient.get('/auth/warnings')
    return data
  },

  getGoogleAuthUrl(role) {
    assertApiConfigured()
    const base = appConfig.apiBaseUrl.replace(/\/+$/, '')
    const url = new URL(`${base}${endpoints.auth.google}`, window.location.origin)
    if (role) url.searchParams.set('role', role)
    return url.toString()
  },
}

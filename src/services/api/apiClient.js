import axios from 'axios'
import { appConfig } from '@/config/appConfig'

export const SESSION_ENDED_EVENT = 'freelink:session-ended'
let sessionVersion = 0

export function advanceSessionVersion() {
  sessionVersion += 1
}

export class ApiNotConfiguredError extends Error {
  constructor(message = 'ยังไม่ได้ตั้งค่า VITE_API_BASE_URL — Frontend ยังไม่เชื่อมต่อ Backend') {
    super(message)
    this.name = 'ApiNotConfiguredError'
    this.code = 'API_NOT_CONFIGURED'
  }
}

export const apiClient = axios.create({
  baseURL: appConfig.apiBaseUrl || '',
  timeout: 20000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  config.freelinkSessionVersion = sessionVersion
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? null
    const payload = error.response?.data
    if (
      typeof window !== 'undefined' && status === 401 && payload?.code === 'LOGIN_REQUIRED' &&
      error.config?.freelinkSessionVersion === sessionVersion
    ) {
      window.dispatchEvent(new Event(SESSION_ENDED_EVENT))
    }
    const routeMissing = status === 405 ||
      (status === 404 && (payload?.code === 'HTTP_404' || payload?.detail === 'Not Found'))
    const message = (routeMissing ? 'ฟีเจอร์นี้ยังไม่พร้อมใช้งานบนเซิร์ฟเวอร์' : payload?.message) ||
      (status ? `คำขอไม่สำเร็จ (HTTP ${status})` : 'เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ')
    return Promise.reject({
      message,
      status,
      code: routeMissing ? 'API_ENDPOINT_UNAVAILABLE' : payload?.code || error.code || 'NETWORK_ERROR',
      details: payload?.errors || null,
      isApiError: true,
    })
  },
)

/** Call this at the start of every real-API service method. */
export function assertApiConfigured() {
  if (!appConfig.apiBaseUrl) throw new ApiNotConfiguredError()
}

export function getErrorMessage(error, fallback = 'เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง') {
  if (!error) return fallback
  return error.message || error.reason || fallback
}

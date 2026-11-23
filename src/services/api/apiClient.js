import axios from 'axios'
import { appConfig } from '@/config/appConfig'

export const SESSION_ENDED_EVENT = 'freelink:session-ended'
export const SERVER_SLOW_EVENT = 'freelink:server-slow'
const SLOW_REQUEST_MS = 4000
let sessionVersion = 0
let slowRequests = 0

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
  timeout: 90000, // The demo server sleeps when idle and needs about a minute to start.
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

function changeSlowRequests(amount) {
  slowRequests += amount
  window.dispatchEvent(new CustomEvent(SERVER_SLOW_EVENT, { detail: slowRequests > 0 }))
}

function settleRequest(config) {
  if (!config?.freelinkSlow) return
  clearTimeout(config.freelinkSlow.timer)
  if (config.freelinkSlow.reported) changeSlowRequests(-1)
  config.freelinkSlow = null
}

apiClient.interceptors.request.use((config) => {
  config.freelinkSessionVersion = sessionVersion
  if (typeof window !== 'undefined') {
    const slow = { reported: false }
    slow.timer = setTimeout(() => {
      slow.reported = true
      changeSlowRequests(1)
    }, SLOW_REQUEST_MS)
    config.freelinkSlow = slow
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => {
    settleRequest(response.config)
    // A host's "starting up" page arrives as a successful HTML reply, which is never API data.
    if (String(response.headers?.['content-type'] || '').includes('text/html')) {
      return Promise.reject({
        message: 'เซิร์ฟเวอร์กำลังเริ่มทำงาน กรุณารอสักครู่แล้วลองใหม่',
        status: null, code: 'SERVER_STARTING', details: null, isApiError: true,
      })
    }
    return response
  },
  (error) => {
    settleRequest(error.config)
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

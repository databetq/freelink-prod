import { createContext, useCallback, useContext, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useAsync } from '@/hooks/useAsync'
import { notificationService } from '@/services/api/notificationService'

const NotificationContext = createContext(null)
const emptyItems = []

export function NotificationProvider({ children }) {
  const { user } = useAuth()
  return <NotificationState key={user?.id} role={user?.role}>{children}</NotificationState>
}

function NotificationState({ role, children }) {
  const { pathname } = useLocation()
  const atNotifications = pathname === '/notifications'
  const readIds = useRef(new Set())
  const list = useCallback(async () => {
    const items = await notificationService.list(role)
    return items.map((item) => readIds.current.has(item.id) ? { ...item, read: true } : item)
  }, [role])
  const { data, loading, error, refresh, setData } = useAsync(list, [role, atNotifications], { immediate: Boolean(role) })

  useEffect(() => {
    if (!role || role === 'admin') return undefined
    let active = true
    let pending = false

    const check = async () => {
      if (pending || document.hidden) return
      pending = true
      try {
        const latest = await list()
        if (active) setData(latest)
      } catch {
        // Keep the last successful list during a background connection failure.
      } finally {
        pending = false
      }
    }

    const timer = window.setInterval(check, 45000)
    window.addEventListener('focus', check)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', check)
    }
  }, [list, role, setData])

  const items = data || emptyItems
  const unread = items.filter((item) => !item.read).length

  const markRead = async (notification) => {
    if (notification.read) return
    const updated = await notificationService.markRead(notification.id)
    readIds.current.add(updated.id)
    setData((current) => current?.map((item) => item.id === updated.id ? updated : item))
  }

  const markAllRead = async () => {
    const ids = new Set(items.filter((item) => !item.read).map((item) => item.id))
    await notificationService.markAllRead(role)
    for (const id of ids) readIds.current.add(id)
    setData((current) => current?.map((item) => ids.has(item.id) ? { ...item, read: true } : item))
  }

  return (
    <NotificationContext.Provider value={{ items, unread, loading, error, refresh, markRead, markAllRead }}>
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications() {
  return useContext(NotificationContext)
}

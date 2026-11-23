import { useEffect, useState } from 'react'
import { SERVER_SLOW_EVENT } from '@/services/api/apiClient'

/** Explains a long wait while the demo server starts up. */
export function ServerStatusNotice() {
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    const update = (event) => setSlow(event.detail)
    window.addEventListener(SERVER_SLOW_EVENT, update)
    return () => window.removeEventListener(SERVER_SLOW_EVENT, update)
  }, [])

  return (
    <div role="status" className="pointer-events-none fixed inset-x-4 top-4 z-[120] flex justify-center">
      {slow && (
        <p className="rounded-full border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-semibold text-ink shadow-lift">
          เซิร์ฟเวอร์เดโมกำลังเริ่มทำงาน ครั้งแรกอาจใช้เวลาราว 1 นาที
        </p>
      )}
    </div>
  )
}

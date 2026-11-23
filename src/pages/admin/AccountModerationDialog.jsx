import { useCallback, useState } from 'react'
import { Button } from '@/components/common/Button'
import { ErrorState } from '@/components/common/ErrorState'
import { Select, Textarea } from '@/components/common/FormField'
import { Modal } from '@/components/common/Modal'
import { useToast } from '@/contexts/ToastContext'
import { useAsync } from '@/hooks/useAsync'
import { adminService } from '@/services/api/adminService'
import { formatDate } from '@/utils/format'

function historyLabel(entry) {
  if (entry.kind === 'warning') return 'คำเตือนถึงผู้ใช้'
  if (entry.kind === 'flag') return 'Flag ภายในทีม'
  return entry.newStatus === 'suspended' ? 'ระงับบัญชี' : 'คืนสถานะบัญชี'
}

export function AccountModerationDialog({ user, onClose, onUserUpdated }) {
  const toast = useToast()
  const [action, setAction] = useState('status')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const { data, loading, error, refresh } = useAsync(() => adminService.getModerationHistory(user.id), [user.id])
  const statusLabel = user.status === 'active' ? 'ระงับบัญชี' : 'คืนสถานะบัญชี'
  const close = useCallback(() => {
    if (!busy) onClose()
  }, [busy, onClose])

  async function save(event) {
    event.preventDefault()
    if (!reason.trim() || busy) return
    setBusy(true)
    try {
      if (action === 'status') {
        const updated = await adminService.updateUserStatus(
          user.id, user.status === 'active' ? 'suspended' : 'active', reason.trim(),
        )
        onUserUpdated(updated)
      } else {
        await adminService.addNotice(user.id, action, reason.trim())
      }
      setReason('')
      toast.success('บันทึกการจัดการแล้ว')
      await refresh()
    } catch (failure) {
      toast.error('บันทึกไม่สำเร็จ', failure.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={close} title="จัดการบัญชี" description={user.name}>
      <form onSubmit={save} className="space-y-4">
        <Select label="การดำเนินการ" value={action} disabled={busy}
          onChange={(event) => {
            setAction(event.target.value)
            setReason('')
          }}>
          <option value="status">{statusLabel}</option>
          <option value="warning">ส่งคำเตือนถึงผู้ใช้</option>
          <option value="flag">ติด Flag ภายในทีม</option>
        </Select>
        <Textarea label="เหตุผล" value={reason} maxLength={500} required disabled={busy}
          hint={action === 'warning' ? 'ผู้ใช้จะเห็นข้อความนี้ในแดชบอร์ด' : 'เหตุผลนี้แสดงเฉพาะแอดมิน'}
          onChange={(event) => setReason(event.target.value)} />
        <div className="flex justify-end">
          <Button type="submit" variant={action === 'status' && user.status === 'active' ? 'danger' : 'brand'}
            disabled={!reason.trim()} loading={busy}>
            {action === 'status' ? statusLabel : action === 'warning' ? 'ส่งคำเตือน' : 'บันทึก Flag'}
          </Button>
        </div>
      </form>

      <section className="mt-6 border-t border-ink/10 pt-4">
        <h3 className="text-sm font-semibold">ประวัติการจัดการ</h3>
        {loading && <p className="mt-2 text-xs text-ink-500">กำลังโหลดประวัติ…</p>}
        {error && <ErrorState error={error} onRetry={refresh} className="mt-2" />}
        {!loading && !error && data?.length === 0 && (
          <p className="mt-2 text-xs text-ink-500">ยังไม่มีประวัติการจัดการบัญชีนี้</p>
        )}
        {!error && (
          <ul className="mt-2 divide-y divide-ink/10">
            {data?.map((entry) => (
              <li key={entry.id} className="py-2 text-xs">
                <p className="font-semibold">{historyLabel(entry)}</p>
                <p className="whitespace-pre-wrap break-words">{entry.reason}</p>
                <p className="text-ink-500">{entry.actorName} · {formatDate(entry.createdAt)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Modal>
  )
}

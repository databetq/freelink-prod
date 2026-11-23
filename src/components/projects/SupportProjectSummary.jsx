import { Button } from '@/components/common/Button'
import { ErrorState } from '@/components/common/ErrorState'
import { StatusBadge } from '@/components/common/StatusBadge'
import { projectStatus } from '@/constants'
import { useAsync } from '@/hooks/useAsync'
import { adminService } from '@/services/api/adminService'
import { formatCurrency, formatDate } from '@/utils/format'

const payments = {
  unprepared: 'ยังไม่ได้เตรียม Escrow',
  prepared: 'รอฝากเงิน',
  pending_verification: 'มีธุรกรรมรอตรวจสอบ',
  funded: 'ยืนยันเงินฝากแล้ว',
  released: 'จ่ายแล้ว',
  refunded: 'คืนเงินแล้ว',
  resolved: 'ข้อพิพาทสิ้นสุดแล้ว',
  expired: 'ข้อตกลงหมดอายุ',
}

const submissions = {
  pending: 'รอตรวจรับ',
  revision: 'ขอแก้ไข',
  approved: 'อนุมัติแล้ว',
}

export function SupportProjectSummary({ reportId }) {
  const { data, loading, error, refresh } = useAsync(() => adminService.getReportProject(reportId), [reportId], { immediate: false })

  return (
    <section className="card mb-5 p-5" aria-label="สถานะโครงการ">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-bold">สถานะโครงการ</h2>
        <Button size="sm" variant="secondary" loading={loading} onClick={() => refresh()}>
          {data ? 'โหลดสถานะล่าสุด' : 'ดูสถานะโครงการ'}
        </Button>
      </div>
      {error ? <ErrorState error={error} /> : data && (
        <div className="mt-4 space-y-3" aria-live="polite">
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink-600">
            <StatusBadge {...projectStatus[data.status]} />
            <span>กำหนดส่งโครงการ {formatDate(data.dueDate)}</span>
          </div>
          <ul className="space-y-2">
            {data.milestones.map((item) => (
              <li key={item.number} className="rounded-xl bg-paper-soft p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-1 font-semibold">
                  <span className="break-words">งวด {item.number} · {item.title}</span>
                  <span>{formatCurrency(item.amountThb)}</span>
                </div>
                <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                  <div><dt className="text-ink-500">Escrow</dt><dd className="mt-1 font-semibold">{payments[item.escrowStatus]}</dd></div>
                  <div>
                    <dt className="text-ink-500">การส่งมอบล่าสุด</dt>
                    <dd className="mt-1 font-semibold">{item.submissionStatus ? submissions[item.submissionStatus] : 'ยังไม่มีงานส่ง'}</dd>
                    {item.submittedAt && <dd className="mt-1 text-ink-500">ส่งเมื่อ {formatDate(item.submittedAt, { hour: '2-digit', minute: '2-digit' })}</dd>}
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

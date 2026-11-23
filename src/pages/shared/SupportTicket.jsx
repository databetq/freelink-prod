import { useState } from 'react'
import { Send } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/common/Button'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { Textarea } from '@/components/common/FormField'
import { InfoBanner } from '@/components/common/InfoBanner'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { SupportProjectSummary } from '@/components/projects/SupportProjectSummary'
import { supportStatuses, supportTopics } from '@/constants/support'
import { useToast } from '@/contexts/ToastContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { adminService } from '@/services/api/adminService'
import { supportService } from '@/services/api/supportService'
import { formatDate } from '@/utils/format'

function TicketMessage({ label, timestamp, body, fromAdmin }) {
  return (
    <li className={fromAdmin ? 'rounded-xl bg-brand-50 p-4' : 'rounded-xl bg-paper-soft p-4'}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{label}</span>
        <time dateTime={timestamp} className="text-xs text-ink-500">
          {formatDate(timestamp, { hour: '2-digit', minute: '2-digit' })}
        </time>
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-700">{body}</p>
    </li>
  )
}

export default function SupportTicket({ admin = false }) {
  const { reportId } = useParams()
  useDocumentTitle('รายละเอียดเรื่องที่แจ้ง')
  return <TicketThread key={reportId} reportId={reportId} admin={admin} />
}

function TicketThread({ reportId, admin }) {
  const { data: report, loading, error, refresh, setData } = useAsync(() => supportService.getReport(reportId), [reportId])
  const toast = useToast()
  const [body, setBody] = useState('')
  const [waitForReporter, setWaitForReporter] = useState(false)
  const [busy, setBusy] = useState(null)
  const [confirmClose, setConfirmClose] = useState(false)

  if (loading) return <PageLoader />
  if (error || !report) return <ErrorState error={error} onRetry={refresh} />

  const closed = report.status === 'resolved'
  const reporterLabel = admin ? report.reporter : 'คุณ'

  const sendReply = async (event) => {
    event.preventDefault()
    if (!body.trim() || busy || closed) return
    setBusy('reply')
    try {
      setData(await supportService.reply(report.id, { body: body.trim(), waitForReporter }))
      setBody('')
      setWaitForReporter(false)
    } catch (err) {
      toast.error('ส่งข้อความไม่สำเร็จ', err.message)
      if (err.code === 'REPORT_CLOSED') refresh()
    } finally {
      setBusy(null)
    }
  }

  const closeTicket = async () => {
    if (busy) return
    setBusy('close')
    try {
      setData(await adminService.resolveReport(report.id, 'resolved'))
      setConfirmClose(false)
      toast.success('ปิดรายงานแล้ว')
    } catch (err) {
      toast.error('ปิดรายงานไม่สำเร็จ', err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={`${supportTopics[report.topic]}${report.target ? ` · ${report.target}` : ''}`}
        backTo={admin ? '/admin/reports' : '/support/tickets'}
        backLabel={admin ? 'กลับไปรายงานปัญหา' : 'กลับไปเรื่องที่แจ้ง'}
        actions={<StatusBadge {...supportStatuses[report.status]} />}
      />

      {admin && report.projectId && !closed && <SupportProjectSummary reportId={report.id} />}

      <section className="card p-5">
        <div className="mb-4 space-y-1 text-xs text-ink-500">
          <p className="break-all">เลขอ้างอิง {report.id}</p>
          {admin && <p className="break-all">ผู้แจ้ง {report.reporter} ({report.contact})</p>}
        </div>
        <ol className="space-y-3">
          <TicketMessage label={reporterLabel} timestamp={report.createdAt} body={report.reason} />
          {report.messages.map((message) => (
            <TicketMessage key={message.id} label={message.fromAdmin ? 'ทีม Freelink' : reporterLabel}
              timestamp={message.createdAt} body={message.body} fromAdmin={message.fromAdmin} />
          ))}
        </ol>

        {closed ? <InfoBanner className="mt-5" title="เรื่องนี้ปิดแล้ว" /> : (
          <form onSubmit={sendReply} className="mt-5 space-y-3">
            <Textarea label="ตอบกลับ" value={body} onChange={(event) => setBody(event.target.value)}
              rows={4} maxLength={5000} disabled={Boolean(busy)} required />
            {admin && (
              <label className="flex items-center gap-2 text-sm text-ink-700">
                <input type="checkbox" checked={waitForReporter} onChange={(event) => setWaitForReporter(event.target.checked)} disabled={Boolean(busy)} />
                รอข้อมูลเพิ่มเติมจากผู้แจ้ง
              </label>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              {admin && <Button variant="secondary" onClick={() => setConfirmClose(true)} disabled={Boolean(busy)}>ปิดรายงาน</Button>}
              <Button type="submit" variant="brand" icon={Send} loading={busy === 'reply'} disabled={!body.trim() || Boolean(busy)}>
                ส่งข้อความ
              </Button>
            </div>
          </form>
        )}
      </section>

      {admin && <ConfirmDialog open={confirmClose} onClose={() => setConfirmClose(false)} onConfirm={closeTicket}
        loading={busy === 'close'} title="ปิดรายงานนี้?" description="ผู้แจ้งจะได้รับแจ้งเตือนและยังเปิดดูประวัติการสนทนาได้"
        confirmLabel="ปิดรายงาน" />}
    </div>
  )
}

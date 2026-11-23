import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  Wallet,
} from 'lucide-react'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useToast } from '@/contexts/ToastContext'
import { projectService } from '@/services/api/projectService'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/common/Button'
import { Avatar } from '@/components/common/Avatar'
import { StatusBadge } from '@/components/common/StatusBadge'
import { RatingStars } from '@/components/common/RatingStars'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { Modal } from '@/components/common/Modal'
import { Textarea } from '@/components/common/FormField'
import { InfoBanner } from '@/components/common/InfoBanner'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { WorkAttachments } from '@/components/projects/WorkAttachments'
import { WorkLinks } from '@/components/projects/WorkLinks'
import { escrowStatus, projectStatus } from '@/constants'
import { formatCurrency, formatDate, timeAgo } from '@/utils/format'

export default function ReviewWork() {
  const { projectId } = useParams()
  const { profileId } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const { data: project, loading, error, refresh } = useAsync(
    () => projectService.getProject(projectId),
    [projectId],
  )
  useDocumentTitle(project ? `ตรวจรับงาน — ${project.title}` : 'ตรวจรับงาน')

  const [confirmApprove, setConfirmApprove] = useState(false)
  const [revisionOpen, setRevisionOpen] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [feedbackError, setFeedbackError] = useState('')
  const [revisionItems, setRevisionItems] = useState([])
  const [busy, setBusy] = useState(false)

  if (loading) return <PageLoader />
  if (error || !project) return <ErrorState error={error} onRetry={refresh} />

  if (project.clientId !== profileId) {
    return (
      <EmptyState
        title="คุณไม่มีสิทธิ์ตรวจรับโครงการนี้"
        description="โครงการนี้เป็นของบัญชีลูกค้าอื่น"
        action={
          <Button to="/client/projects" variant="primary">
            กลับไปโครงการของฉัน
          </Button>
        }
      />
    )
  }

  const submission = project.submissions?.[0]
  const checklist = submission?.checklist ?? []
  const milestone = project.milestones?.find((item) => item.id === submission?.milestoneNumber)
  const canReview = project.status === 'in_review' && submission?.status === 'pending'
  const hasRevisionLimit = Number.isInteger(submission?.revisionLimit) && Number.isInteger(submission?.revisionsUsed)
  const canRequestRevision = canReview && hasRevisionLimit && submission.revisionsUsed < submission.revisionLimit
  const status = projectStatus[project.status]
  const escrow = escrowStatus[project.escrowStatus]

  if (!submission) {
    return (
      <div>
        <PageHeader
          title="ยังไม่มีงานส่งตรวจรับ"
          backTo={`/client/projects/${project.id}`}
          backLabel="กลับไปโครงการ"
        />
        <EmptyState
          icon={FileText}
          title="ฟรีแลนซ์ยังไม่ได้ส่งงาน"
          description="เมื่อมีการส่งงาน คุณจะเห็นรายละเอียด ไฟล์ และลิงก์สำหรับตรวจรับในหน้านี้"
          action={
            <Button to={`/client/projects/${project.id}`} variant="secondary">
              ไปที่โครงการ
            </Button>
          }
        />
      </div>
    )
  }

  const approve = async () => {
    setBusy(true)
    try {
      await projectService.approveSubmission(project.id, submission.id)
      toast.success(
        'อนุมัติงานแล้ว',
        'ไปที่ Escrow เพื่อปล่อยเงินงวดนี้',
      )
      setConfirmApprove(false)
      navigate(`/client/projects/${project.id}/escrow`)
    } catch (err) {
      toast.error('อนุมัติไม่สำเร็จ', err.message)
    } finally {
      setBusy(false)
    }
  }

  const requestRevision = async () => {
    if (!canRequestRevision || busy) return
    const details = feedback.trim()
    if (details.length < 10) {
      setFeedbackError('กรุณาอธิบายสิ่งที่ต้องแก้ไขอย่างน้อย 10 ตัวอักษร')
      return
    }
    const selected = checklist.filter((_, index) => revisionItems.includes(index))
    const message = selected.length ? `รายการที่ยังไม่ผ่าน\n${selected.map((item) => `- ${item}`).join('\n')}\n\n${details}` : details
    if (message.length > 5000) {
      setFeedbackError('รายการที่เลือกและรายละเอียดรวมกันต้องไม่เกิน 5,000 ตัวอักษร')
      return
    }
    setBusy(true)
    try {
      await projectService.requestRevision(project.id, submission.id, message)
      toast.success('ส่งคำขอแก้ไขแล้ว', 'ฟรีแลนซ์จะเห็นข้อเสนอแนะในหน้าโครงการ')
      setRevisionOpen(false)
      setFeedback('')
      setRevisionItems([])
      navigate(`/client/projects/${project.id}`)
    } catch (err) {
      toast.error('ส่งคำขอแก้ไขไม่สำเร็จ', err.message)
      if (err.code === 'WORK_REVISION_LIMIT_REACHED') {
        setRevisionOpen(false)
        refresh()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Review submission"
        title="ตรวจรับงาน"
        description={project.title}
        backTo={`/client/projects/${project.id}`}
        backLabel="กลับไปรายละเอียดโครงการ"
        actions={
          <>
            <StatusBadge label={status?.label} tone={status?.tone} />
            <StatusBadge label={escrow?.label} tone={escrow?.tone} />
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink/[0.06] bg-paper-soft/60 px-5 py-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                  Submission
                </p>
                <h2 className="mt-1 text-base font-bold text-ink">{submission.title}</h2>
                <p className="mt-0.5 text-[11px] text-ink-500">ส่งเมื่อ {timeAgo(submission.submittedAt)}</p>
              </div>
              <StatusBadge
                tone={submission.status === 'approved' ? 'emerald' : submission.status === 'revision' ? 'rose' : 'amber'}
                label={
                  submission.status === 'approved'
                    ? 'อนุมัติแล้ว'
                    : submission.status === 'revision'
                      ? 'ขอแก้ไข'
                      : 'รอตรวจรับ'
                }
              />
            </div>

            <div className="p-5">
              <p className="whitespace-pre-line text-[13px] leading-[1.85] text-ink-600">
                {submission.description}
              </p>

              <WorkLinks submission={submission} />

              <WorkAttachments projectId={project.id} files={submission.files} />

              {submission.feedback && (
                <div className="mt-4 rounded-xl border border-ink/[0.07] bg-paper px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    Feedback ล่าสุด
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-ink-600">{submission.feedback}</p>
                </div>
              )}
            </div>
          </section>

          <section className="card p-5">
            <h2 className="text-sm font-bold">รายการตรวจรับ{milestone && ` งวด ${milestone.id} · ${milestone.title}`}</h2>
            {checklist.length > 0 ? (
              <ul className="mt-3 list-disc space-y-2 break-words pl-5 text-[12px] leading-relaxed text-ink-600">
                {checklist.map((item, index) => <li key={index}>{item}</li>)}
              </ul>
            ) : <p className="mt-2 text-xs text-ink-600">ตรวจงานจากขอบเขตที่ตกลงกันและไฟล์หรือลิงก์ของงานที่ส่ง</p>}
          </section>

          {canReview && <section className="card p-5">
            <h2 className="text-sm font-bold">การตัดสินใจ</h2>
            {hasRevisionLimit && (
              <p className="mt-2 text-sm text-ink-600">
                ขอแก้ไปแล้ว {submission.revisionsUsed} จาก {submission.revisionLimit} รอบตามข้อตกลง
              </p>
            )}
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Button
                variant="brand"
                size="md"
                icon={CheckCircle2}
                onClick={() => setConfirmApprove(true)}
                className="w-full"
              >
                อนุมัติงาน
              </Button>
              <Button
                variant="secondary"
                size="md"
                icon={RotateCcw}
                disabled={!canRequestRevision}
                onClick={() => setRevisionOpen(true)}
                className="w-full"
              >
                ขอแก้ไขงาน
              </Button>
            </div>
            {!canRequestRevision && hasRevisionLimit && (
              <div className="mt-3">
                <InfoBanner tone="warning">หากงานยังไม่ผ่านรายการตรวจรับ คุณสามารถแจ้งทีมให้ตรวจหลักฐานได้</InfoBanner>
                <Button to={`/help?projectId=${project.id}#contact`} variant="ghost" size="sm" className="mt-2">
                  แจ้งปัญหาโครงการ
                </Button>
              </div>
            )}
          </section>}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-[88px] lg:self-start">
          <div className="card p-5">
            <h2 className="text-sm font-bold">สรุปโครงการ</h2>
            <div className="mt-3 flex items-center gap-2.5">
              <Avatar
                name={project.freelancer?.name || 'Freelancer'}
                color={project.freelancer?.avatarColor}
                size="md"
              />
              <div className="min-w-0">
                <p className="truncate text-xs font-bold text-ink">{project.freelancer?.name}</p>
                <p className="truncate text-[10.5px] text-ink-500">{project.freelancer?.title}</p>
                <RatingStars rating={project.freelancer?.rating || 0} size="xs" showValue />
              </div>
            </div>
            <div className="mt-4 space-y-2.5 border-t border-ink/[0.07] pt-4 text-[11.5px]">
              <div className="flex items-center justify-between">
                <span className="text-ink-500">มูลค่าโครงการ</span>
                <span className="font-bold text-ink">{formatCurrency(project.budget)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">เงินใน Escrow</span>
                <span className="font-semibold text-emerald-600">
                  {formatCurrency(project.escrowStatus === 'funded' ? project.escrowAmount : 0)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">กำหนดส่ง</span>
                <span className="font-semibold text-ink">{formatDate(milestone ? milestone.dueDate : project.dueDate)}</span>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              <Button to={`/client/projects/${project.id}/escrow`} variant="secondary" size="sm" className="w-full" icon={Wallet}>
                ดูสถานะ Escrow
              </Button>
              <Button to="/messages" variant="ghost" size="sm" className="w-full" icon={MessageSquare}>
                คุยกับฟรีแลนซ์
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-ink/[0.07] bg-white px-3.5 py-3 text-[10.5px] text-ink-500">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            Escrow release ต้องยืนยันจาก Smart Contract
          </div>
        </aside>
      </div>

      <ConfirmDialog
        open={confirmApprove}
        onClose={() => setConfirmApprove(false)}
        onConfirm={approve}
        loading={busy}
        title="อนุมัติงานงวดนี้?"
        description="ยืนยันผลการตรวจรับงาน แล้วไปที่หน้า Escrow เพื่อดำเนินการจ่ายเงิน"
        confirmLabel="อนุมัติงาน"
        tone="brand"
      />

      <Modal
        open={revisionOpen}
        onClose={() => setRevisionOpen(false)}
        title="ขอแก้ไขงาน"
        description="อธิบายสิ่งที่ต้องแก้ไขให้ชัดเจน ฟรีแลนซ์จะเห็นข้อความนี้ในหน้าโครงการ"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRevisionOpen(false)} disabled={busy}>
              ยกเลิก
            </Button>
            <Button variant="brand" onClick={requestRevision} loading={busy}>
              ส่งคำขอแก้ไข
            </Button>
          </>
        }
      >
        {checklist.length > 0 && (
          <fieldset className="mb-4 space-y-2 text-sm">
            <legend className="mb-2 font-semibold">เลือกข้อที่ยังไม่ผ่าน (ถ้ามี)</legend>
            {checklist.map((item, index) => (
              <label key={index} className="flex items-start gap-2 break-words">
                <input type="checkbox" className="mt-1" checked={revisionItems.includes(index)} onChange={(event) => {
                  const checked = event.target.checked
                  setRevisionItems((items) => checked ? [...items, index] : items.filter((value) => value !== index))
                  setFeedbackError('')
                }} />
                <span>{item}</span>
              </label>
            ))}
          </fieldset>
        )}
        <Textarea
          label="รายละเอียดที่ต้องแก้ไข"
          rows={5}
          maxLength={5000}
          value={feedback}
          onChange={(event) => {
            setFeedback(event.target.value)
            setFeedbackError('')
          }}
          error={feedbackError}
          placeholder="เช่น กรุณาปรับ responsive ของตารางในหน้า dashboard ให้ใช้งานบน tablet ได้..."
          required
        />
      </Modal>
    </div>
  )
}

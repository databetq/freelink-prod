import { useEffect, useState } from 'react'
import { CheckCircle2, History, Star, Wallet } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { projectService } from '@/services/api/projectService'
import { PageHeader } from '@/components/common/PageHeader'
import { StatCard } from '@/components/common/StatCard'
import { Avatar } from '@/components/common/Avatar'
import { Button } from '@/components/common/Button'
import { StatusBadge } from '@/components/common/StatusBadge'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { TableSkeleton } from '@/components/common/LoadingSkeleton'
import { FreelancerReviewDialog } from '@/components/projects/FreelancerReviewDialog'
import { REVIEW_PAYMENT_POLL_MS, ReviewPaymentStatus } from '@/components/projects/ReviewPaymentStatus'
import { formatCurrency, formatDate } from '@/utils/format'

export default function HiringHistory() {
  useDocumentTitle('ประวัติการจ้าง')
  const { profileId } = useAuth()
  const { data, loading, error, refresh, setData } = useAsync(
    () => projectService.listProjects({ role: 'client', profileId }),
    [profileId],
  )

  const [reviewTarget, setReviewTarget] = useState(null)
  const completed = (data || []).filter((project) => project.status === 'completed')
  const totalSpent = completed.reduce((sum, project) => sum + project.releasedAmount, 0)
  const reviewedCount = completed.filter((project) => project.freelancerReviewed).length
  const waitingForPayment = completed.some((project) => project.escrowStatus === 'funded')
  useEffect(() => {
    if (!waitingForPayment) return undefined
    let active = true
    let timer
    async function check() {
      try {
        const updated = await projectService.listProjects({ role: 'client', profileId })
        if (active) setData(updated)
      } catch {
        // Keep the last list while the API is unavailable.
      }
      if (active) timer = setTimeout(check, REVIEW_PAYMENT_POLL_MS)
    }
    timer = setTimeout(check, REVIEW_PAYMENT_POLL_MS)
    return () => { active = false; clearTimeout(timer) }
  }, [waitingForPayment, profileId, setData])

  return (
    <div>
      <PageHeader
        eyebrow="Hiring history"
        title="ประวัติการจ้างงาน"
        description="โครงการที่เสร็จสิ้น มูลค่าที่จ่ายไป และรีวิวที่คุณให้ฟรีแลนซ์"
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="โครงการที่เสร็จสิ้น"
          value={loading ? '—' : completed.length}
          icon={CheckCircle2}
          tone="emerald"
        />
        <StatCard
          label="ยอดจ่ายทั้งหมด"
          value={loading ? '—' : formatCurrency(totalSpent, { compact: true })}
          hint="จาก escrow ที่ปล่อยแล้ว"
          icon={Wallet}
          tone="brand"
        />
        <StatCard
          label="รีวิวที่ให้ไป"
          value={loading ? '—' : reviewedCount}
          hint="ช่วยให้ชุมชนมีข้อมูลคุณภาพ"
          icon={Star}
          tone="amber"
        />
      </div>


      {loading ? (
        <TableSkeleton rows={4} />
      ) : error ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : completed.length === 0 ? (
        <EmptyState
          icon={History}
          title="ยังไม่มีประวัติการจ้างงาน"
          description="เมื่อโครงการแรกเสร็จสิ้นและอนุมัติจ่ายเงิน ประวัติจะแสดงที่นี่"
          action={
            <Button to="/client/jobs" variant="secondary">
              ดูประกาศงาน
            </Button>
          }
        />
      ) : (
        <div className="card overflow-hidden">
          <div className="hidden grid-cols-[2.2fr_1.2fr_1fr_1fr_1.4fr] gap-4 border-b border-ink/[0.06] bg-paper-soft px-5 py-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400 md:grid">
            <span>โครงการ</span>
            <span>ฟรีแลนซ์</span>
            <span>มูลค่า</span>
            <span>เสร็จสิ้น</span>
            <span className="text-right">การจัดการ</span>
          </div>
          <ul className="divide-y divide-ink/[0.06]">
            {completed.map((project) => {
              const reviewed = project.freelancerReviewed
              return (
                <li
                  key={project.id}
                  className="grid gap-3 px-5 py-4 md:grid-cols-[2.2fr_1.2fr_1fr_1fr_1.4fr] md:items-center md:gap-4"
                >
                  <div className="min-w-0">
                    <p className="line-clamp-1 text-[13px] font-semibold text-ink">{project.title}</p>
                    <div className="mt-1 flex items-center gap-1.5">
                      <StatusBadge label="เสร็จสิ้น" tone="emerald" />
                      <span className="text-[10px] text-ink-400">
                        {project.escrowStatus === 'released' ? 'จ่ายเงินแล้ว' : 'รอยืนยันการจ่ายเงิน'}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Avatar
                      name={project.freelancer?.name || 'F'}
                      color={project.freelancer?.avatarColor}
                      size="xs"
                    />
                    <span className="truncate text-[11.5px] font-medium text-ink-600">
                      {project.freelancer?.name}
                    </span>
                  </div>
                  <div className="text-[11.5px] font-semibold text-ink">
                    {formatCurrency(project.releasedAmount)}
                  </div>
                  <div className="text-[11px] text-ink-500">
                    {formatDate(project.completedAt || project.dueDate)}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 md:justify-end">
                    <Button to={`/client/projects/${project.id}`} variant="ghost" size="sm">
                      ดูโครงการ
                    </Button>
                    {project.escrowStatus === 'funded' && <ReviewPaymentStatus projectId={project.id} />}
                    {project.escrowStatus === 'released' && reviewed == null && (
                      <p className="w-full text-xs text-ink-500">ยืนยันการจ่ายเงินแล้ว · API รีวิวไม่พร้อมใช้งาน</p>
                    )}
                    <Button
                      variant={reviewed ? 'secondary' : 'subtle'}
                      size="sm"
                      icon={Star}
                      onClick={() => setReviewTarget(project)}
                      disabled={reviewed !== false || project.escrowStatus !== 'released'}
                    >
                      {reviewed ? 'รีวิวแล้ว' : 'รีวิวฟรีแลนซ์'}
                    </Button>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {reviewTarget && (
        <FreelancerReviewDialog project={reviewTarget} onClose={() => setReviewTarget(null)}
          onSaved={() => { setReviewTarget(null); refresh() }} />
      )}
    </div>
  )
}

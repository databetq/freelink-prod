import { useCallback, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { Briefcase, Flag, ShieldAlert, Users } from 'lucide-react'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { adminService } from '@/services/api/adminService'
import { PageHeader } from '@/components/common/PageHeader'
import { StatCard } from '@/components/common/StatCard'
import { Tabs } from '@/components/common/Tabs'
import { Button } from '@/components/common/Button'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Avatar } from '@/components/common/Avatar'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { TableSkeleton } from '@/components/common/LoadingSkeleton'
import { AccountModerationDialog } from './AccountModerationDialog'
import { AdminDisputes } from './AdminDisputes'
import { jobStatus } from '@/constants'
import { supportStatuses, supportTopics } from '@/constants/support'
import { formatCurrency, formatDate } from '@/utils/format'

const sections = ['users', 'jobs', 'reports', 'disputes']

export default function AdminConsole() {
  const { section = 'users' } = useParams()
  const navigate = useNavigate()
  const tab = sections.includes(section) ? section : 'users'
  useDocumentTitle('Admin console')

  const { data, loading, error, refresh, setData } = useAsync(() => adminService.getOverview(), [])
  const [selectedUserId, setSelectedUserId] = useState(null)
  const closeModeration = useCallback(() => setSelectedUserId(null), [])

  if (!sections.includes(section)) {
    return <Navigate to="/admin/users" replace />
  }

  const users = data?.users || []
  const jobs = data?.jobs || []
  const reports = data?.reports || []
  const selectedUser = users.find((user) => user.id === selectedUserId)

  const updateUser = (updated) => {
    setData((current) => ({
      ...current,
      users: current.users.map((item) => item.id === updated.id ? updated : item),
    }))
  }

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Admin console"
        description="ดูบัญชีผู้ใช้และประกาศงาน พร้อมจัดการสถานะบัญชี"
        actions={
          <Button to="/" variant="secondary" size="md">
            ไปหน้าแรก
          </Button>
        }
      />


      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="ผู้ใช้ทั้งหมด" value={data ? users.length : '—'} icon={Users} tone="brand" />
        <StatCard label="ประกาศงาน" value={data ? jobs.length : '—'} icon={Briefcase} tone="blue" />
        <StatCard label="รายงานที่เปิดอยู่" value={data ? reports.filter((r) => r.status !== 'resolved').length : '—'} icon={Flag} tone="amber" />
      </div>

      <Tabs
        value={tab}
        onChange={(next) => navigate(`/admin/${next}`)}
        className="my-5"
        items={[
          { value: 'users', label: 'ผู้ใช้', count: data ? users.length : undefined },
          { value: 'jobs', label: 'ประกาศงาน', count: data ? jobs.length : undefined },
          { value: 'reports', label: 'รายงานปัญหา', count: reports?.length },
          { value: 'disputes', label: 'ข้อพิพาท Escrow' },
        ]}
      />

      {tab === 'disputes' ? (
        <AdminDisputes />
      ) : loading ? (
        <TableSkeleton rows={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : tab === 'users' ? (
        users.length === 0 ? (
          <EmptyState icon={Users} title="ไม่พบผู้ใช้" />
        ) : (
          <div className="card overflow-hidden">
            <div className="hidden grid-cols-[2fr_1.2fr_0.8fr_0.9fr_1fr] gap-3 border-b border-ink/[0.06] bg-paper-soft px-5 py-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400 md:grid">
              <span>ผู้ใช้</span>
              <span>บทบาท</span>
              <span>สถานะ</span>
              <span>เข้าร่วม</span>
              <span className="text-right">การจัดการ</span>
            </div>
            <ul className="divide-y divide-ink/[0.06]">
              {users.map((user) => (
                <li
                  key={user.id}
                  className="grid gap-2 px-5 py-3.5 md:grid-cols-[2fr_1.2fr_0.8fr_0.9fr_1fr] md:items-center md:gap-3"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <Avatar
                      name={user.name}
                      color={user.role === 'client' ? 'from-indigo-500 to-violet-500' : 'from-violet-500 to-indigo-600'}
                      size="sm"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-semibold text-ink">{user.name}</p>
                      <p className="truncate text-[10px] text-ink-400">{user.contact}</p>
                    </div>
                  </div>
                  <span className="text-[11px] capitalize text-ink-500">{user.role}</span>
                  <span>
                    <StatusBadge
                      label={
                        user.status === 'active' ? 'ใช้งาน' : user.status === 'pending' ? 'รอยืนยัน' : 'ระงับ'
                      }
                      tone={user.status === 'active' ? 'emerald' : user.status === 'pending' ? 'amber' : 'rose'}
                    />
                  </span>
                  <span className="text-[10.5px] text-ink-400">{formatDate(user.joined)}</span>
                  <div className="flex items-center gap-1.5 md:justify-end">
                    {user.role !== 'admin' ? (
                      <Button
                        variant="subtle"
                        size="sm"
                        onClick={() => setSelectedUserId(user.id)}
                      >
                        จัดการ
                      </Button>
                    ) : (
                      <span className="text-[10px] text-ink-400">—</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )
      ) : tab === 'jobs' && jobs.length === 0 ? (
        <EmptyState icon={Briefcase} title="ยังไม่มีประกาศงาน" />
      ) : tab === 'jobs' ? (
        <div className="card overflow-hidden">
          <div className="hidden grid-cols-[2.2fr_1.1fr_0.8fr_1fr_0.9fr] gap-3 border-b border-ink/[0.06] bg-paper-soft px-5 py-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400 md:grid">
            <span>ประกาศงาน</span>
            <span>สถานะ</span>
            <span>ข้อเสนอ</span>
            <span>งบประมาณ</span>
            <span className="text-right">ดู</span>
          </div>
          <ul className="divide-y divide-ink/[0.06]">
            {jobs.map((job) => {
              const status = jobStatus[job.status]
              return (
                <li
                  key={job.id}
                  className="grid gap-2 px-5 py-3.5 md:grid-cols-[2.2fr_1.1fr_0.8fr_1fr_0.9fr] md:items-center md:gap-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold text-ink">{job.title}</p>
                    <p className="text-[10px] text-ink-400">{formatDate(job.createdAt)}</p>
                  </div>
                  <span>
                    <StatusBadge label={status?.label} tone={status?.tone} />
                  </span>
                  <span className="text-[11px] text-ink-500">{job.proposalsCount}</span>
                  <span className="text-[11px] font-semibold text-ink">
                    {formatCurrency(job.budgetMin, { compact: true })}–{formatCurrency(job.budgetMax, { compact: true })}
                  </span>
                  <div className="text-right">
                    {job.status !== 'draft' && <Link
                      to={`/jobs/${job.id}`}
                      className="text-[11px] font-semibold text-brand-700 hover:underline"
                    >
                      เปิดประกาศ →
                    </Link>}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.length === 0 ? (
            <EmptyState icon={Flag} title="ไม่มีรายงานปัญหา" />
          ) : (
            reports.map((report) => (
              <article key={report.id} className="card flex flex-col gap-3 p-5 sm:flex-row sm:items-center">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600">
                  <ShieldAlert className="h-[18px] w-[18px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[12.5px] font-bold text-ink">{supportTopics[report.topic]}{report.target && ` · ${report.target}`}</p>
                    <StatusBadge {...supportStatuses[report.status]} />
                  </div>
                  <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-ink-600">{report.reason}</p>
                  <p className="mt-1 break-words text-[11px] text-ink-500">
                    โดย {report.reporter} ({report.contact}) · อัปเดต {formatDate(report.updatedAt)}
                  </p>
                  <p className="mt-1 break-all text-[10px] text-ink-500">
                    เลขอ้างอิง {report.id}{report.projectId && ` · โครงการ ${report.projectId}`}
                  </p>
                </div>
                <Button to={`/admin/reports/${report.id}`} variant="secondary" size="sm" className="shrink-0">
                  เปิดรายงาน
                </Button>
              </article>
            ))
          )}
        </div>
      )}
      {selectedUser && (
        <AccountModerationDialog key={selectedUser.id}
          user={selectedUser} onClose={closeModeration} onUserUpdated={updateUser} />
      )}
    </div>
  )
}

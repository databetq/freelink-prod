import { LifeBuoy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/common/Button'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { TableSkeleton } from '@/components/common/LoadingSkeleton'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { supportStatuses, supportTopics } from '@/constants/support'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { supportService } from '@/services/api/supportService'
import { formatDate, truncate } from '@/utils/format'

export default function SupportTickets() {
  useDocumentTitle('เรื่องที่แจ้ง')
  const { data, loading, error, refresh } = useAsync(() => supportService.listReports(), [])

  return (
    <div>
      <PageHeader title="เรื่องที่แจ้ง" actions={<Button to="/help#contact" variant="brand">แจ้งเรื่องใหม่</Button>} />
      {loading ? <TableSkeleton rows={4} /> : error ? <ErrorState error={error} onRetry={refresh} /> : data?.length ? (
        <ul className="space-y-3">
          {data.map((report) => (
            <li key={report.id}>
              <Link to={`/support/tickets/${report.id}`} className="card block p-5 transition hover:border-brand-200">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="break-words text-sm font-bold">{supportTopics[report.topic]}{report.target && ` · ${report.target}`}</p>
                  <StatusBadge {...supportStatuses[report.status]} />
                </div>
                <p className="mt-2 break-words text-sm text-ink-600">{truncate(report.reason)}</p>
                <p className="mt-2 text-xs text-ink-500">อัปเดต {formatDate(report.updatedAt)}</p>
              </Link>
            </li>
          ))}
        </ul>
      ) : <EmptyState icon={LifeBuoy} title="ยังไม่มีเรื่องที่แจ้ง" />}
    </div>
  )
}

import { useMemo, useState } from 'react'
import { FolderKanban, SearchX } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { projectService } from '@/services/api/projectService'
import { PageHeader } from '@/components/common/PageHeader'
import { Tabs } from '@/components/common/Tabs'
import { ProjectCard } from '@/components/projects/ProjectCard'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { CardSkeleton } from '@/components/common/LoadingSkeleton'
import { InfoBanner } from '@/components/common/InfoBanner'
import { Button } from '@/components/common/Button'

const projectTabs = {
  ongoing: ['active', 'revision', 'disputed'],
  in_review: ['in_review'],
  completed: ['completed', 'resolved', 'cancelled'],
}

export default function ActiveProjects() {
  const { role, profileId } = useAuth()
  useDocumentTitle('โครงการ')
  const { data, loading, error, refresh } = useAsync(
    () => projectService.listProjects({ role, profileId }),
    [role, profileId],
  )
  const [tab, setTab] = useState('ongoing')

  const projects = data || []
  const groups = useMemo(() => Object.fromEntries(Object.entries(projectTabs).map(([name, statuses]) => [
    name, projects.filter((project) => statuses.includes(project.status)),
  ])), [projects])
  const filtered = tab === 'all' ? projects : groups[tab]

  return (
    <div>
      <PageHeader
        eyebrow="Projects"
        title={role === 'client' ? 'โครงการที่ฉันดูแล' : 'โครงการที่ฉันรับงาน'}
        description={
          role === 'client'
            ? 'ติดตามความคืบหน้า ตรวจรับงาน และจัดการ escrow ของทุกโครงการ'
            : 'ติดตามงานที่ได้รับ ส่งมอบงาน และดูสถานะการตรวจรับ'
        }
        actions={
          role === 'client' ? (
            <Button to="/client/jobs" variant="secondary" size="md">
              ประกาศงานของฉัน
            </Button>
          ) : (
            <Button to="/freelancer/jobs" variant="brand" size="md">
              ค้นหางานใหม่
            </Button>
          )
        }
      />


      <Tabs
        value={tab}
        onChange={setTab}
        className="mb-5"
        items={[
          { value: 'ongoing', label: 'กำลังดำเนินการ', count: groups.ongoing.length },
          { value: 'in_review', label: 'รอตรวจรับ', count: groups.in_review.length },
          { value: 'completed', label: 'ปิดแล้ว', count: groups.completed.length },
          { value: 'all', label: 'ทั้งหมด', count: projects.length },
        ]}
      />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={tab === 'all' ? FolderKanban : SearchX}
          title={tab === 'all' ? 'ยังไม่มีโครงการ' : 'ไม่มีโครงการในสถานะนี้'}
          description={
            role === 'client'
              ? 'เมื่อคุณจ้างฟรีแลนซ์จากข้อเสนอ โครงการจะปรากฏที่นี่เพื่อติดตามงาน'
              : 'เมื่อคุณได้รับงาน โครงการจะปรากฏที่นี่พร้อม milestone และสถานะการชำระเงิน'
          }
          action={
            tab !== 'all' ? (
              <Button variant="secondary" onClick={() => setTab('all')}>
                ดูทั้งหมด
              </Button>
            ) : role === 'client' ? (
              <Button to="/client/jobs" variant="secondary">
                ไปที่ประกาศงาน
              </Button>
            ) : (
              <Button to="/freelancer/jobs" variant="brand">
                ค้นหางาน
              </Button>
            )
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((project) => (
            <ProjectCard key={project.id} project={project} role={role} />
          ))}
        </div>
      )}
    </div>
  )
}

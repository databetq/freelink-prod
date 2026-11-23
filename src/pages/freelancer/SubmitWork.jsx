import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, Send, ShieldCheck, UploadCloud } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { projectService } from '@/services/api/projectService'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/common/Button'
import { Input, Textarea } from '@/components/common/FormField'
import { FileUploadArea } from '@/components/common/FileUploadArea'
import { WorkLinks } from '@/components/projects/WorkLinks'
import { StatusBadge } from '@/components/common/StatusBadge'
import { InfoBanner } from '@/components/common/InfoBanner'
import { ErrorState } from '@/components/common/ErrorState'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { escrowStatus, projectStatus } from '@/constants'
import { formatCurrency, formatDate } from '@/utils/format'
import { validate, minLength, required } from '@/utils/validators'

const MAX_FILES = 3
const MAX_FILE_BYTES = 5 * 1024 * 1024

function encodeAttachment(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({ name: file.name, content: reader.result.split(',', 2)[1] })
    reader.onerror = () => reject(new Error(`อ่านไฟล์ ${file.name} ไม่สำเร็จ`))
    reader.readAsDataURL(file)
  })
}

function workUrl(value) {
  try {
    const url = new URL(value.trim())
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

export default function SubmitWork() {
  const { projectId } = useParams()
  const { profileId } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const { data: project, loading, error, refresh } = useAsync(
    () => projectService.getProject(projectId),
    [projectId],
  )
  useDocumentTitle(project ? `ส่งงาน — ${project.title}` : 'ส่งงาน')

  const [values, setValues] = useState({ title: '', description: '' })
  const [linkRows, setLinkRows] = useState([{ id: 0, label: '', url: '' }])
  const nextLinkId = useRef(1)
  const [files, setFiles] = useState([])
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const maxLinks = project?.maxWorkLinks ?? 1
  const previewLinks = linkRows.map(({ label, url }) => ({ label: label.trim(), url: workUrl(url) }))
    .filter(({ url }) => url && url.length <= 2048)
  const fileLimitExceeded = files.length > MAX_FILES || files.reduce((size, file) => size + file.size, 0) > MAX_FILE_BYTES

  const setField = (field, value) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  const submit = async (event) => {
    event.preventDefault()
    if (busy || !project?.canSubmitWork || fileLimitExceeded) return
    const nextErrors = validate(values, {
      title: [required('ชื่อผลงาน'), minLength(5, 'ชื่อผลงาน')],
      description: [required('รายละเอียดผลงาน'), minLength(20, 'รายละเอียดผลงาน')],
    })
    const links = linkRows.filter(({ label, url }) => label.trim() || url.trim()).map(({ id, label, url }) => {
      const normalized = workUrl(url)
      if (!normalized || normalized.length > 2048) {
        nextErrors[`link-${id}`] = 'กรอก URL ที่ขึ้นต้นด้วย http:// หรือ https:// และยาวไม่เกิน 2,048 ตัวอักษร'
      }
      return { label: label.trim(), url: normalized }
    })
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setBusy(true)
    try {
      await projectService.submitWork(project.id, {
        title: values.title.trim(),
        description: values.description.trim(),
        ...(project.maxWorkLinks ? { links } : { link: links[0]?.url ?? null }),
        files: await Promise.all(files.map(encodeAttachment)),
      })
      toast.success(
        'ส่งงานแล้ว',
        'ระบบบันทึกรายละเอียดการส่งงานแล้ว',
      )
      navigate(`/freelancer/projects/${project.id}`)
    } catch (err) {
      toast.error('ส่งงานไม่สำเร็จ', err.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <PageLoader />
  if (error || !project) return <ErrorState error={error} onRetry={refresh} />

  if (project.freelancerId !== profileId) {
    return (
      <div>
        <PageHeader title="คุณไม่มีสิทธิ์ส่งงานในโครงการนี้" />
        <InfoBanner tone="danger" title="ไม่ใช่โครงการของคุณ">
          โครงการนี้เป็นของฟรีแลนซ์คนอื่น — กลับไปที่รายการโครงการของคุณ
        </InfoBanner>
        <Button to="/freelancer/projects" variant="primary" className="mt-4">
          กลับไปโครงการ
        </Button>
      </div>
    )
  }

  const escrow = escrowStatus[project.escrowStatus]
  const status = projectStatus[project.status]
  const canSubmit = project.canSubmitWork
  const waitingForFunding = ['active', 'revision'].includes(project.status) && project.escrowStatus !== 'funded'

  return (
    <div>
      <PageHeader
        eyebrow="Submit work"
        title="ส่งมอบงาน"
        description={project.title}
        backTo={`/freelancer/projects/${project.id}`}
        backLabel="กลับไปรายละเอียดโครงการ"
        actions={
          <>
            <StatusBadge label={status?.label} tone={status?.tone} />
            <StatusBadge label={escrow?.label} tone={escrow?.tone} />
          </>
        }
      />

      {!canSubmit && (
        <InfoBanner tone="info" className="mb-5" title={waitingForFunding ? 'รอยืนยันการฝากเงินเข้า Escrow' : 'งวดนี้ยังส่งงานเพิ่มไม่ได้'}>
          {waitingForFunding ? 'ส่งงานได้เมื่อระบบยืนยันเงินฝากของงวดปัจจุบันแล้ว' : project.status === 'in_review'
            ? 'งานล่าสุดอยู่ระหว่างตรวจรับ ส่งเวอร์ชันใหม่ได้เมื่อลูกค้าขอแก้ไข'
            : 'ตรวจสถานะงานและงวดถัดไปในรายละเอียดโครงการ'}
        </InfoBanner>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <form onSubmit={submit} noValidate className="space-y-4">
          <section className="card p-5">
            <h2 className="text-sm font-bold">รายละเอียดงานที่ส่ง</h2>
            <div className="mt-4 space-y-3.5">
              <Input
                label="ชื่อผลงาน / เวอร์ชัน"
                value={values.title}
                onChange={(event) => setField('title', event.target.value)}
                error={errors.title}
                maxLength={200}
                placeholder="เช่น Landing page v1 พร้อม design system"
                required
              />
              <Textarea
                label="อธิบายสิ่งที่ส่งมอบ"
                rows={5}
                value={values.description}
                onChange={(event) => setField('description', event.target.value)}
                error={errors.description}
                maxLength={20000}
                placeholder="สรุปงานที่ทำ ไฟล์ที่แนบ และจุดที่อยากให้ลูกค้าตรวจเป็นพิเศษ"
                required
              />
              <fieldset className="space-y-3">
                <legend className="mb-2 text-sm font-semibold">ลิงก์ผลงาน (ไม่บังคับ)</legend>
                {linkRows.map(({ id, label, url }, index) => (
                  <div key={id} className="space-y-2 rounded-xl border border-ink/10 p-3">
                    {maxLinks > 1 && (
                      <Input label={`ชื่อลิงก์ ${index + 1} (ไม่บังคับ)`} value={label} maxLength={100}
                        placeholder="เช่น แบบมือถือ หรือ Design System"
                        onChange={(event) => setLinkRows((rows) => rows.map((row) => (
                          row.id === id ? { ...row, label: event.target.value } : row
                        )))} />
                    )}
                    <Input label={`URL ผลงาน ${index + 1}`} type="url" value={url} maxLength={2048}
                      placeholder="https://www.figma.com/..." error={errors[`link-${id}`]}
                      onChange={(event) => setLinkRows((rows) => rows.map((row) => (
                        row.id === id ? { ...row, url: event.target.value } : row
                      )))} />
                    {linkRows.length > 1 && (
                      <Button type="button" variant="ghost" size="sm"
                        onClick={() => setLinkRows((rows) => rows.filter((row) => row.id !== id))}>
                        ลบลิงก์ {index + 1}
                      </Button>
                    )}
                  </div>
                ))}
                {linkRows.length < maxLinks && (
                  <Button type="button" variant="secondary" size="sm" onClick={() => {
                    const id = nextLinkId.current++
                    setLinkRows((rows) => [...rows, { id, label: '', url: '' }])
                  }}>+ เพิ่มลิงก์</Button>
                )}
              </fieldset>
              <FileUploadArea
                files={files}
                onFilesChange={setFiles}
                label="ไฟล์แนบ"
                hint="แนบได้สูงสุด 3 ไฟล์ ขนาดรวมไม่เกิน 5 MB"
              />
              {fileLimitExceeded && <p role="alert" className="text-xs text-rose-700">กรุณาลดจำนวนหรือขนาดไฟล์แนบก่อนส่งงาน</p>}
            </div>
          </section>

          <section className="card p-5">
            <h2 className="text-sm font-bold">เช็กลิสต์ก่อนส่ง</h2>
            <ul className="mt-3 space-y-2">
              {[
                'ตรวจงานครบทุก deliverables ในขอบเขตที่ตกลง',
                'ไฟล์และลิงก์เปิดได้โดยไม่ต้องขอสิทธิ์',
                'ทดสอบบนอุปกรณ์และเบราว์เซอร์หลักแล้ว',
                'ระบุเวอร์ชันและสิ่งที่เปลี่ยนแปลงให้ชัดเจน',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-[12px] leading-relaxed text-ink-600">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                  {item}
                </li>
              ))}
            </ul>
          </section>


          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => navigate(-1)} disabled={busy}>
              ยกเลิก
            </Button>
            <Button type="submit" variant="brand" size="md" icon={Send} loading={busy} disabled={!canSubmit || fileLimitExceeded}>
              ส่งงานให้ลูกค้า
            </Button>
          </div>
        </form>

        <aside className="space-y-4 lg:sticky lg:top-[88px] lg:self-start">
          <div className="card p-5">
            <h2 className="text-sm font-bold">สรุปโครงการ</h2>
            <div className="mt-3 space-y-2.5 text-[11.5px]">
              <div className="flex items-center justify-between">
                <span className="text-ink-500">ลูกค้า</span>
                <span className="font-semibold text-ink">{project.client?.name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">มูลค่างาน</span>
                <span className="font-bold text-ink">{formatCurrency(project.budget)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">กำหนดส่ง</span>
                <span className="font-semibold text-ink">{formatDate(project.dueDate)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">เงินใน Escrow</span>
                <span className="font-semibold text-emerald-600">
                  {formatCurrency(project.escrowStatus === 'funded' ? project.escrowAmount : 0)}
                </span>
              </div>
            </div>
            <div className="mt-4 space-y-1.5 border-t border-ink/[0.06] pt-3">
              {(project.milestones || []).map((milestone) => (
                <div key={milestone.id} className="flex items-center justify-between gap-2 text-[10.5px]">
                  <span className="truncate text-ink-500">{milestone.title}</span>
                  <span className="shrink-0 font-semibold text-ink">{formatCurrency(milestone.amount, { compact: true })}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-5">
            <div className="flex items-center gap-2 text-[12px] font-bold">
              <UploadCloud className="h-4 w-4 text-brand-600" />
              หลังส่งงาน
            </div>
            <ol className="mt-2.5 space-y-2 text-[11px] leading-relaxed text-ink-500">
              <li>1. ลูกค้าได้รับแจ้งเตือนและตรวจงาน</li>
              <li>2. ลูกค้าอนุมัติงานและยืนยันการจ่ายเงินแยกในหน้า Escrow</li>
              <li>3. หากต้องแก้ไข คุณจะเห็น feedback และส่งใหม่ได้</li>
            </ol>
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-emerald-50/70 px-3 py-2">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
              <p className="text-[10px] leading-relaxed text-emerald-800">
                ตรวจสถานะการจ่ายเงินจริงได้จากหน้า Escrow
              </p>
            </div>
          </div>

          <Button to={`/help?projectId=${project.id}#contact`} variant="secondary" size="sm" className="w-full">
            แจ้งปัญหาโครงการให้แอดมิน
          </Button>

          {previewLinks.length > 0 && (
            <section className="card p-5">
              <h2 className="text-xs font-bold">ตัวอย่างลิงก์ที่ลูกค้าจะเห็น</h2>
              <WorkLinks submission={{ links: previewLinks }} />
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}

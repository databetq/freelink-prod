import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { HelpCircle, Mail, MessageSquare, SearchX, ShieldCheck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { SearchBar } from '@/components/common/SearchBar'
import { FaqAccordion } from '@/components/common/FaqAccordion'
import { InfoBanner } from '@/components/common/InfoBanner'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/common/Button'
import { Select, Textarea } from '@/components/common/FormField'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { validate, minLength, required } from '@/utils/validators'
import { faqs } from '@/data/faqs'
import { supportService } from '@/services/api/supportService'
import { supportTopics } from '@/constants/support'

export default function HelpPage() {
  useDocumentTitle('ช่วยเหลือ & FAQ')
  const { user, loading: authLoading } = useAuth()
  const toast = useToast()
  const location = useLocation()
  const projectId = new URLSearchParams(location.search).get('projectId')
  const [query, setQuery] = useState('')
  const [values, setValues] = useState({ topic: projectId ? 'report' : 'general', message: '' })
  const [errors, setErrors] = useState({})
  const [receipt, setReceipt] = useState(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (location.hash !== '#contact') return undefined
    const frame = requestAnimationFrame(() => document.getElementById('contact')?.scrollIntoView())
    return () => cancelAnimationFrame(frame)
  }, [location.hash])

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return faqs
    return faqs.filter((faq) =>
      `${faq.question} ${faq.answer}`.toLowerCase().includes(term),
    )
  }, [query])

  const submit = async (event) => {
    event.preventDefault()
    if (!user || sending) return
    const nextErrors = validate(values, {
      message: [required('รายละเอียด'), minLength(20, 'รายละเอียด')],
    })
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setSending(true)
    setReceipt(null)
    try {
      const result = await supportService.submitReport({ ...values, message: values.message.trim(), projectId })
      setReceipt(result.id)
      setValues((current) => ({ ...current, message: '' }))
      toast.success('ส่งข้อความถึงแอดมินแล้ว')
    } catch (error) {
      toast.error('ส่งข้อความไม่สำเร็จ', error.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="pt-[72px]">
      <div className="relative border-b border-ink/[0.06] bg-white">
        <div className="surface-grid absolute inset-0 opacity-60" aria-hidden="true" />
        <div className="container-page relative py-10 sm:py-12">
          <PageHeader
            eyebrow="Help center"
            title="มีคำถาม? เรามีคำตอบ"
            description="ค้นหาคำตอบเรื่องการจ้างงาน การชำระเงิน และสถานะการเชื่อมต่อระบบในเวอร์ชันนี้"
          />
          <div className="max-w-xl">
            <SearchBar
              value={query}
              onChange={setQuery}
              placeholder="ค้นหาคำถาม เช่น escrow, google login, ค่าธรรมเนียม…"
              size="lg"
            />
          </div>
        </div>
      </div>

      <div className="container-page py-8 sm:py-10">
        <div className="grid gap-8 lg:grid-cols-[1.35fr_0.65fr]">
          <div>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-bold text-ink">
                คำถามที่พบบ่อย {query && `· ${filtered.length} ผลลัพธ์`}
              </h2>
              <span className="text-[11px] text-ink-400">ทั้งหมด {faqs.length} คำถาม</span>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                icon={SearchX}
                title="ไม่พบคำตอบที่ตรงกับคำค้น"
                description="ลองใช้คำที่สั้นลง หรือดูคำถามทั้งหมดอีกครั้ง"
                action={
                  <Button variant="secondary" onClick={() => setQuery('')}>
                    ล้างคำค้นหา
                  </Button>
                }
              />
            ) : (
              <FaqAccordion items={filtered} defaultOpen={filtered[0]?.id} />
            )}

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {[
                { icon: ShieldCheck, title: 'Escrow safety', text: 'เงินถูกคุ้มครองจนกว่าจะตรวจรับงาน' },
                { icon: MessageSquare, title: 'คุยกับฟรีแลนซ์', text: 'ใช้หน้าข้อความเพื่อตกลงรายละเอียด' },
                { icon: HelpCircle, title: 'สถานะระบบ', text: 'งานและข้อเสนอใช้ข้อมูลจากเซิร์ฟเวอร์' },
              ].map((item) => {
                const Icon = item.icon
                return (
                  <div key={item.title} className="rounded-xl border border-ink/[0.07] bg-white p-4">
                    <Icon className="h-4 w-4 text-brand-600" aria-hidden="true" />
                    <p className="mt-2 text-xs font-bold text-ink">{item.title}</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-ink-500">{item.text}</p>
                  </div>
                )
              })}
            </div>
          </div>

          <aside className="space-y-4">
            <form id="contact" onSubmit={submit} className="card scroll-mt-24 p-5" noValidate>
              <h2 className="text-base font-bold">ติดต่อทีม Freelink</h2>
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink-500">
                {projectId ? 'ส่งปัญหาพร้อมเลขอ้างอิงโครงการให้แอดมินตรวจสอบ' : 'ส่งคำถามหรือแจ้งปัญหาให้แอดมินตรวจสอบ'}
              </p>

              {user ? <div className="mt-4 space-y-3">
                <Select
                  label="หัวข้อ"
                  value={values.topic}
                  onChange={(event) => setValues({ ...values, topic: event.target.value })}
                >
                  {Object.entries(supportTopics).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </Select>
                <Textarea
                  label="รายละเอียด"
                  rows={4}
                  maxLength={5000}
                  value={values.message}
                  onChange={(event) => setValues({ ...values, message: event.target.value })}
                  error={errors.message}
                  placeholder="อธิบายสิ่งที่ต้องการความช่วยเหลือ (อย่างน้อย 20 ตัวอักษร)"
                  required
                />
                <Button type="submit" variant="brand" size="md" className="w-full" icon={Mail} loading={sending}>
                  ส่งข้อความ
                </Button>
              </div> : !authLoading && (
                <Link to="/login" state={{ from: location.pathname + location.search + location.hash }} className="mt-4 inline-flex text-sm font-semibold text-brand-700 underline">
                  เข้าสู่ระบบเพื่อส่งข้อความ
                </Link>
              )}

              {receipt && (
                <InfoBanner className="mt-3" title="ส่งข้อความถึงแอดมินแล้ว">
                  <p className="break-all">เลขอ้างอิง {receipt}</p>
                  <Link to={`/support/tickets/${receipt}`} className="mt-1 inline-block font-semibold text-brand-700 underline">
                    เปิดเรื่องที่เพิ่งแจ้ง
                  </Link>
                </InfoBanner>
              )}
            </form>
            {user && <Button to="/support/tickets" variant="secondary">ดูเรื่องที่แจ้งทั้งหมด</Button>}
          </aside>
        </div>
      </div>
    </div>
  )
}

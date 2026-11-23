import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  Bell,
  ChevronRight,
  Database,
  LogOut,
  ShieldCheck,
  Trash2,
  UserRound,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/common/Button'
import { Avatar } from '@/components/common/Avatar'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { StatusBadge } from '@/components/common/StatusBadge'
import { appConfig } from '@/config/appConfig'
import { contractConfig, isContractConfigured } from '@/config/contractConfig'
import { cn } from '@/utils/cn'

const PREF_KEY = 'freelink.preferences'
const defaultPrefs = {
  emailUpdates: true,
  proposalAlerts: true,
  paymentAlerts: true,
  productNews: false,
}

function Toggle({ checked, onChange, label, description }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <p className="text-[12.5px] font-semibold text-ink">{label}</p>
        <p className="mt-0.5 text-[10.5px] leading-relaxed text-ink-500">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition',
          checked ? 'bg-brand-600' : 'bg-ink/15',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition',
            checked ? 'left-[18px]' : 'left-0.5',
          )}
        />
      </button>
    </div>
  )
}

export default function Settings() {
  useDocumentTitle('ตั้งค่า')
  const { user, role, signOut } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [prefs, setPrefs] = useState(defaultPrefs)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(PREF_KEY)
      if (raw) setPrefs({ ...defaultPrefs, ...JSON.parse(raw) })
    } catch {
      // Ignore malformed preferences.
    }
  }, [])

  const updatePrefs = (patch) => {
    const next = { ...prefs, ...patch }
    setPrefs(next)
    try {
      window.localStorage.setItem(PREF_KEY, JSON.stringify(next))
    } catch {
      // Preferences still apply for the session.
    }
  }

  const handleConfirm = async () => {
    setBusy(true)
    try {
      if (confirm === 'saved') {
        window.localStorage.removeItem('freelink.savedJobs')
        toast.success('ล้างรายการงานที่บันทึกแล้ว')
      } else if (confirm === 'logout') {
        await signOut()
        toast.info('ออกจากระบบแล้ว')
        navigate('/')
        return
      }
      setConfirm(null)
    } catch (error) {
      toast.error('ดำเนินการไม่สำเร็จ', error.message)
    } finally {
      setBusy(false)
    }
  }

  if (role === 'admin') return <Navigate to="/admin" replace />

  const profilePath = role === 'client' ? '/client/profile' : '/freelancer/profile'

  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="ตั้งค่า"
        description="จัดการบัญชี การแจ้งเตือน และรายการที่บันทึกไว้"
      />

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <section className="card p-5">
            <h2 className="text-sm font-bold">บัญชี</h2>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Avatar name={user?.name || 'User'} color={user?.avatarColor} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-ink">{user?.displayName || user?.name}</p>
                <p className="truncate text-[11px] text-ink-500">{user?.email}</p>
                <div className="mt-1 flex items-center gap-1.5">
                  <StatusBadge
                    label={role === 'client' ? 'Client' : 'Freelancer'}
                    tone={role === 'client' ? 'blue' : 'violet'}
                  />
                </div>
              </div>
              <Button to={profilePath} variant="secondary" size="sm" icon={UserRound}>
                แก้ไขโปรไฟล์
              </Button>
            </div>

            <div className="mt-4 grid gap-3 border-t border-ink/[0.06] pt-4 sm:grid-cols-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">อีเมล</p>
                <p className="mt-0.5 text-[11.5px] text-ink-600">{user?.email}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">ผู้ให้บริการยืนยันตัวตน</p>
                <p className="mt-0.5 text-[11.5px] text-ink-600">
                  Google
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="danger-ghost" size="sm" icon={LogOut} onClick={() => setConfirm('logout')}>
                ออกจากระบบ
              </Button>
            </div>
          </section>

          <section className="card p-5">
            <h2 className="flex items-center gap-2 text-sm font-bold">
              <Bell className="h-4 w-4 text-brand-600" />
              การแจ้งเตือน
            </h2>
            <p className="mt-1 text-[11px] text-ink-500">
              บันทึกไว้ในเบราว์เซอร์เท่านั้น — ยังไม่มีระบบส่งอีเมลหรือ push จริง
            </p>
            <div className="mt-2 divide-y divide-ink/[0.06]">
              <Toggle
                checked={prefs.emailUpdates}
                onChange={(value) => updatePrefs({ emailUpdates: value })}
                label="อัปเดตทางอีเมล"
                description="สรุปความเคลื่อนไหวของงานและข้อความ"
              />
              <Toggle
                checked={prefs.proposalAlerts}
                onChange={(value) => updatePrefs({ proposalAlerts: value })}
                label="แจ้งเตือนข้อเสนอ"
                description="เมื่อมีข้อเสนอใหม่หรือข้อเสนอถูกคัดเลือก"
              />
              <Toggle
                checked={prefs.paymentAlerts}
                onChange={(value) => updatePrefs({ paymentAlerts: value })}
                label="แจ้งเตือนการชำระเงิน"
                description="สถานะ escrow และการปล่อยเงิน"
              />
              <Toggle
                checked={prefs.productNews}
                onChange={(value) => updatePrefs({ productNews: value })}
                label="ข่าวสารผลิตภัณฑ์"
                description="ฟีเจอร์ใหม่และเคล็ดลับการใช้งาน"
              />
            </div>
          </section>

          <section className="card p-5">
            <h2 className="flex items-center gap-2 text-sm font-bold">
              <Database className="h-4 w-4 text-brand-600" />
              ข้อมูลในเบราว์เซอร์
            </h2>
            <div className="mt-4 space-y-2">
              <button
                type="button"
                onClick={() => setConfirm('saved')}
                className="flex w-full items-center justify-between rounded-xl border border-ink/[0.08] bg-white px-3.5 py-2.5 text-left transition hover:border-brand-300"
              >
                <span className="flex items-center gap-2 text-[11.5px] font-semibold text-ink">
                  <Trash2 className="h-3.5 w-3.5 text-ink-400" />
                  ล้างรายการงานที่บันทึกไว้
                </span>
                <ChevronRight className="h-3.5 w-3.5 text-ink-300" />
              </button>
            </div>
          </section>
        </div>

        <aside className="space-y-4">
          <section className="card p-5">
            <h2 className="text-sm font-bold">สถานะระบบ</h2>
            <div className="mt-3 space-y-2.5 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="text-ink-500">API base URL</span>
                <span className="max-w-[160px] truncate text-right font-mono text-[9.5px] text-ink-600">
                  {appConfig.apiBaseUrl || 'ยังไม่ตั้งค่า'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">Smart Contract</span>
                <span
                  className={cn(
                    'font-semibold',
                    isContractConfigured() ? 'text-emerald-600' : 'text-amber-600',
                  )}
                >
                  {isContractConfigured() ? 'พร้อมใช้งาน' : 'รอการตั้งค่า'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-500">Chain ID</span>
                <span className="font-semibold text-ink">{contractConfig.chainId || '—'}</span>
              </div>
            </div>
          </section>

          <section className="card p-5">
            <h2 className="flex items-center gap-2 text-sm font-bold">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              ความปลอดภัย
            </h2>
            <ul className="mt-2.5 space-y-2 text-[11px] leading-relaxed text-ink-500">
              <li>• ไม่มีการเก็บรหัสผ่านหรือ private key ใน Frontend</li>
              <li>• Wallet ลงนามธุรกรรมในอุปกรณ์ของคุณเท่านั้น</li>
              <li>• ไม่มี API key หรือ secret ฝังใน bundle</li>
            </ul>
          </section>
        </aside>
      </div>

      <ConfirmDialog
        open={Boolean(confirm)}
        onClose={() => setConfirm(null)}
        onConfirm={handleConfirm}
        loading={busy}
        title={
          confirm === 'saved'
              ? 'ล้างรายการที่บันทึกไว้?'
              : 'ออกจากระบบ?'
        }
        description={
          confirm === 'saved'
              ? 'รายการงานที่คุณบันทึกไว้ในเบราว์เซอร์จะถูกล้าง'
              : 'คุณจะกลับไปหน้าแรกและต้องเข้าสู่ระบบใหม่เพื่อใช้งานแดชบอร์ด'
        }
        confirmLabel={confirm === 'logout' ? 'ออกจากระบบ' : 'ยืนยัน'}
      />
    </div>
  )
}

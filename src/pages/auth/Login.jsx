import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { BriefcaseBusiness, Palette } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/FormField'
import { InfoBanner } from '@/components/common/InfoBanner'
import { GoogleIcon } from '@/components/common/GoogleIcon'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { resolveAuthReturnPath } from '@/services/auth/authService'
import { cn } from '@/utils/cn'

const roles = [
  { value: 'client', label: 'ฉันต้องการจ้างงาน', description: 'โพสต์งานและจัดการโครงการ', icon: BriefcaseBusiness },
  { value: 'freelancer', label: 'ฉันต้องการรับงาน', description: 'ค้นหางานและส่งข้อเสนอ', icon: Palette },
]

const googleLoginErrors = {
  'account-not-found': 'บัญชี Google นี้ยังไม่ได้สมัคร Freelink กรุณากดสมัครใช้งานเพื่อเลือกบทบาท',
  'account-suspended': 'บัญชีนี้ถูกระงับ กรุณาติดต่อทีมงานหากต้องการตรวจสอบ',
}

export default function Login({ register = false }) {
  const title = register ? 'สมัครใช้งาน' : 'เข้าสู่ระบบ'
  useDocumentTitle(title)
  const { user, loading, authError, signInWithGoogle, signInPassword, registerPassword } = useAuth()
  const location = useLocation()
  const from = location.state?.from
  const [role, setRole] = useState(from?.startsWith('/freelancer/') ? 'freelancer' : 'client')
  const [error, setError] = useState(null)
  const [redirecting, setRedirecting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const callbackCode = new URLSearchParams(location.search).get('error')
  const callbackError = Object.hasOwn(googleLoginErrors, callbackCode) ? googleLoginErrors[callbackCode] : null
  const displayError = error || callbackError || authError?.message

  if (user) return <Navigate to={resolveAuthReturnPath(user, from)} replace />

  const handlePassword = async (event) => {
    event.preventDefault()
    if (loading || submitting || redirecting) return
    setError(null)
    setSubmitting(true)
    try {
      if (register) {
        await registerPassword({ name, email, role, password })
      } else {
        await signInPassword(email, password)
      }
    } catch (failure) {
      setError(failure.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleGoogle = () => {
    setError(null)
    setRedirecting(true)
    try {
      signInWithGoogle(register ? role : undefined, from)
    } catch (failure) {
      setError(failure.message)
      setRedirecting(false)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-extrabold tracking-tight">{title} Freelink</h1>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">
        {register ? 'เลือกบทบาท แล้วสมัครด้วยอีเมลหรือ Google' : 'เข้าสู่ระบบด้วยอีเมลและรหัสผ่าน หรือใช้บัญชี Google'}
      </p>
      {register && (
        <fieldset className="mt-6">
          <legend className="sr-only">เลือกบทบาท</legend>
          <div className="grid grid-cols-2 gap-2.5">
            {roles.map(({ value, label, description, icon: Icon }) => (
              <label
                key={value}
                className={cn(
                  'relative cursor-pointer rounded-xl border p-3.5 transition',
                  role === value ? 'border-brand-500 bg-brand-50/70' : 'border-ink/10 bg-white',
                )}
              >
                <input
                  type="radio"
                  name="role"
                  value={value}
                  checked={role === value}
                  onChange={() => setRole(value)}
                  className="sr-only"
                />
                <Icon className="h-[18px] w-[18px] text-brand-600" aria-hidden="true" />
                <span className="mt-2 block text-[12.5px] font-bold text-ink">{label}</span>
                <span className="mt-0.5 block text-[10.5px] text-ink-500">{description}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {displayError && (
        <InfoBanner tone="warning" className="mt-5"
          title={!error && !callbackError && authError?.code === 'SESSION_ENDED' ? 'กรุณาเข้าสู่ระบบใหม่' : 'เข้าสู่ระบบไม่สำเร็จ'}>
          {displayError}
        </InfoBanner>
      )}
      <form className="mt-5 space-y-4" onSubmit={handlePassword}>
        {register && (
          <Input label="ชื่อที่แสดง" name="name" autoComplete="name" maxLength={200} required
            value={name} onChange={(event) => setName(event.target.value)} />
        )}
        <Input label="อีเมล" name="email" type="email" autoComplete={register ? 'email' : 'username'}
          maxLength={320} required value={email} onChange={(event) => setEmail(event.target.value)} />
        <Input label="รหัสผ่าน" name="password" type="password"
          autoComplete={register ? 'new-password' : 'current-password'}
          hint={register ? 'อย่างน้อย 8 ตัวอักษร' : undefined} minLength={register ? 8 : 1}
          maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
        <Button type="submit" variant="brand" size="lg" className="w-full" loading={submitting}
          disabled={loading || redirecting}>
          {title}
        </Button>
      </form>
      <p className="mt-4 text-center text-xs text-ink-500">หรือ</p>
      <Button variant="secondary" size="lg" className="mt-2 w-full" onClick={handleGoogle}
        loading={redirecting} disabled={loading || submitting}>
        <GoogleIcon className="h-4 w-4" />
        ดำเนินการต่อด้วย Google
      </Button>
      <p className="mt-5 text-center text-[12.5px] text-ink-500">
        {register ? 'มีบัญชีแล้ว?' : 'ยังไม่มีบัญชี?'}{' '}
        <Link to={register ? '/login' : '/register'} state={location.state} className="font-semibold text-brand-700 hover:underline">
          {register ? 'เข้าสู่ระบบ' : 'สมัครใช้งาน'}
        </Link>
      </p>
      {!register && (
        <Link to="/admin/login" className="mt-4 block text-center text-xs text-ink-500 hover:underline">
          เข้าสู่ระบบสำหรับแอดมิน
        </Link>
      )}
    </div>
  )
}

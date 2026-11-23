import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/FormField'
import { InfoBanner } from '@/components/common/InfoBanner'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { resolveAuthReturnPath } from '@/services/auth/authService'

export default function AdminLogin() {
  useDocumentTitle('เข้าสู่ระบบแอดมิน')
  const { loading, user, authError, signInAdmin } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const location = useLocation()
  if (user?.role === 'admin') return <Navigate to={resolveAuthReturnPath(user, location.state?.from)} replace />

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await signInAdmin(username, password)
    } catch (failure) {
      setError(failure.message)
    } finally {
      setPassword('')
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-extrabold tracking-tight">เข้าสู่ระบบแอดมิน</h1>
      {error && <InfoBanner tone="warning" className="mt-5" title="เข้าสู่ระบบไม่สำเร็จ">{error}</InfoBanner>}
      {!error && authError?.code === 'SESSION_ENDED' && (
        <InfoBanner tone="warning" className="mt-5" title="กรุณาเข้าสู่ระบบใหม่">{authError.message}</InfoBanner>
      )}
      <form className="mt-6 space-y-4" onSubmit={submit}>
        <Input label="ชื่อผู้ใช้" name="username" autoComplete="username" maxLength={64}
          value={username} onChange={(event) => setUsername(event.target.value)} required />
        <Input label="รหัสผ่าน" name="password" type="password" autoComplete="current-password" maxLength={128}
          value={password} onChange={(event) => setPassword(event.target.value)} required />
        <Button type="submit" variant="brand" size="lg" className="w-full" loading={loading || submitting}>
          เข้าสู่ระบบ
        </Button>
      </form>
      <Link to="/login" className="mt-5 block text-center text-xs text-ink-500 hover:underline">
        กลับไปหน้าเข้าสู่ระบบทั่วไป
      </Link>
    </div>
  )
}

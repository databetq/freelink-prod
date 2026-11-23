import { useState } from 'react'
import { Star } from 'lucide-react'
import { Button } from '@/components/common/Button'
import { Modal } from '@/components/common/Modal'
import { Textarea } from '@/components/common/FormField'
import { profileService } from '@/services/api/profileService'
import { cn } from '@/utils/cn'

export function FreelancerReviewDialog({ project, onClose, onSaved }) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (busy) return
    if (!rating || comment.trim().length < 10) {
      setError('เลือกคะแนนและเขียนความคิดเห็นอย่างน้อย 10 ตัวอักษร')
      return
    }
    setBusy(true)
    setError('')
    try {
      await profileService.addReview({ freelancerId: project.freelancerId, projectId: project.id, rating, comment: comment.trim() })
      onSaved(project.id)
    } catch (err) {
      if (err.code === 'REVIEW_ALREADY_EXISTS') onSaved(project.id)
      else setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open onClose={() => { if (!busy) onClose() }} title="รีวิวฟรีแลนซ์" description={project.freelancer?.name || project.title}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={busy}>ยกเลิก</Button>
        <Button variant="brand" onClick={submit} loading={busy}>ส่งรีวิว</Button>
      </>}>
      <fieldset className="mb-4">
        <legend className="field-label">คะแนนโดยรวม</legend>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((value) => (
            <button key={value} type="button" aria-label={`${value} ดาว`} aria-pressed={value === rating}
              disabled={busy} onClick={() => setRating(value)} className="rounded-md p-1 focus-visible:ring-2 focus-visible:ring-brand-500">
              <Star aria-hidden="true" className={cn('h-7 w-7', value <= rating ? 'fill-amber-400 text-amber-400' : 'text-slate-300')} />
            </button>
          ))}
        </div>
      </fieldset>
      <Textarea label="ความคิดเห็น" value={comment} onChange={(event) => setComment(event.target.value)}
        rows={4} maxLength={2000} disabled={busy} />
      {error && <p role="alert" className="mt-2 text-sm text-rose-700">{error}</p>}
      <p className="mt-2 text-xs text-ink-500">รีวิวนี้จะแสดงบนโปรไฟล์ฟรีแลนซ์</p>
    </Modal>
  )
}

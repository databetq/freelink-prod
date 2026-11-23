import { useState } from 'react'
import { Button } from '@/components/common/Button'
import { useToast } from '@/contexts/ToastContext'
import { proposalService } from '@/services/api/proposalService'

export function ShortlistButton({ proposal, setProposals }) {
  const [updating, setUpdating] = useState(false)
  const toast = useToast()
  const shortlisted = proposal.status === 'shortlisted'

  const updateShortlist = async () => {
    setUpdating(true)
    try {
      const updated = await proposalService.updateStatus(proposal.id, shortlisted ? 'pending' : 'shortlisted')
      setProposals((current) => current?.map((item) => item.id === updated.id ? updated : item))
      toast.success(shortlisted ? 'ยกเลิกการคัดเลือกแล้ว' : 'คัดเลือกข้อเสนอแล้ว')
    } catch (error) {
      toast.error('อัปเดตไม่สำเร็จ', error.message)
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Button variant="subtle" size="sm" loading={updating} onClick={updateShortlist}>
      {shortlisted ? 'ยกเลิกการคัดเลือก' : 'คัดเลือก'}
    </Button>
  )
}

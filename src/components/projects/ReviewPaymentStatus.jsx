import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { escrowService } from '@/services/api/escrowService'
import { getExplorerTxUrl } from '@/services/blockchain/transactionService'

export const REVIEW_PAYMENT_POLL_MS = 12000

const labels = {
  checking_transaction: 'กำลังตรวจธุรกรรมใน Sepolia',
  awaiting_finality: 'ปล่อยเงินแล้ว · รอครบจำนวนบล็อกยืนยัน',
  syncing: 'Sepolia ยืนยันแล้ว · ระบบกำลังบันทึกยอดจ่าย',
  released: 'ยืนยันการจ่ายเงินแล้ว',
}
const blockNumber = new Intl.NumberFormat('en-US')

export function ReviewPaymentStatus({ projectId, milestoneNumber, showEscrowLink = true, role = 'client' }) {
  const [result, setResult] = useState(null)
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    let active = true
    let timer
    async function check() {
      try {
        const next = await escrowService.getReleaseProgress(projectId)
        if (active) {
          setResult({ projectId, ...next })
          setUnavailable(false)
        }
      } catch {
        if (active) setUnavailable(true)
      }
      if (active) timer = setTimeout(check, REVIEW_PAYMENT_POLL_MS)
    }
    check()
    return () => { active = false; clearTimeout(timer) }
  }, [projectId])

  const progress = result?.projectId === projectId ? result : null
  const explorerUrl = getExplorerTxUrl(progress?.txHash)
  const status = progress?.status
  const heading = status === 'awaiting_release'
    ? `รอธุรกรรมปล่อยเงิน${milestoneNumber ? `งวด ${milestoneNumber}` : 'งวดสุดท้าย'}`
    : labels[status] || 'กำลังอ่านสถานะการปล่อยเงิน'
  return (
    <div className="w-full text-xs leading-relaxed text-ink-600" aria-live="polite">
      <p className="font-medium">{heading}</p>
      {progress?.txBlock != null && <p>ธุรกรรมปล่อยเงินอยู่ในบล็อก #{blockNumber.format(progress.txBlock)}</p>}
      {progress?.finalizedBlock != null && <p>ระบบตรวจยืนยันถึงบล็อก #{blockNumber.format(progress.finalizedBlock)}</p>}
      {unavailable && <p>อ่านสถานะล่าสุดไม่ได้ชั่วคราว ระบบจะลองอีกครั้ง</p>}
      <p>ตรวจสถานะอัตโนมัติทุก {REVIEW_PAYMENT_POLL_MS / 1000} วินาที</p>
      {explorerUrl ? <a href={explorerUrl} target="_blank" rel="noreferrer" className="font-semibold text-brand-700 underline">ดูบน Etherscan</a>
        : showEscrowLink && <Link to={`/${role}/projects/${projectId}/escrow`} className="font-semibold text-brand-700 underline">ดูหน้า Escrow</Link>}
    </div>
  )
}

import { useState } from 'react'
import { Button } from '@/components/common/Button'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { ErrorState } from '@/components/common/ErrorState'
import { InfoBanner } from '@/components/common/InfoBanner'
import { TableSkeleton } from '@/components/common/LoadingSkeleton'
import { WorkLinks } from '@/components/projects/WorkLinks'
import { TransactionStatus } from '@/components/wallet/TransactionStatus'
import { WalletConnectButton } from '@/components/wallet/WalletConnectButton'
import { contractConfig } from '@/config/contractConfig'
import { useWallet } from '@/contexts/WalletContext'
import { useAsync } from '@/hooks/useAsync'
import { adminService } from '@/services/api/adminService'
import { hashTerms, readEscrow, resolveDispute } from '@/services/blockchain/contractService'
import { executeTransaction } from '@/services/blockchain/transactionService'
import { formatDate } from '@/utils/format'

export function AdminDisputes() {
  const { data, loading, error, refresh } = useAsync(adminService.getDisputes, [])
  if (loading) return <TableSkeleton rows={3} />
  if (error) return <ErrorState error={error} onRetry={refresh} />

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <WalletConnectButton />
        <Button variant="secondary" size="sm" onClick={refresh}>อัปเดตรายการ</Button>
      </div>
      {!data?.length && <InfoBanner>ยังไม่มีข้อพิพาทที่ระบบยืนยัน</InfoBanner>}
      {data?.map((dispute) => <DisputeCard key={dispute.agreementId} dispute={dispute} />)}
    </section>
  )
}

function DisputeCard({ dispute }) {
  const wallet = useWallet()
  const [percent, setPercent] = useState('50')
  const [confirm, setConfirm] = useState(false)
  const [transaction, setTransaction] = useState(null)
  const [busy, setBusy] = useState(false)
  const terms = JSON.parse(dispute.termsJson)
  const sameDeployment = terms.chainId === contractConfig.chainId && terms.contract === contractConfig.contractAddress?.toLowerCase()
  const ready = sameDeployment && wallet.isConnected && wallet.chainId === terms.chainId
  const { data: onChain, loading, error, refresh } = useAsync(
    () => ready ? readEscrow({ escrowId: dispute.escrowId }) : null,
    [ready, dispute.escrowId, wallet.address],
  )
  const matching = ready && onChain?.termsHash === dispute.termsHash && hashTerms(dispute.termsJson) === dispute.termsHash
    && onChain.client.toLowerCase() === terms.client && onChain.freelancer.toLowerCase() === terms.freelancer
    && String(onChain.amount) === terms.amountWei
  const open = matching && onChain.statusName === 'disputed'
  const isArbiter = open && wallet.address?.toLowerCase() === onChain.arbiter.toLowerCase()
  const payout = Number(percent)
  const canResolve = isArbiter && percent !== '' && Number.isInteger(payout) && payout >= 0 && payout <= 100 && !loading && !error

  async function resolve() {
    if (!canResolve || busy) return
    setBusy(true)
    try {
      await executeTransaction(() => resolveDispute({
        escrowId: dispute.escrowId, freelancerBps: payout * 100, address: onChain.arbiter,
      }), { onStatus: setTransaction })
      await refresh()
    } finally {
      setConfirm(false)
      setBusy(false)
    }
  }

  return (
    <article className="card space-y-3 p-5">
      <h2 className="font-bold">{dispute.projectTitle} · งวด {dispute.milestoneNumber} รอบ {dispute.attemptNumber}</h2>
      <p className="text-sm text-ink-600">ผู้จ้าง {dispute.clientName} · ฟรีแลนซ์ {dispute.freelancerName}
        {dispute.openedAt && ` · เปิดเมื่อ ${formatDate(dispute.openedAt)}`}</p>
      {dispute.submissions.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">รายละเอียดงานที่ส่ง</summary>
          <ul className="mt-2 space-y-3">
            {dispute.submissions.map((submission) => (
              <li key={submission.id} className="space-y-1 border-l border-ink/15 pl-3">
                <p className="font-semibold">{submission.title}</p>
                <p className="whitespace-pre-wrap break-words">{submission.description}</p>
                {submission.feedback && <p className="whitespace-pre-wrap break-words">{submission.feedback}</p>}
                <WorkLinks submission={submission} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {dispute.status === 'resolved' && <p className="text-sm">ข้อพิพาทสิ้นสุดแล้ว</p>}
      {dispute.status === 'refunded' && <p className="text-sm">คืนเงินให้ผู้จ้างแล้ว</p>}
      {!sameDeployment && dispute.status === 'funded' && <InfoBanner tone="warning">ข้อพิพาทนี้อยู่บน Contract คนละชุดกับที่เว็บตั้งค่า</InfoBanner>}
      {matching && onChain.statusName === 'resolved' && <p className="text-sm">ผลบน Sepolia · ฟรีแลนซ์ได้รับ {onChain.payoutBps / 100}% ของค่าจ้าง</p>}
      {error && <ErrorState error={error} onRetry={refresh} />}
      {open && (
        <>
          <p className="break-all text-sm">Wallet ผู้ตัดสิน {onChain.arbiter}</p>
          {isArbiter ? (
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-sm">
                ส่วนแบ่งฟรีแลนซ์ (%)
                <input className="w-32 rounded-lg border border-ink/15 px-3 py-2" type="number" min="0" max="100" step="1"
                  value={percent} disabled={busy} onChange={(event) => setPercent(event.target.value)} />
              </label>
              <Button disabled={!canResolve || busy} onClick={() => setConfirm(true)}>ตัดสินข้อพิพาท</Button>
            </div>
          ) : <InfoBanner>สลับไปยัง Wallet ผู้ตัดสินของข้อพิพาทนี้เพื่อบันทึกคำตัดสิน</InfoBanner>}
        </>
      )}
      <ConfirmDialog open={confirm} loading={busy} onClose={() => { if (!busy) setConfirm(false) }}
        onConfirm={resolve} title="ยืนยันผลการแบ่งเงิน?"
        description={`ฟรีแลนซ์ได้รับ ${payout}% ของค่าจ้าง ผู้จ้างได้รับเงินส่วนที่เหลือคืน ข้อพิพาทและโครงการจะสิ้นสุด`} />
      {transaction && <TransactionStatus {...transaction} />}
    </article>
  )
}

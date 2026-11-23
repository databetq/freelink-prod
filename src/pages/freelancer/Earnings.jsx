import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownToLine, TrendingUp, Wallet } from 'lucide-react'
import { formatEther } from 'ethers'
import { useAuth } from '@/contexts/AuthContext'
import { useWallet } from '@/contexts/WalletContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { transactionService } from '@/services/api/transactionService'
import { projectService } from '@/services/api/projectService'
import { readPendingWithdrawal, withdraw } from '@/services/blockchain/contractService'
import { executeTransaction } from '@/services/blockchain/transactionService'
import { PageHeader } from '@/components/common/PageHeader'
import { StatCard } from '@/components/common/StatCard'
import { Button } from '@/components/common/Button'
import { Modal } from '@/components/common/Modal'
import { StatusBadge } from '@/components/common/StatusBadge'
import { InfoBanner } from '@/components/common/InfoBanner'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { TableSkeleton } from '@/components/common/LoadingSkeleton'
import { WalletConnectButton } from '@/components/wallet/WalletConnectButton'
import { TransactionStatus } from '@/components/wallet/TransactionStatus'
import { transactionStatus, transactionTypes } from '@/constants'
import { formatCurrency, formatDate } from '@/utils/format'
import { cn } from '@/utils/cn'

export default function Earnings() {
  useDocumentTitle('รายได้')
  const { user, profileId } = useAuth()
  const wallet = useWallet()
  const { data, loading, error, refresh } = useAsync(
    () => transactionService.list(user?.id),
    [user?.id],
  )
  const { data: projects } = useAsync(
    () => projectService.listProjects({ role: 'freelancer', profileId }),
    [profileId],
  )

  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [withdrawal, setWithdrawal] = useState(null)
  const walletAddress = wallet.isConnected && !wallet.isWrongNetwork ? wallet.address : null
  const { data: claim, loading: claimLoading, error: claimError, refresh: refreshClaim } = useAsync(async () => (
    walletAddress ? { address: walletAddress, amount: await readPendingWithdrawal(walletAddress) } : null
  ), [walletAddress])
  const pendingAmount = claim && claim.address === walletAddress && !claimError ? claim.amount : null
  const canWithdraw = pendingAmount > 0n && !claimLoading && !busy

  const transactions = data || []
  const fundedProjects = (projects || []).filter((project) => project.escrowStatus === 'funded')
  const inEscrow = fundedProjects.reduce((sum, project) => sum + project.escrowAmount, 0)
  const earnings = transactions.filter((tx) => tx.type === 'earning' && tx.status === 'confirmed')
  const totalEarnings = earnings.reduce((sum, tx) => sum + tx.amount, 0)

  const monthly = useMemo(() => {
    const formatter = new Intl.DateTimeFormat('th-TH', { month: 'short' })
    const now = new Date()
    const buckets = Array.from({ length: 6 }).map((_, index) => {
      const date = new Date(now.getFullYear(), now.getMonth() - (5 - index), 1)
      return {
        key: `${date.getFullYear()}-${date.getMonth()}`,
        label: formatter.format(date),
        total: 0,
      }
    })
    transactions
      .filter((tx) => tx.type === 'earning' && tx.status === 'confirmed')
      .forEach((tx) => {
        const date = new Date(tx.createdAt)
        const bucket = buckets.find((item) => item.key === `${date.getFullYear()}-${date.getMonth()}`)
        if (bucket) bucket.total += tx.amount
      })
    const max = Math.max(1, ...buckets.map((bucket) => bucket.total))
    return { buckets, max }
  }, [transactions])

  const submitWithdrawal = async () => {
    if (!canWithdraw) return
    setBusy(true)
    try {
      await executeTransaction(() => withdraw(walletAddress), { onStatus: setWithdrawal })
      await refreshClaim()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Earnings"
        title="รายได้ของฉัน"
        description="รายได้ที่ยืนยันแล้วและยอดที่รอปล่อยจาก Escrow"
        actions={
          <Button
            variant="brand"
            size="md"
            icon={ArrowDownToLine}
            onClick={() => {
              setWithdrawOpen(true)
              refreshClaim()
            }}
          >
            ถอนยอดค้างจาก Escrow
          </Button>
        }
      />


      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="รายได้ทั้งหมด"
          value={loading || error ? '—' : formatCurrency(totalEarnings)}
          hint="ยอดจากรายการจ่ายที่ยืนยันแล้ว"
          icon={TrendingUp}
          tone="emerald"
        />
        <StatCard
          label="ยอดค้างที่เบิกได้"
          value={claimLoading || pendingAmount === null ? '—' : `${formatEther(pendingAmount)} ETH`}
          hint="ยอดค้างจ่ายของ Wallet ที่เชื่อมอยู่"
          icon={Wallet}
          tone="brand"
        />
        <StatCard
          label="รอปล่อยจาก Escrow"
          value={projects ? formatCurrency(inEscrow) : '—'}
          hint="รอธุรกรรมปล่อยเงินบนเครือข่าย"
          icon={Wallet}
          tone="blue"
        />
        <StatCard
          label="รายการจ่ายที่ยืนยันแล้ว"
          value={loading || error ? '—' : String(earnings.length)}
          hint="นับจากประวัติรายได้"
          icon={ArrowDownToLine}
          tone="violet"
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <section className="card p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold">รายได้ 6 เดือนล่าสุด</h2>

          </div>
          {loading ? <p className="mt-4 text-sm text-ink-500">กำลังโหลดรายได้</p> : error ? (
            <p className="mt-4 text-sm text-ink-500">โหลดข้อมูลรายได้ไม่สำเร็จ</p>
          ) : monthly.buckets.every((bucket) => bucket.total === 0) ? (
            <p className="mt-4 rounded-lg bg-paper p-4 text-sm text-ink-500">
              ยังไม่มีธุรกรรมจ่ายค่าจ้างที่ยืนยันในช่วง 6 เดือนนี้
            </p>
          ) : <div className="mt-5 flex h-44 items-end gap-2 sm:gap-3">
            {monthly.buckets.map((bucket) => {
              const height = Math.round((bucket.total / monthly.max) * 100)
              return (
                <div key={bucket.key} className="flex flex-1 flex-col items-center gap-1.5">
                  <span className="text-[9px] font-semibold text-ink-500">
                    {bucket.total > 0 ? formatCurrency(bucket.total, { compact: true }) : ''}
                  </span>
                  <div className="flex h-32 w-full items-end rounded-lg bg-paper">
                    <div
                      className={cn(
                        'w-full rounded-lg bg-gradient-to-t from-brand-600 to-violet-400 transition-all duration-700',
                        bucket.total === 0 && 'bg-ink/[0.06]',
                      )}
                      style={{ height: `${Math.max(bucket.total > 0 ? 8 : 2, height)}%` }}
                      title={`${bucket.label}: ${formatCurrency(bucket.total)}`}
                    />
                  </div>
                  <span className="text-[10px] text-ink-400">{bucket.label}</span>
                </div>
              )
            })}
          </div>}
        </section>

        <section className="card p-5">
          <h2 className="text-sm font-bold">กระเป๋าเงิน</h2>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-500">
            เมื่อผู้จ้างปล่อยเงิน สัญญาจะโอนค่าจ้างเข้า Wallet ฟรีแลนซ์ตามข้อตกลงโดยตรง
          </p>
          <WalletConnectButton size="md" className="mt-3" />
          <div className="mt-4 space-y-2 border-t border-ink/[0.06] pt-3 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-ink-500">รายได้ยืนยันแล้ว</span>
              <span className="font-semibold text-ink">{loading || error ? '—' : formatCurrency(totalEarnings)}</span>
            </div>
          </div>
          <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-[10px] leading-relaxed text-ink-400">
            หากโอนเข้า Wallet ไม่สำเร็จ สัญญาจะเก็บเป็นยอดค้างที่เบิกได้จากหน้านี้
          </p>
        </section>
      </div>

      <section className="mt-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-bold">รายการล่าสุด</h2>
          <Link to="/freelancer/transactions" className="text-[11.5px] font-semibold text-brand-700 hover:underline">
            ดูทั้งหมด →
          </Link>
        </div>

        {loading ? (
          <TableSkeleton rows={4} />
        ) : error ? (
          <ErrorState error={error} onRetry={refresh} />
        ) : transactions.length === 0 ? (
          <EmptyState
            icon={Wallet}
            title="ยังไม่มีรายการรายได้"
            description="รายได้จะแสดงเมื่อระบบยืนยันธุรกรรมปล่อยค่าจ้างบนเครือข่ายแล้ว"
          />
        ) : (
          <div className="card overflow-hidden">
            <div className="hidden grid-cols-[1.5fr_1.2fr_1fr_0.9fr] gap-4 border-b border-ink/[0.06] bg-paper-soft px-5 py-3 text-[10px] font-semibold uppercase tracking-wide text-ink-400 sm:grid">
              <span>รายการ</span>
              <span>ประเภท</span>
              <span>จำนวน</span>
              <span>สถานะ</span>
            </div>
            <ul className="divide-y divide-ink/[0.06]">
              {transactions.slice(0, 6).map((tx) => {
                const status = transactionStatus[tx.status]
                return (
                  <li key={tx.id} className="grid gap-2 px-5 py-3.5 sm:grid-cols-[1.5fr_1.2fr_1fr_0.9fr] sm:items-center sm:gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-medium text-ink">{tx.note}</p>
                      <p className="mt-0.5 text-[10px] text-ink-400">{formatDate(tx.createdAt)}</p>
                    </div>
                    <div className="text-[11px] text-ink-500">{transactionTypes[tx.type] || tx.type}</div>
                    <div className="text-[12px] font-bold text-ink">{formatCurrency(tx.amount)}</div>
                    <div>
                      <StatusBadge label={status?.label} tone={status?.tone} />
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </section>

      {fundedProjects.length > 0 && (
        <section className="card mt-5 p-5">
          <h2 className="text-sm font-bold">โครงการที่มีเงินรอปล่อยจาก Escrow</h2>
          <ul className="mt-2 divide-y divide-ink/[0.06]">
            {fundedProjects.map((project) => (
              <li key={project.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <Link to={`/freelancer/projects/${project.id}/escrow`} className="font-semibold text-brand-700 hover:underline">
                  {project.title}
                </Link>
                <span>{formatCurrency(project.escrowAmount)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Modal
        open={withdrawOpen}
        onClose={() => { if (!busy) setWithdrawOpen(false) }}
        title="ถอนยอดค้างจาก Escrow"
        description="สัญญาจะโอนยอดค้างทั้งหมดให้ Wallet ที่เชื่อมอยู่เมื่อคุณยืนยันธุรกรรม"
        footer={
          <>
            <Button variant="secondary" onClick={() => setWithdrawOpen(false)} disabled={busy}>
              ปิด
            </Button>
            <Button variant="brand" onClick={submitWithdrawal} loading={busy} disabled={!canWithdraw}>
              ถอนทั้งหมด
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <WalletConnectButton size="sm" />
          {!walletAddress ? <InfoBanner>เชื่อม Wallet และเลือกเครือข่าย Escrow เพื่อดูยอด</InfoBanner>
            : claimLoading ? <InfoBanner>กำลังตรวจยอดจาก Smart Contract</InfoBanner>
            : claimError ? (
              <InfoBanner tone="warning">
                อ่านยอดค้างจาก Smart Contract ไม่สำเร็จ
                <Button onClick={refreshClaim} variant="ghost" size="sm">ลองอีกครั้ง</Button>
              </InfoBanner>
            ) : pendingAmount === 0n ? <InfoBanner>Wallet นี้ไม่มียอดค้างจ่ายจาก Escrow</InfoBanner>
            : pendingAmount !== null && <InfoBanner>ยอดที่เบิกได้ {formatEther(pendingAmount)} ETH</InfoBanner>}
          {withdrawal && <TransactionStatus {...withdrawal} />}
        </div>
      </Modal>
    </div>
  )
}

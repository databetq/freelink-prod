import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { formatEther } from 'ethers'
import { Button } from '@/components/common/Button'
import { ErrorState } from '@/components/common/ErrorState'
import { InfoBanner } from '@/components/common/InfoBanner'
import { PageLoader } from '@/components/common/LoadingSkeleton'
import { PageHeader } from '@/components/common/PageHeader'
import { ReviewPaymentStatus } from '@/components/projects/ReviewPaymentStatus'
import { EscrowPrepareForm } from '@/components/wallet/EscrowPrepareForm'
import { EscrowTerms } from '@/components/wallet/EscrowTerms'
import { WalletConnectButton } from '@/components/wallet/WalletConnectButton'
import { TransactionStatus } from '@/components/wallet/TransactionStatus'
import { contractConfig } from '@/config/contractConfig'
import { useAuth } from '@/contexts/AuthContext'
import { useWallet } from '@/contexts/WalletContext'
import { useAsync } from '@/hooks/useAsync'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { escrowService } from '@/services/api/escrowService'
import { projectService } from '@/services/api/projectService'
import * as contract from '@/services/blockchain/contractService'
import { normalizeWalletError } from '@/services/blockchain/errors'
import { executeTransaction, getExplorerTxUrl, TX_STATUS } from '@/services/blockchain/transactionService'

const labels = {
  prepared: 'รอฝากเงิน', funded: 'ยืนยันการฝากเงินแล้ว', released: 'จ่ายเงินแล้ว',
  refunded: 'คืนเงินแล้ว', resolved: 'ข้อพิพาทสิ้นสุดแล้ว', expired: 'ข้อตกลงหมดอายุ',
}
const txErrors = {
  ESCROW_TX_REVERTED: 'ธุรกรรมถูก revert',
  ESCROW_EVENT_MISMATCH: 'ธุรกรรมนี้ไม่มี event ที่ตรงกับข้อตกลง',
  ESCROW_CONSENT_REQUIRED: 'ไม่มีการยอมรับข้อตกลงของคนจ้างก่อนฝาก',
}
const txMessages = {
  EscrowFunded: 'ยืนยันการฝากเงินแล้ว',
  PaymentReleased: 'ยืนยันการจ่ายเงินแล้ว',
  EscrowRefunded: 'ยืนยันการคืนเงินแล้ว',
  DisputeResolved: 'ยืนยันผลข้อพิพาทแล้ว',
}

export default function EscrowPayment() {
  const { projectId } = useParams()
  return <ProjectEscrow key={projectId} projectId={projectId} />
}

function ProjectEscrow({ projectId }) {
  const { profileId } = useAuth()
  const { data: project, loading, error, refresh } = useAsync(() => projectService.getProject(projectId), [projectId])
  useDocumentTitle(project ? `Escrow · ${project.title}` : 'Escrow')
  if (loading) return <PageLoader />
  if (error || !project) return <ErrorState error={error} onRetry={refresh} />
  return <EscrowWorkspace project={project} isClient={profileId === project.clientId} />
}

function EscrowWorkspace({ project, isClient }) {
  const wallet = useWallet()
  const { data, loading, error, refresh, setData } = useAsync(() => escrowService.get(project.id), [project.id])
  const [selection, setSelection] = useState(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')

  useEffect(() => {
    if (!data || busy) return undefined
    let current = true
    const interval = setInterval(async () => {
      try {
        const updated = await escrowService.get(project.id)
        if (current) setData(updated)
      } catch {
        // Keep showing the last verified agreement while the service is unreachable.
      }
    }, 12000)
    return () => { current = false; clearInterval(interval) }
  }, [project.id, Boolean(data), busy, setData])

  if (loading) return <PageLoader />
  if (error || !data) return <ErrorState error={error} onRetry={refresh} />
  const { agreements, tosText, proposedDeliveryDays, minDeadlineDays, approvedAgreementIds = [], deliverables } = data
  const currentByNumber = new Map(agreements.map((item) => [item.milestoneNumber, item]))
  const activeNumber = [...currentByNumber.values()].filter((item) => item.status === 'released').length + 1
  const active = currentByNumber.get(activeNumber)
  const agreement = agreements.find((item) => item.id === selection) || active || agreements.at(-1)
  const plan = agreements.length ? JSON.parse(agreements[0].termsJson).milestones : null
  const totalMilestones = plan?.length ?? 1
  const needsPreparation = !['cancelled', 'completed'].includes(project.status) && activeNumber <= totalMilestones
    && (!active || ['refunded', 'expired'].includes(active.status))
  const nextReady = needsPreparation && activeNumber > 1 && !active

  async function prepare(payload) {
    setBusy(true)
    setFailure('')
    try {
      const prepared = await escrowService.prepare(project.id, payload)
      setSelection(prepared.id)
      setData(await escrowService.get(project.id))
    } catch (err) {
      setFailure(err.message)
    } finally {
      setBusy(false)
    }
  }

  const reload = async () => setData(await escrowService.get(project.id))
  return (
    <div>
      <PageHeader title="ข้อตกลงและการจ่ายเงิน" description={project.title}
        backTo={`/${isClient ? 'client' : 'freelancer'}/projects/${project.id}`} backLabel="กลับไปโครงการ" />
      <div className="space-y-4">
        {failure && <InfoBanner tone="danger">{failure}</InfoBanner>}
        {isClient && nextReady && <InfoBanner title={`พร้อมเตรียมงวด ${activeNumber}`}>
          ยืนยันการจ่ายเงินงวด {activeNumber - 1} แล้ว คุณเตรียมข้อตกลงงวดนี้ได้ทันที
        </InfoBanner>}
        {isClient && active?.status === 'funded' && activeNumber < totalMilestones && (
          <InfoBanner title={`งวด ${activeNumber + 1} รอการยืนยันการจ่ายงวด ${activeNumber}`}>
            ปุ่มสร้างและดูข้อตกลงจะขึ้นอัตโนมัติเมื่อระบบยืนยันการจ่ายงวดก่อน วันส่งตามแผนคือวันครบกำหนดส่งงาน คุณเตรียมงวดถัดไปได้ทันทีที่ปุ่มขึ้น
          </InfoBanner>
        )}
        {isClient && activeNumber > totalMilestones && <InfoBanner>ยืนยันการจ่ายเงินครบทุกงวดแล้ว</InfoBanner>}
        {!agreement && !isClient && <InfoBanner>รอคนจ้างเตรียมข้อตกลง เมื่อพร้อมแล้วคุณจะเห็นยอด กำหนดส่ง และรายการตรวจรับที่นี่</InfoBanner>}
        {!agreement && isClient && <WalletConnectButton />}
        {!agreement && isClient && wallet.isConnected && !wallet.isWrongNetwork && (
          <LegacyEscrow projectId={project.id} clientAddress={wallet.address} />
        )}
        {isClient && needsPreparation && (
          <EscrowPrepareForm key={`${activeNumber}:${active?.id}`} project={project} agreement={active}
            milestoneNumber={activeNumber} hasPlan={agreements.length > 0} busy={busy} onPrepare={prepare}
            proposedDeliveryDays={proposedDeliveryDays} minDeadlineDays={minDeadlineDays} deliverables={deliverables}
            plannedDeadline={!active ? plan?.[activeNumber - 1]?.deadline : undefined} />
        )}
        {agreements.length > 1 && (
          <label className="block text-sm font-medium">
            งวดและรอบฝากที่แสดง
            <select className="mt-1 block rounded-lg border border-ink/10 bg-white p-2" value={agreement.id}
              onChange={(event) => setSelection(event.target.value)}>
              {agreements.map((item) => <option key={item.id} value={item.id}>งวด {item.milestoneNumber} · รอบ {item.attemptNumber} · {labels[item.status]}</option>)}
            </select>
          </label>
        )}
        {agreement && <AgreementPayment key={agreement.id} agreement={agreement} projectId={project.id}
          isClient={isClient} isActive={agreement.id === active?.id} workApproved={approvedAgreementIds.includes(agreement.id)} tosText={tosText} reload={reload} />}
      </div>
    </div>
  )
}

function AgreementPayment({ agreement, projectId, isClient, isActive, workApproved, tosText, reload }) {
  const wallet = useWallet()
  const terms = JSON.parse(agreement.termsJson)
  const termsHash = contract.hashTerms(agreement.termsJson)
  const matchingHash = termsHash === agreement.termsHash && terms.projectId === projectId
  const sameDeployment = terms.contract === contractConfig.contractAddress?.toLowerCase() && terms.chainId === contractConfig.chainId
  const chainReady = matchingHash && sameDeployment && wallet.isConnected && wallet.chainId === terms.chainId
  const signerReady = chainReady && wallet.address?.toLowerCase() === terms.client
  const freelancerSignerReady = chainReady && wallet.address?.toLowerCase() === terms.freelancer
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [hash, setHash] = useState('')
  const [broadcastHash, setBroadcastHash] = useState(null)
  const [checkedResult, setCheckedResult] = useState(null)
  const [acceptTx, setAcceptTx] = useState(null)
  const { data: chain, loading: chainLoading, error: chainError, refresh: refreshChain } = useAsync(async () => {
    if (!chainReady) return null
    const [onChain, quote] = await Promise.all([
      contract.readEscrow({ escrowId: agreement.expectedEscrowId }),
      agreement.status === 'prepared' ? contract.quote(terms.amountWei) : null,
    ])
    return { onChain, quote }
  }, [chainReady, wallet.address, agreement.id, agreement.status])
  const pending = agreement.transactions.filter((tx) => tx.status === 'pending')
  const checkedTransaction = agreement.transactions.find((tx) => tx.txHash === checkedResult?.txHash) || checkedResult
  const waitingForOwnTransaction = broadcastHash && !agreement.transactions.some((tx) => tx.txHash === broadcastHash && tx.status !== 'pending')
  const deposit = agreement.transactions.find((tx) => tx.event === 'EscrowFunded')
  const onChain = chainReady ? chain?.onChain : null
  const canDeposit = signerReady && agreement.status === 'prepared' && chain?.quote && !onChain && !waitingForOwnTransaction
    && terms.deadline > Date.now() / 1000
  const canRelease = signerReady && agreement.status === 'funded' && ['active', 'submitted'].includes(onChain?.statusName)
  const chainTermsMatch = onChain && onChain.termsHash === termsHash && String(onChain.amount) === terms.amountWei
    && onChain.client.toLowerCase() === terms.client && onChain.freelancer.toLowerCase() === terms.freelancer
  const awaitingAcceptance = agreement.status === 'funded' && onChain?.statusName === 'funded'
  const acceptanceDeadlinePassed = terms.deadline <= Date.now() / 1000
  const canAccept = !isClient && freelancerSignerReady && awaitingAcceptance && chainTermsMatch
    && onChain.deadline === terms.deadline && !acceptanceDeadlinePassed && !chainError && !chainLoading
    && acceptTx?.status !== TX_STATUS.CONFIRMED
  useEffect(() => {
    if (!isClient || !awaitingAcceptance || busy || chainLoading) return undefined
    const timer = setTimeout(refreshChain, 12000)
    return () => clearTimeout(timer)
  }, [isClient, awaitingAcceptance, busy, chainLoading, refreshChain])
  const releaseAwaitingSync = agreement.status === 'funded' && chainTermsMatch && onChain.statusName === 'released'
  let statusLabel = labels[agreement.status]
  if (agreement.status === 'prepared') {
    if (chainTermsMatch) statusLabel = 'พบ Escrow บนเครือข่าย · รอยืนยันในระบบ'
    else if (pending.length > 0) statusLabel = 'กำลังตรวจธุรกรรมบนเครือข่าย'
  }
  if (releaseAwaitingSync) statusLabel = 'ปล่อยเงินแล้วบน Sepolia · รอยืนยันในระบบ'
  const releasePending = releaseAwaitingSync || waitingForOwnTransaction || pending.some((tx) => tx.event === 'PaymentReleased')
  const showReleaseProgress = isActive && agreement.status === 'funded' && (workApproved || releasePending || pending.length > 0)

  async function verify(txHash) {
    const result = await escrowService.recordTransaction(projectId, agreement.id, txHash)
    await reload()
    return result
  }

  async function record(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    setCheckedResult(null)
    try {
      const result = await verify(hash.trim())
      setCheckedResult(result)
      setHash('')
      refreshChain()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function send(isDeposit) {
    setBusy(true)
    setMessage('')
    setCheckedResult(null)
    try {
      if (isDeposit) {
        await escrowService.consent(projectId, { agreementId: agreement.id, termsHash, tosVersion: terms.tosVersion, accepted })
      }
      const tx = isDeposit ? await contract.depositEscrow({
        projectKey: terms.projectKey, clientAddress: terms.client, freelancerAddress: terms.freelancer,
        deadline: terms.deadline, termsHash, amountWei: terms.amountWei, expectedTotal: chain.quote.total,
      }) : await contract.releasePayment({ escrowId: agreement.escrowId, clientAddress: terms.client })
      setBroadcastHash(tx.hash)
      setHash(tx.hash)
      const result = await verify(tx.hash)
      if (result.status === 'rejected') setMessage(txErrors[result.error] || 'ตรวจสอบธุรกรรมไม่ผ่าน')
      setHash('')
      refreshChain()
    } catch (err) {
      setMessage(err.isApiError ? err.message : normalizeWalletError(err).message)
      refreshChain()
    } finally {
      setBusy(false)
    }
  }

  async function acceptWork() {
    if (!canAccept || busy) return
    setBusy(true)
    setMessage('')
    setCheckedResult(null)
    try {
      await executeTransaction(() => contract.acceptEscrow({
        escrowId: agreement.expectedEscrowId,
        freelancerAddress: terms.freelancer,
        termsHash,
        expectedAmountWei: terms.amountWei,
        expectedDeadline: terms.deadline,
      }), { onStatus: setAcceptTx })
      await refreshChain()
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <EscrowTerms agreement={agreement} terms={terms} />
      <section className="card space-y-4 p-5">
        <h2 className="text-sm font-bold">{statusLabel}</h2>
        {!matchingHash && <InfoBanner tone="danger">ไม่สามารถตรวจ hash ของข้อตกลงได้</InfoBanner>}
        {!sameDeployment && <InfoBanner tone="warning">เครือข่ายหรือ Contract Address ของเว็บต่างจากข้อตกลงนี้</InfoBanner>}
        {message && <InfoBanner tone="warning">{message}</InfoBanner>}
        {chainError && <InfoBanner tone="warning">{chainError.message} <Button onClick={refreshChain} variant="ghost" size="sm">อ่านอีกครั้ง</Button></InfoBanner>}
        {sameDeployment && <WalletConnectButton />}
        {chainReady && !chainError && <Button onClick={refreshChain} variant="ghost" size="sm">อ่านสถานะจากเครือข่าย</Button>}
        {isClient && chainReady && !signerReady && <InfoBanner tone="warning">เลือก Wallet คนจ้างที่ระบุในข้อตกลงก่อนเซ็นธุรกรรม</InfoBanner>}
        {awaitingAcceptance && isClient && <InfoBanner>รอฟรีแลนซ์รับงานบน Sepolia ก่อนจึงจะปล่อยเงินได้</InfoBanner>}
        {awaitingAcceptance && !isClient && !freelancerSignerReady && (
          <InfoBanner tone="warning">เลือก Wallet ฟรีแลนซ์ที่ระบุในข้อตกลงเพื่อรับงานบน Sepolia</InfoBanner>
        )}
        {awaitingAcceptance && !isClient && freelancerSignerReady && acceptanceDeadlinePassed && (
          <InfoBanner tone="warning">ข้อตกลงเลยกำหนดส่งแล้ว จึงรับงานบน Sepolia ไม่ได้</InfoBanner>
        )}
        {onChain && !chainTermsMatch && <InfoBanner tone="danger">ข้อมูลบนเครือข่ายไม่ตรงกับข้อตกลง</InfoBanner>}
        {onChain && chainTermsMatch && (
          <p className="text-sm text-ink-600">ยอดฝากรวม {formatEther(onChain.amount + onChain.fee)} ETH · ค่าจ้าง {formatEther(onChain.amount)} ETH · ค่าธรรมเนียม {formatEther(onChain.fee)} ETH{onChain.deadline !== terms.deadline && ' · กำหนดส่งบนเครือข่ายเปลี่ยนจากต้นฉบับ'}</p>
        )}
        {deposit?.feeWei && !onChain && <p className="text-sm text-ink-600">ค่าธรรมเนียมที่ยืนยันแล้ว {formatEther(deposit.feeWei)} ETH</p>}
        {isClient && canDeposit && (
          <div className="space-y-3">
            <p className="text-sm">ยอดฝากรวม {formatEther(chain.quote.total)} ETH · ค่าธรรมเนียม {formatEther(chain.quote.fee)} ETH</p>
            <label className="flex items-start gap-2 text-sm text-ink-600">
              <input className="mt-1" type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <span>ฉันยืนยันข้อตกลงงวดนี้และยอมรับเงื่อนไขการใช้งานฉบับ {terms.tosVersion}<br />{tosText}</span>
            </label>
            <Button variant="brand" loading={busy} disabled={!accepted} onClick={() => send(true)}>ฝากเงินผ่าน MetaMask</Button>
          </div>
        )}
        {showReleaseProgress && (
          <InfoBanner title={workApproved ? 'อนุมัติงานแล้ว' : 'สถานะการปล่อยเงิน'}>
            <ReviewPaymentStatus projectId={projectId} milestoneNumber={agreement.milestoneNumber} showEscrowLink={false} />
          </InfoBanner>
        )}
        {isClient && canRelease && chainTermsMatch && !waitingForOwnTransaction && <Button loading={busy} onClick={() => send(false)}>ปล่อยเงินงวดนี้</Button>}
        {canAccept && (
          <div className="space-y-2">
            <p className="text-sm text-ink-600">ยืนยันรับข้อตกลงงวดนี้บน Sepolia เพื่อให้ผู้จ้างปล่อยเงินได้</p>
            <Button variant="brand" loading={busy} onClick={acceptWork}>รับงานบน Sepolia</Button>
          </div>
        )}
        {!isClient && agreement.status === 'funded' && ['active', 'submitted'].includes(onChain?.statusName) && (
          <InfoBanner>รับงานบน Sepolia แล้ว ผู้จ้างสามารถปล่อยเงินจากหน้าข้อตกลงได้</InfoBanner>
        )}
        {acceptTx && <TransactionStatus {...acceptTx} />}
        {!showReleaseProgress && (pending.length > 0 || releaseAwaitingSync) && (
          <InfoBanner>{releaseAwaitingSync
            ? 'สัญญาบน Sepolia แสดงว่าปล่อยเงินแล้ว ประวัติรายได้จะอัปเดตเมื่อระบบตรวจยืนยันธุรกรรมจากบล็อก finalized'
            : 'ระบบจะอัปเดตสถานะเมื่อตรวจพบธุรกรรมที่ตรงกับข้อตกลงในบล็อกที่ Sepolia ยืนยันขั้นสุดท้าย (finalized) แล้ว'}
          </InfoBanner>
        )}
        <div role="status" className={checkedTransaction ? undefined : 'sr-only'}>
          {checkedTransaction && (
            <InfoBanner tone={checkedTransaction.status === 'rejected' ? 'warning' : 'info'}>
              {checkedTransaction.status === 'pending' && 'ตรวจเลขนี้แล้ว · ระบบยังรอผลตรวจสอบจาก Sepolia'}
              {checkedTransaction.status === 'confirmed' && (txMessages[checkedTransaction.event] || 'ยืนยันธุรกรรมแล้ว')}
              {checkedTransaction.status === 'rejected' && (txErrors[checkedTransaction.error] || 'ตรวจสอบธุรกรรมไม่ผ่าน')}
            </InfoBanner>
          )}
        </div>
        {agreement.transactions.length > 0 && (
          <ul className="space-y-2 text-xs text-ink-600">
            {agreement.transactions.map((tx) => (
              <li key={tx.txHash} className="break-all">
                {getExplorerTxUrl(tx.txHash) ? <a className="underline" href={getExplorerTxUrl(tx.txHash)} target="_blank" rel="noreferrer">{tx.txHash}</a> : tx.txHash}
                <span className="ml-2">{txErrors[tx.error] || (tx.status === 'pending' ? 'รอยืนยัน' : txMessages[tx.event] || 'ตรวจสอบไม่ผ่าน')}</span>
              </li>
            ))}
          </ul>
        )}
        {['prepared', 'funded'].includes(agreement.status) && (
          <details className="text-sm">
            <summary className="cursor-pointer">ตรวจจากเลขธุรกรรม</summary>
            <form className="mt-2 flex flex-wrap gap-2" onSubmit={record}>
              <input className="min-w-56 flex-1 rounded-lg border border-ink/10 px-3" aria-label="เลขธุรกรรม" placeholder="0x…" required
                pattern="0x[0-9a-fA-F]{64}" value={hash} onChange={(event) => setHash(event.target.value)} />
              <Button size="sm" type="submit" variant="secondary" loading={busy}>ตรวจธุรกรรม</Button>
            </form>
          </details>
        )}
      </section>
    </>
  )
}

function LegacyEscrow({ projectId, clientAddress }) {
  const escrowId = contract.getEscrowId({ projectId, clientAddress })
  const { data, refresh } = useAsync(() => contract.readEscrow({ escrowId }), [escrowId])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  if (!data) return null

  async function release() {
    setBusy(true)
    try {
      const tx = await contract.releasePayment({ escrowId, clientAddress })
      setMessage(`ส่งธุรกรรมแล้ว ${tx.hash}`)
      await tx.wait()
      refresh()
    } catch (err) {
      setMessage(normalizeWalletError(err).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <InfoBanner tone="warning" title="พบ Escrow จากขั้นตอนฝากเดิม">
      <p>รายการเดิมยังใช้รหัส {escrowId} และยอด {formatEther(data.amount)} ETH</p>
      {['active', 'submitted'].includes(data.statusName) && <Button size="sm" variant="secondary" loading={busy} onClick={release}>ปล่อยเงินรายการเดิม</Button>}
      {message && <p className="break-all">{message}</p>}
    </InfoBanner>
  )
}

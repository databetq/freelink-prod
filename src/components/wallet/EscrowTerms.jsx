import { formatEther } from 'ethers'
import { Button } from '@/components/common/Button'
import { formatCurrency, formatDate } from '@/utils/format'

export function EscrowTerms({ agreement, terms }) {
  function download() {
    const url = URL.createObjectURL(new Blob([agreement.termsJson], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `freelink-${terms.projectId}-${terms.milestoneNumber}-${terms.attemptNumber}.json`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <section className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold">ข้อตกลงงวด {terms.milestoneNumber} · รอบ {terms.attemptNumber}</h2>
        <Button variant="secondary" size="sm" onClick={download}>ดาวน์โหลด JSON</Button>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-ink-500">ค่าจ้าง</dt><dd>{formatEther(terms.amountWei)} ETH · {formatCurrency(terms.amountThb, { maximumFractionDigits: 2 })}</dd></div>
        <div><dt className="text-ink-500">กำหนดส่ง</dt><dd>{formatDate(new Date(terms.deadline * 1000), { hour: '2-digit', minute: '2-digit' })}</dd></div>
        <div><dt className="text-ink-500">Wallet คนจ้าง</dt><dd className="break-all font-mono text-xs">{terms.client}</dd></div>
        <div><dt className="text-ink-500">Wallet คนรับงาน</dt><dd className="break-all font-mono text-xs">{terms.freelancer}</dd></div>
        <div><dt className="text-ink-500">จำนวนรอบแก้</dt><dd>{terms.revisionPolicy.maxRevisions}</dd></div>
        <div><dt className="text-ink-500">การเผยแพร่</dt><dd>{terms.confidential ? 'งานลับ' : 'เผยแพร่ได้ตามข้อตกลง'}</dd></div>
      </dl>
      <div className="text-sm">
        <h3 className="font-semibold">ขอบเขตงาน</h3>
        <p className="mt-1 whitespace-pre-wrap break-words text-ink-600">{terms.scope}</p>
      </div>
      {terms.deliverables.length > 0 && (
        <div className="text-sm">
          <h3 className="font-semibold">สิ่งที่ต้องส่ง</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-600">
            {terms.deliverables.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
      )}
      <div className="text-sm">
        <h3 className="font-semibold">แผนงวดและรายการตรวจรับ</h3>
        <ol className="mt-1 list-decimal space-y-2 pl-5 text-ink-600">
          {terms.milestones.map((milestone, index) => (
            <li key={index}>
              {milestone.title} · {formatCurrency(milestone.amountThb, { maximumFractionDigits: 2 })}
              {milestone.deadline && (
                <p className="text-ink-500">กำหนดส่งตามแผน {formatDate(new Date(milestone.deadline * 1000), { hour: '2-digit', minute: '2-digit' })}</p>
              )}
              <ul className="list-disc pl-5">
                {milestone.checklist.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}
              </ul>
            </li>
          ))}
        </ol>
      </div>
      <details className="text-xs text-ink-600">
        <summary className="cursor-pointer font-semibold">ข้อมูลบนเครือข่ายและต้นฉบับข้อตกลง</summary>
        <dl className="my-3 space-y-2 break-all">
          <div><dt>เครือข่ายและสัญญา</dt><dd className="font-mono">{terms.chainId} · {terms.contract}</dd></div>
          <div><dt>ผู้ตัดสิน ณ เวลาเตรียมข้อตกลง</dt><dd className="font-mono">{terms.arbiterAtPreparation}</dd></div>
          <div><dt>Terms hash</dt><dd className="font-mono">{agreement.termsHash}</dd></div>
          <div><dt>Escrow ID</dt><dd className="font-mono">{agreement.escrowId || 'รอยืนยันการฝากเงิน'}</dd></div>
        </dl>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-paper p-3">{agreement.termsJson}</pre>
      </details>
    </section>
  )
}

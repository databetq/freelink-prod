import { useState } from 'react'
import { Button } from '@/components/common/Button'
import { allocateMilestones, toSatang } from '@/utils/escrowMilestones'
import { milestoneSchedule } from '@/utils/escrowSchedule'
import { formatCurrency, formatDate } from '@/utils/format'

function localDateTime(timestamp) {
  const date = new Date(Math.ceil(timestamp / 60000) * 60000)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

let nextRow = 0
const emptyMilestone = (autoDeadline) => ({ id: nextRow++, title: '', amountThb: '', autoAmount: true,
  autoDeadline, deadline: '', checklist: '' })
const field = 'w-full rounded-lg border border-ink/10 bg-white px-3 py-2 text-sm'
const money = (amount) => formatCurrency(amount, { maximumFractionDigits: 2 })
const checklistItems = (text) => text.split('\n').map((line) => line.trim()).filter(Boolean)

export function EscrowPrepareForm({ project, agreement, milestoneNumber, hasPlan, busy, onPrepare,
  proposedDeliveryDays, plannedDeadline, minDeadlineMinutes = 10080, deliverables = [] }) {
  const [custom, setCustom] = useState(false)
  const [deadline, setDeadline] = useState('')
  const [deadlineError, setDeadlineError] = useState('')
  const [milestones, setMilestones] = useState([])
  const [planStart, setPlanStart] = useState(0)
  const [confidential, setConfidential] = useState(true)
  const isSplit = milestones.length > 0
  const canUseProposal = !hasPlan && Boolean(proposedDeliveryDays)
  const minLeadMs = minDeadlineMinutes * 60000
  const minDays = minDeadlineMinutes / 1440
  const minLeadLabel = Number.isInteger(minDays) ? `${minDays} วัน` : `${minDeadlineMinutes} นาที`
  const earliest = Date.now() + minLeadMs
  const canUsePlan = plannedDeadline * 1000 >= earliest
  const useCustomDeadline = custom || (!canUseProposal && !canUsePlan)
  const minimum = localDateTime(earliest)
  const budget = toSatang(project.budget)
  const allocation = isSplit ? allocateMilestones(budget, milestones) : null
  const deliveryDays = Math.max(proposedDeliveryDays || 0, Math.floor(minDays) + 1)
  const schedule = isSplit ? milestoneSchedule(milestones, planStart, earliest, deliveryDays) : null

  function update(id, key, value) {
    setMilestones((items) => items.map((item) => item.id === id ? { ...item, [key]: value } : item))
    if (key === 'deadline' || key === 'checklist') setDeadlineError('')
  }

  function chooseAmountMode(id, autoAmount, calculatedAmount) {
    setMilestones((items) => items.map((item) => item.id === id ? {
      ...item, autoAmount,
      amountThb: !autoAmount && calculatedAmount !== null ? (calculatedAmount / 100).toFixed(2) : item.amountThb,
    } : item))
  }

  function changeRows(items) {
    setMilestones(items)
    setDeadlineError('')
  }

  function beginSplit() {
    setPlanStart(Math.ceil(Date.now() / 60000) * 60000)
    changeRows([emptyMilestone(canUseProposal), emptyMilestone(canUseProposal)])
  }

  function changeDeadlineMode(item, index, autoDeadline) {
    const calculated = schedule.dates[index]
    setMilestones((items) => items.map((row) => row.id === item.id ? {
      ...row, autoDeadline,
      deadline: !autoDeadline && Number.isFinite(calculated) ? localDateTime(calculated) : row.deadline,
    } : row))
    setDeadlineError('')
  }

  function submit(event) {
    event.preventDefault()
    const payload = { milestoneNumber, confidential }
    if (isSplit) {
      if (allocation.error || schedule.errors.some(Boolean)) return
      if (schedule.dates[0] < Date.now() + minLeadMs) {
        setDeadlineError(`กำหนดส่งงวดแรกต้องห่างจากตอนนี้อย่างน้อย ${minLeadLabel} กรุณาตรวจสอบวันส่งอีกครั้ง`)
        return
      }
      const checklists = milestones.map((item) => checklistItems(item.checklist))
      const invalidChecklist = checklists.findIndex((items) => !items.length || items.length > 30 || items.some((item) => item.length > 200))
      if (invalidChecklist !== -1) {
        setDeadlineError(`งวด ${invalidChecklist + 1} ต้องมีรายการตรวจรับ 1–30 ข้อ ข้อละไม่เกิน 200 ตัวอักษร`)
        return
      }
      payload.milestones = milestones.map(({ title }, index) => ({
        title,
        amountThb: (allocation.amounts[index] / 100).toFixed(2),
        deadline: Math.floor(schedule.dates[index] / 1000),
        checklist: checklists[index],
      }))
    } else if (useCustomDeadline) {
      const selected = Date.parse(deadline)
      if (!Number.isFinite(selected) || selected < Date.now() + minLeadMs) {
        setDeadlineError(`เลือกวันและเวลาส่งงานที่ห่างจากตอนนี้อย่างน้อย ${minLeadLabel}`)
        return
      }
      payload.deadline = Math.floor(selected / 1000)
    }
    onPrepare(payload)
  }

  return (
    <form onSubmit={submit} className="card space-y-4 p-5">
      <div>
        <h2 className="text-sm font-bold">{isSplit ? 'เตรียมข้อตกลงแบ่งจ่าย' : agreement ? 'เตรียมรอบฝากใหม่' : `เตรียมข้อตกลงงวด ${milestoneNumber}`}</h2>
        {!hasPlan && <p className="mt-1 text-sm text-ink-500">ค่าจ้างรวม {money(project.budget)}</p>}
      </div>
      {!isSplit && <div className="space-y-2 text-sm">
        <h3 className="font-semibold">กำหนดส่งงานของงวดนี้</h3>
        {(canUseProposal || canUsePlan) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <label className="inline-flex items-center gap-1.5">
              <input type="radio" name="deadline-mode" checked={!custom} onChange={() => { setCustom(false); setDeadlineError('') }} />
              {canUsePlan ? 'ใช้กำหนดส่งตามแผน' : `ตามข้อเสนอ ${proposedDeliveryDays} วัน`}
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input type="radio" name="deadline-mode" checked={custom} onChange={() => setCustom(true)} />
              เลือกวันเอง
            </label>
          </div>
        )}
        {plannedDeadline && (
          <p className="text-ink-500">
            ตามแผน {formatDate(new Date(plannedDeadline * 1000), { hour: '2-digit', minute: '2-digit' })}
            {!canUsePlan && ` · เหลือไม่ถึง ${minLeadLabel} กรุณาเลือกกำหนดส่งใหม่สำหรับรอบนี้`}
          </p>
        )}
        {useCustomDeadline ? (
          <label className="block space-y-1">
            <span>วันและเวลาส่งงาน</span>
            <input className={field} type="datetime-local" required min={minimum} value={deadline}
              onChange={(event) => { setDeadline(event.target.value); setDeadlineError('') }} />
            <span className="block text-ink-500">{canUsePlan ? 'วันใหม่จะใช้ในข้อตกลงรอบนี้' : `เลือกได้ตั้งแต่อีก ${minLeadLabel}`}</span>
          </label>
        ) : canUseProposal && (
          <p className="text-ink-500">
            {proposedDeliveryDays < minDays
              ? `ข้อตกลงนี้จะใช้ระยะเวลาขั้นต่ำ ${minLeadLabel} แม้ข้อเสนอจะระบุ ${proposedDeliveryDays} วัน`
              : 'ระบบจะแสดงวันส่งจริงเมื่อสร้างข้อตกลง โดยนับจากตอนเตรียมข้อตกลง'}
          </p>
        )}
      </div>}
      {!hasPlan && (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confidential} onChange={(event) => setConfidential(event.target.checked)} />
            งานนี้เป็นความลับ
          </label>
          {!isSplit && (
            <Button variant="secondary" size="sm" onClick={beginSplit}>
              แบ่งจ่ายหลายงวด
            </Button>
          )}
          {isSplit && (
            <div className="space-y-3">
              <p className="text-sm text-ink-500">งวดแรกไม่เกิน 30% และงวดสุดท้ายไม่น้อยกว่า 30% ระบบแบ่งยอดที่เหลือให้งวดที่เลือกคำนวณอัตโนมัติ</p>
              {canUseProposal && <p className="text-sm text-ink-500">
                คำนวณวันส่งตามข้อเสนอ {proposedDeliveryDays} วัน โดยแบ่งช่วงระหว่างวันที่เลือกเอง
                {deliveryDays > proposedDeliveryDays && ` · ใช้ ${deliveryDays} วันสำหรับการคำนวณเพื่อให้งวดแรกห่างอย่างน้อย ${minLeadLabel}`}
              </p>}
              {milestones.map((item, index) => (
                <fieldset key={item.id} className="space-y-2 rounded-lg border border-ink/10 p-3">
                  <legend className="px-1 text-sm font-semibold">งวด {index + 1}</legend>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="space-y-1 text-sm">ชื่องวด<input className={field} required maxLength={200} value={item.title} onChange={(event) => update(item.id, 'title', event.target.value)} /></label>
                    <label className="space-y-1 text-sm">
                      <span>วิธีกำหนดยอด</span>
                      <select className={field} value={item.autoAmount ? 'auto' : 'manual'}
                        onChange={(event) => chooseAmountMode(item.id, event.target.value === 'auto', allocation.amounts[index])}>
                        <option value="auto">คำนวณอัตโนมัติ</option>
                        <option value="manual">กำหนดเอง</option>
                      </select>
                    </label>
                    {item.autoAmount ? (
                      <div className="space-y-1 text-sm">
                        <div>ยอดงวด</div>
                        <output className={`${field} block bg-ink/[0.03]`}>
                          {allocation.amounts[index] === null ? '—' : money(allocation.amounts[index] / 100)}
                        </output>
                      </div>
                    ) : (
                      <label className="space-y-1 text-sm">จำนวนบาท<input className={field} type="number" required min="0.01" step="0.01" value={item.amountThb} onChange={(event) => update(item.id, 'amountThb', event.target.value)} /></label>
                    )}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {canUseProposal && <label className="space-y-1 text-sm">
                      <span>วิธีกำหนดวันส่ง</span>
                      <select className={field} value={item.autoDeadline ? 'auto' : 'manual'}
                        onChange={(event) => changeDeadlineMode(item, index, event.target.value === 'auto')}>
                        <option value="auto">คำนวณอัตโนมัติ</option>
                        <option value="manual">เลือกวันเอง</option>
                      </select>
                    </label>}
                    {item.autoDeadline ? <div className="space-y-1 text-sm">
                      <div>วันและเวลาส่งงาน</div>
                      <output className={`${field} block`}>
                        {Number.isFinite(schedule.dates[index]) ? formatDate(new Date(schedule.dates[index]), { hour: '2-digit', minute: '2-digit' }) : 'รอคำนวณ'}
                      </output>
                    </div> : <label className="space-y-1 text-sm">
                      <span>วันและเวลาส่งงาน</span>
                      <input className={field} type="datetime-local" required min={minimum} value={item.deadline}
                        aria-invalid={Boolean(schedule.errors[index] && item.deadline)}
                        onChange={(event) => update(item.id, 'deadline', event.target.value)} />
                      <span className="block text-ink-500">{index ? `เลือกหลังงวด ${index}` : `เลือกได้ตั้งแต่อีก ${minLeadLabel}`}</span>
                    </label>}
                  </div>
                  {schedule.errors[index] && <p className="text-sm text-rose-600">{schedule.errors[index]}</p>}
                  <label className="block space-y-1 text-sm">
                    <span>รายการตรวจรับ (บรรทัดละหนึ่งข้อ)</span>
                    <textarea className={field} required rows={2} value={item.checklist}
                      placeholder="เช่น ลองส่งฟอร์มติดต่อแล้วอีเมลเข้ากล่องบริษัท"
                      onChange={(event) => update(item.id, 'checklist', event.target.value)} />
                  </label>
                  {deliverables.length > 0 && <label className="block space-y-1 text-sm">
                    <span>เพิ่มสิ่งที่ต้องส่งจากประกาศ</span>
                    <select className={field} value="" onChange={(event) => update(item.id, 'checklist', [...checklistItems(item.checklist), event.target.value].join('\n'))}>
                      <option value="">เลือกทีละรายการ แล้วปรับข้อความได้</option>
                      {[...new Set(deliverables)].map((value) => <option key={value} value={value} disabled={checklistItems(item.checklist).includes(value)}>{value}</option>)}
                    </select>
                  </label>}
                  {milestones.length > 2 && <Button variant="ghost" size="sm" onClick={() => changeRows(milestones.filter((row) => row.id !== item.id))}>ลบงวดนี้</Button>}
                </fieldset>
              ))}
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" disabled={milestones.length >= 12} onClick={() => changeRows([...milestones, emptyMilestone(canUseProposal)])}>เพิ่มงวด</Button>
                <Button variant="ghost" size="sm" onClick={() => changeRows([])}>กลับไปจ่ายงวดเดียว</Button>
              </div>
              <div aria-live="polite" className="rounded-lg bg-paper p-3 text-sm">
                <p className="font-semibold">ยอดรวมทุกงวด {money((budget - allocation.remaining) / 100)} · {allocation.remaining < 0 ? 'เกินงบ' : 'คงเหลือ'} {money(Math.abs(allocation.remaining) / 100)}</p>
                {allocation.error && <p className="mt-1 text-rose-600">{allocation.error}</p>}
              </div>
            </div>
          )}
        </>
      )}
      {deadlineError && <p role="alert" className="text-sm text-rose-600">{deadlineError}</p>}
      <Button type="submit" variant="brand" loading={busy} disabled={Boolean(allocation?.error || schedule?.errors.some(Boolean))}>สร้างและดูข้อตกลง</Button>
    </form>
  )
}

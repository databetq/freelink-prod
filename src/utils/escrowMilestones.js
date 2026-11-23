export function toSatang(value) {
  if (!/^\d*(?:\.\d{1,2})?$/.test(String(value)) || value === '') return null
  const satang = Math.round(Number(value) * 100)
  return Number.isSafeInteger(satang) ? satang : null
}

export function allocateMilestones(budget, milestones) {
  const firstMax = Math.floor(budget * 3 / 10)
  const lastMin = Math.ceil(budget * 3 / 10)
  const last = milestones.length - 1
  const amounts = milestones.map((item) => item.autoAmount ? null : toSatang(item.amountThb))
  const automatic = milestones.flatMap((item, index) => item.autoAmount ? [index] : [])
  const unallocated = budget - amounts.reduce((sum, amount) => sum + (amount ?? 0), 0)

  if (milestones.some((item, index) => !item.autoAmount && !(amounts[index] > 0))) {
    return { amounts, remaining: unallocated, error: 'กรอกยอดที่มากกว่า 0 บาทในงวดที่กำหนดเอง' }
  }
  if (amounts[0] > firstMax || (amounts[last] !== null && amounts[last] < lastMin)) {
    return { amounts, remaining: unallocated, error: 'งวดแรกต้องไม่เกิน 30% และงวดสุดท้ายต้องไม่น้อยกว่า 30%' }
  }
  if (!automatic.length) {
    return { amounts, remaining: unallocated, error: unallocated === 0 ? '' : 'ยอดทุกงวดรวมกันต้องเท่ากับค่าจ้าง' }
  }

  // Apply the first and last limits before sharing the rest, in whole satang.
  const manualAmounts = amounts.slice()
  let remaining = unallocated
  if (automatic[0] === 0 && remaining / automatic.length > firstMax) {
    amounts[automatic.shift()] = firstMax
    remaining -= firstMax
  }
  if (automatic.at(-1) === last && remaining / automatic.length < lastMin) {
    amounts[automatic.pop()] = lastMin
    remaining -= lastMin
  }
  if (remaining < automatic.length || (!automatic.length && remaining !== 0) || amounts[0] === 0) {
    return { amounts: manualAmounts, remaining: unallocated,
      error: 'ยอดที่เหลือแบ่งอัตโนมัติตามเงื่อนไขไม่ได้ ลองปรับยอดที่กำหนดเองหรือจำนวนงวด' }
  }

  if (automatic.length) {
    const share = Math.floor(remaining / automatic.length)
    const extra = remaining % automatic.length
    automatic.forEach((index, position) => {
      amounts[index] = share + (position >= automatic.length - extra ? 1 : 0)
    })
  }
  return { amounts, remaining: 0, error: '' }
}

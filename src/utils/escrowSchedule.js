export const DAY_MS = 86400000
const MINUTE_MS = 60000

export function milestoneSchedule(rows, start, minimum, deliveryDays) {
  const dates = rows.map((row) => row.autoDeadline ? null : Date.parse(row.deadline))
  const errors = rows.map(() => '')
  const firstMinute = Math.ceil(minimum / MINUTE_MS)
  let previousIndex = -1
  let previousTime = start / MINUTE_MS
  for (const [index, date] of dates.entries()) {
    const last = index === dates.length - 1
    if (date === null && !last) continue
    if (Number.isNaN(date)) {
      errors[index] = 'เลือกวันและเวลาส่งงาน'
      break
    }
    const end = date === null ? (start + deliveryDays * DAY_MS) / MINUTE_MS : date / MINUTE_MS
    const steps = index - previousIndex
    const firstAllowed = Math.max(firstMinute, previousTime + 1)
    if (end < firstAllowed + steps - 1) {
      errors[index] = date === null
        ? 'ระยะเวลาที่เหลือจัดวันส่งอัตโนมัติไม่ได้ ลองเลือกวันส่งงวดสุดท้ายเอง'
        : steps === 1 && previousIndex === -1
          ? 'เลือกวันส่งตั้งแต่วันและเวลาขั้นต่ำที่แสดง'
          : 'เลือกวันส่งให้ช้าลงเพื่อให้ทุกงวดก่อนหน้ามีวันส่งตามลำดับ'
      break
    }
    const firstEven = previousTime + (end - previousTime) / steps
    const first = Math.max(firstAllowed, firstEven)
    let prior = previousTime
    for (let offset = 1; offset < steps; offset++) {
      const ideal = first + (end - first) * (offset - 1) / (steps - 1)
      const minutesPerDay = DAY_MS / MINUTE_MS
      const wholeDay = previousTime + Math.round((ideal - previousTime) / minutesPerDay) * minutesPerDay
      const lower = Math.max(firstAllowed, prior + 1)
      const upper = end - (steps - offset)
      prior = wholeDay >= lower && wholeDay <= upper ? wholeDay : Math.min(upper, Math.max(lower, Math.round(ideal)))
      dates[previousIndex + offset] = prior * MINUTE_MS
    }
    dates[index] = end * MINUTE_MS
    previousIndex = index
    previousTime = end
  }
  return { dates, errors }
}

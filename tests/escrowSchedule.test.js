import assert from 'node:assert/strict'
import test from 'node:test'
import { DAY_MS, milestoneSchedule } from '../src/utils/escrowSchedule.js'

const start = Date.UTC(2026, 10, 23, 12)
const atDay = (day) => start + day * DAY_MS
const auto = { autoDeadline: true }
const manual = (day) => ({ autoDeadline: false, deadline: new Date(atDay(day)).toISOString() })
const schedule = (rows, duration = 118) => milestoneSchedule(rows, start, atDay(7), duration)

test('divides the proposed duration and keeps the last day', () => {
  assert.deepEqual(schedule([auto, auto, auto]), { dates: [39, 79, 118].map(atDay), errors: ['', '', ''] })
  assert.deepEqual(schedule([auto, auto]).dates, [59, 118].map(atDay))
})

test('fills only the gaps between manually chosen dates', () => {
  assert.deepEqual(schedule([manual(50), auto, auto]).dates, [50, 84, 118].map(atDay))
  assert.deepEqual(schedule([auto, manual(50), auto, manual(100)]).dates, [25, 50, 75, 100].map(atDay))
})

test('validates minimum, order, and a fixed date past the proposed end', () => {
  assert.ok(schedule([manual(6), auto]).errors[0])
  assert.ok(schedule([manual(50), manual(50)]).errors[1])
  assert.ok(schedule([manual(119), auto]).errors[1])
  assert.ok(schedule([auto, { autoDeadline: false, deadline: '' }]).errors[1])
})

test('can fit twelve milestones on a short valid schedule', () => {
  const { dates, errors } = schedule(Array(12).fill(auto), 8)
  assert.ok(errors.every((error) => !error))
  assert.equal(dates[0], atDay(7))
  assert.equal(dates.at(-1), atDay(8))
  assert.ok(dates.every((date, index) => !index || date > dates[index - 1]))
})

# แผนปรับระบบ Freelink สำหรับเดโมส่งงาน (contract V2)

ฉบับ 2 · 24 พฤศจิกายน 2026 · ปรับตามคำตอบของเจ้าของโปรเจกต์ เอกสารนี้เป็นแผนอย่างเดียว ยังไม่มีโค้ดถูกแก้

> เอกสารนี้ระบุจุดอ่อนที่ยังไม่ได้แก้ ถ้าจะเปิด repo เป็น public ให้แก้จุดเหล่านั้นหรือย้ายไฟล์นี้ออกก่อน

ขนาดงาน: **S** ไม่เกินครึ่งวัน · **M** 1–2 วัน · **L** 3–5 วัน (ประมาณคร่าว ๆ ต่อคนเดียว)

---

## 0. แผน 1 วัน (ส่ง 25 พ.ย. 2026) — ทำตามข้อนี้ก่อน

ข้อ 1–13 เป็นแผนเต็ม ใช้ต่อหลังส่งหรืออ้างอิงในรายงาน

| # | งาน | ใคร | เวลาคร่าว ๆ |
|---|---|---|---|
| 1 | ย้าย repo + tag `demo-safe` (จุดย้อนกลับ) | เจ้าของ | 30 นาที |
| 2 | deploy โค้ดปัจจุบัน Vercel + Render + Neon (ข้อ 9) | โค้ด: Claude / ตั้งค่า: เจ้าของ | 2–3 ชม. |
| 3 | ปุ่ม contract ครบในหน้า escrow อ่านสถานะจาก chain โดยตรง + `ESCROW_CONFIRMATIONS` ยืนยันราว 40 วิ | Claude | 3–4 ชม. |
| 4 | แก้ทางตัน: แก้/ลบงานที่จ้างแล้ว, อนุมัติหลังคืนเงิน, ข้อพิพาทจบแล้วจบโปรเจกต์, ปล่อย/เบิกเงินแล้วโปรเจกต์ปิด | Claude | 1–2 ชม. |
| 5 | deploy V2 เวลาสั้น (ข้อ 10) ใช้ private key ของเจ้าของ | เจ้าของ | 30 นาที |
| 6 | ทดสอบด้วย MetaMask 2 กระเป๋าบนเว็บจริง | เจ้าของ + Claude แก้ | 2 ชม. |
| 7 | โครงการตัวอย่าง, README, วิดีโอสำรอง | ช่วยกัน | 1–2 ชม. |
| ถ้าทัน | หน้าแอดมินตัดสินข้อพิพาท (`resolveDispute`) | Claude | 1–2 ชม. |

ทางลัดของข้อ 3: backend ฟัง event จบงาน (จ่าย/คืน/ตัดสิน) อยู่แล้ว จึงเพิ่มปุ่มได้โดยไม่แก้ schema ปุ่มใช้ตาราง 5.6 ตรวจจาก `getEscrow`

**ตัดออกจาก 1 วัน:** คอลัมน์ `stage`, draft ของงานก่อนเซ็น, ตารางข้อพิพาท, แจ้งเตือน, ยกเลิกโปรเจกต์, CI, ลบไฟล์ Counter

**เกณฑ์หยุด:** deploy ไม่ผ่านภายในเที่ยงวันที่ 24 → เดโมบนเครื่อง + วิดีโอ · หยุดเพิ่มโค้ด 22:00 น. วันที่ 24 หลังจากนั้นแก้เฉพาะของพัง · ถ้าพังหนักกลับไป `demo-safe`

---

## 1. เป้าหมาย

อาจารย์เปิดลิงก์เดียวแล้วตรวจงานได้เอง ทุกเส้นทางหลักของ contract V2 ทำได้จากหน้าเว็บบน Sepolia ไม่ต้องรอหลายวัน และไม่มีสถานะที่กดแล้วตัน ไม่ใช่การเปิดใช้จริง

หลักที่ใช้ตัดสินใจ

1. **Contract คือความจริงเรื่องเงิน** DB เก็บสำเนาที่อ่านจาก chain ปุ่มในเว็บไม่เปลี่ยนสถานะเงินเอง
2. **บันทึกก่อนเซ็น** เก็บเนื้อหาใน DB ก่อนแล้วค่อยเซ็น MetaMask ถ้าปิดเบราว์เซอร์กลางทาง worker ตามเก็บจาก event ได้
3. **ไม่ส่งข้อความส่วนตัวขึ้น chain** ขึ้นแค่ hash กับรหัสสั้น
4. **deploy ตั้งแต่ต้น แล้วค่อยเติมฟีเจอร์** เพื่อเจอปัญหา cookie และเซิร์ฟเวอร์หลับก่อนวันส่ง
5. ไม่ย้ายโฟลเดอร์ใหญ่ เพราะทีมแก้พร้อมกันอยู่

---

## 2. ข้อตัดสินใจ

| # | เรื่อง | สรุป | ที่มา |
|---|---|---|---|
| 1 | Contract | **V2 เท่านั้น** ตัด V3 ออกจากแผน | เจ้าของตอบ |
| 2 | ปุ่ม "อนุมัติ" กับ "ปล่อยเงิน" | **แยกปุ่มเหมือนเดิม** เก็บการรวมปุ่มเป็นไอเดีย (ข้อ 13) | เจ้าของตอบ |
| 3 | ข้อพิพาทจบ | **จบทั้งโปรเจกต์** เพิ่มสถานะ `resolved` งวดที่เหลือยกเลิก | เจ้าของตอบ |
| 4 | โฮสต์ | **Vercel (เว็บ) + Render (API และ worker) + Neon (ฐานข้อมูล)** VPS xver.cloud เป็นทางสุดท้าย | เจ้าของตอบ + ตรวจเอกสารแล้ว |
| 5 | ขอบเขต | **เดโมส่งอาจารย์** ตัดงานสำหรับผู้ใช้จริงออก (ข้อ 13) | เจ้าของตอบ |
| 6 | งานรายชั่วโมง | ซ่อนตัวเลือก | ค่าเริ่มต้น |
| 7 | ยกเลิกโปรเจกต์ | ปิดประกาศ แล้วมีปุ่ม "ประกาศใหม่จากงานนี้" | ค่าเริ่มต้น |
| 8 | กระเป๋าผู้ตัดสิน / owner / ค่าธรรมเนียม | 3 กระเป๋า ตั้งตอน deploy สัญญาเดโม | ค่าเริ่มต้น |
| 9 | repo | private ระหว่างทำ แล้วเชิญอาจารย์ หรือเปิด public ตอนส่งหลังลบรหัสเดโม | ค่าเริ่มต้น |

### ขอบเขต

| กลุ่ม | งาน | ขนาด |
|---|---|---|
| **A ต้องมี** | A1 ย้าย repo (ข้อ 4) | S |
| | A2 deploy ระบบปัจจุบันขึ้นก่อน (ข้อ 9) | M |
| | A3 ต่อ contract ให้ครบวงจรงาน (ข้อ 5) | L+L |
| | A4 โหมดเดโม: สัญญาเวลาสั้น + ยืนยันเร็ว (ข้อ 10) | M |
| | A5 บั๊กที่คนตรวจเจอได้ง่าย (ข้อ 7) | 2–4 วัน |
| | A6 ชุดสำหรับอาจารย์ตรวจ (ข้อ 11) | S–M |
| **B ควรมี** | B1 ข้อพิพาทแบบย่อ (ข้อ 6) | L |
| | B2 แจ้งเตือน escrow (ข้อ 8) | M |
| | B3 แก้ข้อความค้าง, verify contract บน Etherscan | S+S |

รวมกลุ่ม A ราว 11–19 วันทำงานต่อคน กลุ่ม B ราว 5–8 วัน แบ่ง 3 คนทำขนานกันได้

---

## 3. โครงสร้างเป้าหมาย

`+` ไฟล์ใหม่ · `~` แก้ · `-` ลบ · (B) ทำในกลุ่ม B

```
freelink-prod/
├─ + vercel.json                     /api → Render และ SPA fallback
├─ ~ .gitignore                      เพิ่ม __pycache__/ *.pyc
├─ + .github/workflows/ci.yml        เทสต์ contract + backend + frontend ทุก PR
├─ ~ README.md                       หน้าแรกสำหรับอาจารย์ (ข้อ 11)
├─ backend/
│   ├─ + .python-version             3.12
│   ├─ app/
│   │   ├─ ~ escrow_chain.py         event เพิ่ม 6 ตัว, อ่าน getEscrow ครบ struct, ตั้งระดับการยืนยันได้
│   │   ├─ ~ escrow.py               reconcile แยก "สถานะเงิน" กับ "ขั้นงาน"
│   │   ├─ ~ escrow_worker.py        sync ขั้นงาน, รวม getLogs, ไม่ล้มทั้ง process
│   │   ├─ + project_state.py        คำนวณสถานะโปรเจกต์จากข้อตกลง ที่เดียว
│   │   ├─ + work.py                 ย้าย submissions/approve/revision ออกจาก marketplace.py
│   │   ├─ + disputes.py             (B) ข้อพิพาทแบบย่อ
│   │   └─ ~ marketplace.py, models.py, schemas.py, config.py, db.py, main.py, transactions.py, create_account.py
│   └─ migrations/versions/
│       ├─ + 0015 escrow stage + work hash + สถานะโปรเจกต์ resolved
│       └─ + 0016 (B) disputes
├─ src/
│   ├─ ~ services/api/apiClient.js                timeout ยาวขึ้น + ข้อความปลุกเซิร์ฟเวอร์
│   ├─ ~ services/blockchain/contractService.js   resolveDispute + ระบุ signer ทุกคำสั่ง
│   ├─ ~ config/contractConfig.js                 เพิ่ม resolveDispute
│   ├─ + utils/escrowActions.js                   ตารางว่าใครกดอะไรได้ (pure function มีเทสต์)
│   ├─ + hooks/useEscrowChain.js                  อ่าน escrow + policy + เวลาบล็อก
│   ├─ + components/escrow/                       EscrowActions, EscrowTimeline, RefundDialog, PendingWithdrawalCard, (B) DisputeDialog
│   ├─ + pages/admin/AdminDisputes.jsx            (B)
│   └─ ~ EscrowPayment, SubmitWork, ReviewWork, ProjectDetails, WalletPage, Earnings, EscrowPrepareForm, constants
├─ tests/  + escrowActions.test.js
└─ smart-contact/
    ├─ - contracts/Counter.sol, Counter.t.sol, test/Counter.ts, ignition/modules/Counter.ts, scripts/send-op-tx.ts
    └─ ~ .env, .env.example          ค่าเวลาสั้นสำหรับเดโม และ ESCROW_ADDRESS ใหม่
```

---

## 4. A1 — เก็บงานและย้าย repo (S) ต้องทำก่อนทุกอย่าง

ตอนนี้ `backend/` ทั้งโฟลเดอร์ไม่อยู่ใน git (ไม่มี git ซ้อน เป็น repo เดียวทั้งโปรเจกต์)

- [ ] เพิ่ม `__pycache__/` และ `*.pyc` ใน `.gitignore` หลัก (ตอนนี้ `scripts/__pycache__` จะติดไปด้วย)
- [ ] ตั้ง repo ใหม่เป็น private
- [ ] commit ทุกอย่าง → เปลี่ยน remote → push `main`
- [ ] เพิ่มเพื่อนเป็น collaborator และส่ง `.env` 3 ไฟล์ให้กันทางช่องส่วนตัว

ข้อห้าม: ไม่ใช้ `git push --mirror` (มี ref ชั่วคราวของเครื่องมือ 137 ตัวใน `refs/t3/`), ไม่รัน `git init` ใน `backend/` และไม่รันชุดคำสั่ง "create a new repository" ของ GitHub เพราะ commit แค่ README

---

## 5. A3 — ต่อ contract ให้ครบวงจรงาน (L+L) สำคัญที่สุด

### 5.1 ฐานข้อมูล (migration 0015)

คง `escrow_agreements.status` ไว้เป็น **สถานะเงิน** (`prepared / funded / released / refunded / resolved / expired`) เพราะมีโค้ดเช็ก `funded` มากกว่า 12 จุดทั้งสองฝั่ง แล้วเพิ่ม **ขั้นงาน** แยกต่างหาก

| ตาราง | เพิ่ม |
|---|---|
| `escrow_agreements` | `stage` (`awaiting_acceptance / active / submitted / disputed`, null เมื่อยังไม่ฝากหรือจบแล้ว), `chain_deadline`, `review_ends_at`, `disputed_at`, `revision_count`, `payout_bps`, `arbiter_address`, `synced_block` |
| `work_submissions` | `work_hash`, `manifest_json`, `tx_hash`, `chain_submitted_at`, สถานะ `draft`, `feedback_hash` |
| `projects` | ค่า `resolved` ใน CHECK, `closed_reason` |
| `escrow_transactions` | `sender`, `checked_at` ใช้หมดอายุรายการ pending |

ข้อมูลเดิม 3 ข้อตกลงเป็น `released` ทั้งหมด จึงไม่ต้อง backfill

### 5.2 ชั้นอ่าน chain — `escrow_chain.py`

- [ ] เพิ่ม `EscrowAccepted`, `WorkSubmitted`, `RevisionRequested`, `DisputeOpened`, `PayoutDeferred`, `Withdrawn`
- [ ] `Event.decode` บังคับความยาว `32 * จำนวนฟิลด์` ซึ่งใช้ไม่ได้กับ event ที่มี `string` (`RevisionRequested`, `DisputeOpened`) ต้องตรวจความยาวเฉพาะ event ที่เป็น static
- [ ] เพิ่ม `read_escrow(contract, key, block)` ถอด struct 12 ฟิลด์ (static ทั้งหมด = 12 คำ) แทนการอ่านแค่คำแรกใน `is_occupied`
- [ ] `policy()` อ่าน `reviewPeriod`, `arbiterTimeout`, `revisionPeriod` เพิ่ม
- **กับดัก:** ถ้าเพิ่ม event ใน `EVENTS` อย่างเดียว dict ที่ `escrow.py:386` จะ KeyError → ถูกแปลงเป็น 503 → worker วนซ้ำไม่จบ ต้องแก้พร้อมกัน

### 5.3 reconcile และ worker

- [ ] event เปลี่ยนสถานะเงินเฉพาะ FUNDED / RELEASED / REFUNDED / RESOLVED ที่เหลือบันทึกประวัติอย่างเดียว
- [ ] ขั้นงานไม่คำนวณจาก event ทีละตัว ให้อ่าน `getEscrow` ที่บล็อกซึ่งยืนยันแล้ว (ดูข้อ 10) แล้วเขียนทับ `stage` และเวลาต่าง ๆ (ถ้า event หลุดก็ยังถูก)
- [ ] ตรวจตัวเอง: ถ้า `getEscrow` บอกว่าจบแล้วแต่ DB ยัง `funded` ให้ปรับตาม chain และ log เป็น error
- [ ] `PayoutDeferred` ไม่มี escrowId ให้อ่านจาก receipt เดียวกับ event จบงาน แล้วแจ้งผู้รับให้ไปกดถอน
- [ ] รวม `eth_getLogs` เป็นครั้งเดียวต่อ contract (ส่ง escrowId เป็นรายการใน topic ที่ 2) และไม่ถือ row lock ระหว่างรอ RPC
- [ ] `main()` จับทุก exception พร้อม backoff ตอนนี้ TypeError/ValueError จาก `EscrowChain.__init__` ทำ worker ตายได้
- [ ] รายการ pending: ไม่เกิน 5 ต่อข้อตกลง, ไม่พบบน chain เกิน 24 ชม. → `rejected`, ขึ้น `pending_verification` เฉพาะเมื่อพบธุรกรรมจริงที่ส่งถึง contract จากกระเป๋าคู่สัญญา

### 5.4 สถานะโปรเจกต์คำนวณจากที่เดียว — `project_state.py`

เรียกทุกครั้งที่ข้อตกลงหรือการส่งงานเปลี่ยน แทนการตั้ง `project.status` กระจายหลาย endpoint

| ข้อตกลงงวดปัจจุบัน | `project.status` | งานส่งล่าสุด |
|---|---|---|
| ไม่มี / prepared / expired / refunded | `active` (รอฝาก) | — |
| funded + awaiting_acceptance | `active` (รอรับงาน) | — |
| funded + active, `revision_count` = 0 | `active` | — |
| funded + active, `revision_count` > 0 | `revision` | `revision` |
| funded + submitted | `in_review` | `pending` |
| funded + submitted และผู้จ้างอนุมัติแล้ว | งวดสุดท้าย `completed` (แสดง "รอปล่อยเงิน") งวดอื่น `active` | `approved` |
| funded + disputed | `disputed` | คงเดิม |
| released แต่ยังมีงวดต่อ | `active` | `approved` อัตโนมัติ |
| released ครบทุกงวด | `completed`, job → `closed` | `approved` อัตโนมัติ |
| resolved | `resolved`, job → `closed` | คงเดิม |
| ผู้ใช้ยกเลิก | `cancelled`, job → `closed` | — |

ตารางนี้ปิดบั๊ก: ปล่อยเงินก่อนส่งงานแล้วค้าง, คืนเงินแล้วยังอนุมัติได้, ข้อพิพาทจบแล้วตัน และกรณีฟรีแลนซ์เบิกเองแล้วโปรเจกต์ไม่จบ

### 5.5 ขั้นตอนของแต่ละปุ่ม

**ส่งงาน**
1. `POST /projects/{id}/submissions` → เก็บ `draft` + ไฟล์ คืน `manifestJson`, `workHash`, `escrowId`
   - `workHash = keccak256(NFC(JSON เรียงคีย์ {v, agreementId, submissionId, title, description, links, files:[{name,size,sha256}]}))`
   - เงื่อนไข: อ่าน latest แล้วเป็น Active, ยังไม่เลย deadline **บน chain**
2. เว็บคำนวณ hash ซ้ำจาก `manifestJson` เทียบก่อนเซ็น → `submitWork(escrowId, workHash)` ด้วยกระเป๋าในข้อตกลง
3. `POST /escrow/transactions` หรือ worker เจอ `WorkSubmitted` → draft ที่ hash ตรงกลายเป็น `pending`, แจ้งผู้จ้าง, ลบ draft อื่นของงวดนั้น
4. ปฏิเสธใน MetaMask → draft ยังอยู่ กดเซ็นต่อได้
5. พบการส่งงานบน chain ที่ไม่มีไฟล์ในระบบ → แสดงคำเตือนให้ผู้จ้าง ยังปล่อยเงินหรือพิพาทได้

**ขอแก้งาน** เก็บ feedback + hash → `requestRevision(escrowId, "freelink:rev:v1:<hash>")` → `RevisionRequested` → งานเป็น `revision`, อัปเดต `chain_deadline`, แจ้งฟรีแลนซ์ จำนวนรอบอ่านจาก `revisionCount` บน chain

**อนุมัติ** (หน้าตรวจรับงาน) เพิ่มการตรวจว่า agreement ยัง `funded` และขั้นเป็น active/submitted แล้วพาไปหน้า escrow เหมือนเดิม

**ปล่อยเงิน** (หน้าข้อตกลงและการจ่ายเงิน) `releasePayment` เมื่อยืนยันแล้วงานที่ค้างตรวจเป็น `approved` อัตโนมัติ และถ้าผู้จ้างอนุมัติแล้วไม่ปล่อย ฟรีแลนซ์เบิกเองได้เมื่อพ้นช่วงตรวจ

**เบิกเอง** `claimAfterReview` แสดงตัวนับถอยหลังจาก `review_ends_at`

**คืนเงิน / ยกเลิก / ปฏิเสธรับงาน** `refundClient` ปุ่มเดียวแต่ข้อความต่างกันตามบทบาทและสถานะ

**ถอนยอดค้าง** ย้ายจาก Earnings มาเป็นการ์ดในหน้า Wallet ใช้ได้ทั้งสองบทบาท

### 5.6 ใครกดอะไรได้เมื่อไหร่ — `src/utils/escrowActions.js`

ใช้เวลาบล็อกล่าสุด ไม่ใช้นาฬิกาเครื่อง และใช้ deadline จาก chain (ถูกขยายได้ตอนขอแก้)

| ขั้นบน chain | เงื่อนไข | ผู้จ้าง | ฟรีแลนซ์ |
|---|---|---|---|
| Funded | ก่อน deadline | ยกเลิกรับเงินคืน | รับงาน · ปฏิเสธ (คืนเงิน) |
| Funded | ถึง/เลย deadline | ยกเลิกรับเงินคืน | ปฏิเสธ (คืนเงิน) |
| Active รอบแรก | ไม่เลย deadline | ปล่อยเงิน · พิพาท | ส่งงาน · พิพาท · ยอมคืนเงิน |
| Active รอบแรก | เลย deadline | ปล่อยเงิน · **ขอเงินคืน** · พิพาท | ยอมคืนเงิน |
| Active หลังขอแก้ | ไม่เลย deadline | ปล่อยเงิน · พิพาท | ส่งงานแก้ · พิพาท · ยอมคืนเงิน |
| Active หลังขอแก้ | เลย deadline | ปล่อยเงิน · พิพาท (ขอคืนเองไม่ได้) | ยอมคืนเงิน |
| Submitted | ในช่วงตรวจ | อนุมัติ · ปล่อยเงิน · ขอแก้ n/2 · พิพาท | รอ · ยอมคืนเงิน |
| Submitted | พ้นช่วงตรวจ | อนุมัติ · ปล่อยเงิน | **เบิกค่าจ้าง** · ยอมคืนเงิน |
| Disputed | ยังไม่ครบเวลาผู้ตัดสิน | ยอมปล่อยเงินเต็ม | ยอมคืนเงินเต็ม |
| Disputed | ครบเวลาผู้ตัดสินแล้ว | ยอมปล่อย · แบ่งครึ่ง | ยอมคืน · แบ่งครึ่ง |

ผู้ตัดสิน: `resolveDispute` เฉพาะ Disputed และกระเป๋าตรงกับ `arbiter` ที่ล็อกตอนเปิดข้อพิพาท

### 5.7 งานฝั่งหน้าเว็บ

- [ ] `contractService.js` เพิ่ม `resolveDispute`; ฟังก์ชัน `submitWork`, `requestRevision`, `claimAfterReview`, `refundClient`, `openDispute`, `settleExpiredDispute` ตอนนี้ไม่ระบุ address ที่ต้องเซ็น ให้รับ `signerAddress` ทุกตัว
- [ ] `useEscrowChain` ใช้ร่วมกันใน EscrowPayment, SubmitWork, ReviewWork, ProjectDetails
- [ ] `SubmitWork.jsx` เป็น 3 ขั้น: บันทึก → เซ็น → ยืนยัน และกลับมาทำต่อได้
- [ ] `ReviewWork.jsx` แสดงว่า hash ของงานตรงกับ chain หรือไม่ + เวลาตรวจที่เหลือ
- [ ] `constants` เพิ่มป้ายขั้นงาน และ `cancelled`, `resolved` (ตอนนี้ไม่มี `cancelled`)
- [ ] `WalletPage` ลิงก์ตามบทบาท (ตอนนี้พาผู้จ้างไปหน้าฟรีแลนซ์)
- [ ] `transactions.py` แสดงผลข้อพิพาทที่แบ่งเงินและยอดที่ถอน (ตอนนี้ `DisputeResolved` คืน None)

### 5.8 เกณฑ์ผ่าน A3

- 8 จาก 11 ฟังก์ชันใช้ได้จากหน้าเว็บ (3 ฟังก์ชันข้อพิพาทอยู่ B1) และ backend ติดตาม event วงจรงานครบ 10
- ปิดเบราว์เซอร์ทันทีหลังเซ็น แล้วสถานะยังอัปเดตเองเมื่อ worker เห็นธุรกรรม
- เส้นทางที่ผ่านจริง: ปกติ · ขอแก้ 2 รอบ · ผู้จ้างเงียบแล้วฟรีแลนซ์เบิก · ไม่รับงานแล้วยกเลิก · เลย deadline แล้วคืนเงิน · หลายงวด

---

## 6. B1 — ข้อพิพาทแบบย่อ (L)

ใช้ฟังก์ชัน contract ครบ 3 ตัว แต่ไม่ทำระบบหลักฐานเต็ม

**ฐานข้อมูล (0016)** ตารางเดียว `disputes` — agreement (unique), ผู้เปิด, `reason_code`, คำชี้แจงของสองฝ่าย, `reason_hash`, `opened_at`, `arbiter_address`, `expires_at`, `ruling_bps`, คำวินิจฉัย, แอดมินที่ตัดสิน, `by_timeout` และชนิดแจ้งเตือน `dispute`

| เส้นทาง | ใคร |
|---|---|
| `POST /projects/{id}/disputes` เก็บเหตุผลก่อนเซ็น `openDispute` | คู่สัญญา |
| `PATCH /projects/{id}/disputes/statement` อีกฝ่ายชี้แจงได้ 1 ครั้ง | คู่สัญญา |
| `GET /admin/disputes`, `POST /admin/disputes/{id}/ruling` เก็บเหตุผลและ % ก่อนเซ็น | แอดมิน |

- [ ] คู่สัญญา: ปุ่มเปิดข้อพิพาท, นับถอยหลัง, ยอมแพ้, แบ่งครึ่งเมื่อครบเวลา
- [ ] แอดมิน: ดูข้อตกลง + งานที่ส่ง + คำชี้แจงสองฝ่าย → เลือก % (มีปุ่มลัด 0/50/100) → เห็นยอดที่แต่ละฝ่ายได้ → เชื่อมกระเป๋าผู้ตัดสินแล้วเซ็น `resolveDispute`
- [ ] % บน chain ไม่ตรงกับที่บันทึก → เตือนและใช้ค่าจาก chain
- [ ] จบแล้วโปรเจกต์เป็น `resolved` และ job → `closed` (ข้อตัดสินใจ 3)

หลักฐานเพิ่มเติมใช้ ticket แจ้งปัญหาที่มีอยู่แล้ว

**เกณฑ์ผ่าน:** เปิดจากทั้งสองฝ่าย → ตัดสิน 0 / 60 / 100% → ยอดตรง และกรณีผู้ตัดสินเงียบแบ่งครึ่งได้

---

## 7. A5 — บั๊กที่ต้องแก้ก่อนให้ตรวจ

| # | ปัญหา | จุด | วิธีแก้ | ขนาด |
|---|---|---|---|---|
| 1 | งานที่จ้างจบแล้วเปิดรับใหม่ได้ | `marketplace.py:205` | แก้ได้เฉพาะงานที่ยังไม่มีโปรเจกต์ | S |
| 2 | ลบงานที่มีโปรเจกต์ได้ 503 | `:227` | ตอบ 409 และซ่อนปุ่ม | S |
| 3 | อนุมัติหลังคืนเงิน, ปล่อยเงินก่อนส่งงานแล้วค้าง, ข้อพิพาทจบแล้วตัน | `marketplace.py:600`, `escrow.py:186` | แก้ใน A3 (5.4) | — |
| 4 | tx hash ปลอมไม่จำกัด | `escrow.py:393` | แก้ใน A3 (5.3) | — |
| 5 | ยกเลิกโปรเจกต์ไม่ได้ | ใหม่ | `POST /projects/{id}/cancel` เมื่อไม่มีเงินล็อกและ key บน chain ว่าง | M |
| 6 | ยอมรับข้อตกลงหลังยกเลิกได้ | `escrow.py:267` | `consent` ตรวจสถานะโปรเจกต์ | S |
| 7 | จ้างคนที่ถูกระงับ / งานของคนที่ถูกระงับยังแสดง | `marketplace.py:339`, `job_query` | ตรวจสถานะบัญชีทั้งสองจุด | S |
| 8 | เสนอราคาเกินงบไม่จำกัด | `marketplace.py:263` | ไม่เกินงบสูงสุด | S |
| 9 | งานรายชั่วโมงคิดเป็นเหมา | ฟอร์มลงงาน | ซ่อนตัวเลือกและปฏิเสธใน API | S |
| 10 | ลิงก์ในหน้า Wallet พาผู้จ้างไปหน้าฟรีแลนซ์ | `WalletPage.jsx:187` | ลิงก์ตามบทบาท | S |

ทุกข้อต้องมีเทสต์ที่ล้มกับโค้ดเดิมก่อน

---

## 8. B2 และ B3 — แจ้งเตือนและข้อความค้าง

- [ ] แจ้งเตือนในเว็บ: ฝากแล้วให้ไปรับงาน · รับงานแล้ว · ส่งงาน · ขอแก้ · ปล่อยเงิน · คืนเงิน · มียอดให้ถอน · เปิด/ตัดสินข้อพิพาท (ใช้ `notify()` ชนิด `payment` ที่มีอยู่แล้วแต่ไม่เคยถูกใช้)
- [ ] ข้อความค้าง: `HowItWorks.jsx:239`, `JobDetails.jsx:378`, `AuthLayout.jsx:9`, FAQ ที่บอกว่ามีแค่ Google, Settings ที่แสดง "Google" ทุกบัญชี, README หลักและ backend
- [ ] verify ซอร์สของสัญญาเดโมบน Etherscan ให้อาจารย์อ่านโค้ดและ event ได้

---

## 9. A2 — Deploy: Vercel + Render + Neon (M)

ทำทันทีหลังย้าย repo ด้วยโค้ดปัจจุบัน ยังไม่ต้องรอฟีเจอร์

```
เบราว์เซอร์ ── https://<ชื่อ>.vercel.app
                ├─ /            ไฟล์เว็บ (Vite dist) เปิดทันที
                └─ /api/*       rewrite ──► https://<ชื่อ>.onrender.com/*
                                             └─ Render Web Service (ฟรี) 1 ตัว
                                                 ├─ uvicorn
                                                 └─ escrow worker ในเครื่องเดียวกัน ──► RPC Sepolia
                                             └──────► Neon PostgreSQL (Singapore)
```

เบราว์เซอร์เห็นโดเมนเดียว cookie `SameSite=Lax` เดิมจึงควรใช้ได้โดยไม่ต้องแก้

### 9.1 ข้อจำกัดที่ตรวจจากเอกสารแล้ว (พ.ย. 2026)

| บริการ | ข้อจำกัด | ผลกับเรา | รับมือ |
|---|---|---|---|
| Render ฟรี | ไม่มี background worker และ cron | worker แยกตัวไม่ได้ | รัน worker ใน Web Service เดียวกัน |
| | หลับเมื่อไม่มีคนเข้า 15 นาที ตื่นราว 1 นาที | คำขอแรกช้า และ worker หยุดระหว่างหลับ | worker จำตำแหน่งบล็อกใน DB (`next_scan_block`) ตื่นแล้วตามเก็บเอง หลับ 1 วัน ≈ 7,200 บล็อก ใช้ราว 4 นาที |
| | 0.1 CPU / RAM 512 MB | ล็อกอินด้วยรหัสผ่านช้า (hash ใช้ CPU 0.15 วิบนเครื่องพัฒนา คาดว่า 1.5–3 วิ) | ยอมรับได้ วัดจริงตอน deploy |
| | 750 ชม./เดือน, ไม่มี shell, ไม่มี pre-deploy command | รัน migration แยกไม่ได้ | ใส่ `alembic upgrade head` ใน start command สร้างแอดมินจากเครื่องตัวเอง |
| | Postgres ฟรี **ลบหลัง 30 วัน** (ผ่อน 14 วัน) ไม่มี backup | ฐานข้อมูลอาจหายก่อนอาจารย์ตรวจ | ใช้ Neon แทน |
| Neon ฟรี | 100 CU-ชม./เดือน = 400 ชม.ที่ 0.25 CU, 1 GB | ถ้าปลุกค้าง 24 ชม. หมดในราว 17 วัน (worker ถาม DB ทุก 15 วิ) | ปล่อยให้หลับตามปกติ ปลุกค้างเฉพาะวันนำเสนอ |
| Vercel Hobby | ใช้แบบไม่เชิงพาณิชย์, rewrite รอได้ 120 วิ | พอสำหรับ Render ตื่น | — |
| | cache คำตอบจากปลายทางตาม header (โปรเจกต์ใหม่เปิดอัตโนมัติ) | ข้อมูลผู้ใช้ไม่ควรถูก cache | ตั้ง `x-vercel-enable-rewrite-caching: 0` และ API ส่ง `Cache-Control: no-store` |
| | private repo: เอกสารสองหน้าขัดกันว่า commit ของเพื่อน deploy ได้ไหม | อาจ deploy ไม่ขึ้น | ทดสอบ 1 ครั้ง ถ้าติดให้เจ้าของ repo เป็นคน merge |

ที่มา: [Render free](https://render.com/docs/free) · [Vercel rewrites](https://vercel.com/docs/rewrites) · [Vercel limits](https://vercel.com/docs/limits) · [Vercel collaboration](https://vercel.com/docs/deployments/troubleshoot-project-collaboration) · [Neon plans](https://neon.com/docs/introduction/plans)

### 9.2 ตั้งค่า

**Neon** สร้างโปรเจกต์ที่ Singapore ใช้ connection string แบบ **direct** (ไม่มี `-pooler`) เปลี่ยนหัวเป็น `postgresql+psycopg://` และลงท้าย `?sslmode=require`

**Render** Web Service จาก repo ใหม่
- Root Directory `backend` · Region Singapore · Health check `/health`
- Build `pip install -r requirements.txt`
- Start (ทดสอบรูปแบบคำสั่งใน bash แล้ว)
  ```
  alembic upgrade head && (while true; do python -m app.escrow_worker; sleep 5; done &) && uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```
- Env: `PYTHON_VERSION`, `DATABASE_URL`, `FRONTEND_ORIGIN=https://<ชื่อ>.vercel.app`, `SESSION_SECRET` (32 ตัวขึ้นไป สร้างใหม่), `SESSION_COOKIE_SECURE=true`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://<ชื่อ>.vercel.app/api/auth/google/callback`, `ESCROW_CHAIN_ID`, `ESCROW_CONTRACT_ADDRESS`, `ESCROW_THB_PER_ETH`, `ESCROW_RPC_URL` (คีย์ของตัวเอง)

**Vercel** import repo เดียวกัน framework Vite
- `vercel.json`: rewrite `/api/:path*` → Render **ต้องอยู่ก่อน** `/(.*)` → `/index.html`
- Env: `VITE_API_BASE_URL=/api`, `VITE_CHAIN_ID=11155111`, `VITE_CONTRACT_ADDRESS`, `VITE_EXPLORER_URL`
- ใช้เฉพาะ URL production เพราะ backend ตรวจ origin ตรงตัว ลิงก์ preview จะล็อกอินไม่ได้

**Google Console** เพิ่ม redirect URI ใหม่ ถ้าอยู่โหมด Testing ให้เพิ่มอีเมลอาจารย์เป็น test user

**แอดมิน** รันจากเครื่องตัวเองโดยตั้ง `DATABASE_URL` ของ Neon ชั่วคราวแล้ว `npm run init:admin`

### 9.3 โค้ดที่ต้องแก้เพื่อโฮสต์นี้ (S)

- [ ] `apiClient.js:21` timeout 20 วิ สั้นกว่าเวลาที่ Render ตื่น → 90 วิ + ข้อความ "กำลังปลุกเซิร์ฟเวอร์"
- [ ] `db.py` `connect_timeout` 3 วิ → ตั้งค่าได้ (10 วิ) เพราะ Neon ต้องตื่น
- [ ] `main.py` ใส่ `Cache-Control: no-store` เป็นค่าเริ่มต้นของ API
- [ ] `create_account.py:18` เอา `DEMO_PASSWORD` ออกจากโค้ด รับจาก env แทน

### 9.4 ต้องทดสอบทันทีหลัง deploy ครั้งแรก

| ทดสอบ | ถ้าไม่ผ่าน |
|---|---|
| ล็อกอินแล้วรีเฟรชยังอยู่ (cookie ผ่าน rewrite) | ใช้ทาง 2 ใน 9.5 |
| Google Login ครบรอบ | ตรวจ redirect URI ก่อน แล้วใช้ทาง 2 |
| แนบไฟล์รวม 5 MB (เอกสารไม่ระบุเพดานของ rewrite) | ลดเพดานไฟล์ หรือให้ส่งเป็นลิงก์ |
| เรียก API ตอน Render หลับ ได้ JSON ไม่ใช่หน้า HTML รอโหลด | เรียก `/api/health` ตอนเปิดเว็บและรอจนพร้อม |
| deploy commit ของเพื่อน | เจ้าของ repo เป็นคน merge |
| ฝากเงิน 1 รายการ แล้ว worker บน Render อัปเดตสถานะ | ดู log ของ Render |

### 9.5 ทางสำรองเรียงลำดับ

1. Vercel + Render + Neon (แผนหลัก)
2. **Render ตัวเดียว** ให้ FastAPI เสิร์ฟไฟล์ `dist` เอง โดเมนเดียวแท้ ๆ ไม่มี proxy แลกกับหน้าเว็บต้องรอเซิร์ฟเวอร์ตื่นด้วย
3. **VPS xver.cloud** ใช้เมื่อสองทางแรกไม่ผ่าน หรือต้องเปิดค้างตลอดโดยไม่มีช่วงตื่น: Docker Compose (Caddy + api + worker + postgres)

---

## 10. A4 — โหมดเดโม (M)

สัญญา V2 ตัวปัจจุบันตั้งช่วงตรวจ 7 วัน รอผู้ตัดสิน 14 วัน แก้ไม่ได้ และทุกสถานะเงินรอบล็อก finalized ราว 13–15 นาที อาจารย์จะตรวจไม่จบในครั้งเดียว

- [ ] **deploy V2 โค้ดเดิมอีกชุด** ด้วยเวลาสั้น ไม่แก้ Solidity แค่ตั้งใน `smart-contact/.env`
  `REVIEW_PERIOD_SECONDS=900` · `REVISION_PERIOD_SECONDS=900` · `ARBITER_TIMEOUT_SECONDS=1200` · `ARBITER_ADDRESS` และ `FEE_RECIPIENT_ADDRESS` คนละกระเป๋า
- [ ] **`MIN_DEADLINE_DAYS` ตั้งค่าได้** (`escrow.py:32` และ `EscrowPrepareForm.jsx`) เดโมใช้ขั้นต่ำ 10 นาที
- [ ] **ระดับการยืนยันตั้งค่าได้** `ESCROW_CONFIRMATIONS` เดโมใช้ latest ย้อน 3 บล็อก (ราว 40 วิ) ค่าเริ่มต้นยังเป็น finalized แก้ 3 จุดที่เรียก `chain.block()` และข้อความ "finalized" ในหน้าเว็บ
- [ ] ใช้ฐานข้อมูลใหม่กับ address ใหม่ ข้อตกลงเดิม 3 รายการจ่ายจบแล้วและยอดในสัญญาเดิมเป็น 0 จึงเปลี่ยนได้ปลอดภัย

เขียนในรายงานว่าเวลาสั้นและการยืนยัน 3 บล็อกใช้เฉพาะเดโม ของจริงใช้ 7/14 วันและ finalized

---

## 11. A6 — ชุดสำหรับอาจารย์ตรวจ (S–M)

- [ ] **README หน้าแรก**: ลิงก์เว็บ, ลิงก์สัญญาบน Etherscan, "เปิดครั้งแรกรอราว 1 นาที", ขั้นตอนตรวจ 10 นาที
- [ ] **บัญชีทดสอบ 3 บทบาท** รหัสส่งให้อาจารย์ทางส่วนตัว ไม่อยู่ใน repo
- [ ] **กระเป๋าทดสอบ** สร้างใหม่สำหรับงานนี้ มี Sepolia ETH พอใช้ ไม่เคยถือเงินจริง
- [ ] **โครงการตัวอย่างครบทุกสถานะ**: รอฝาก · รอรับงาน · กำลังทำ · รอตรวจ · ขอแก้ · พิพาท · จ่ายแล้ว · คืนเงินแล้ว
- [ ] **ตารางเทียบ** ฟังก์ชัน contract 11 ตัว → หน้าเว็บ → ปุ่ม → tx ตัวอย่างบน Etherscan
- [ ] **วิดีโอสำรอง 3–5 นาที** เผื่อ RPC หรือ Render ล่มวันนำเสนอ
- [ ] เช้าวันนำเสนอ: ปลุกเซิร์ฟเวอร์, เช็กยอด ETH, ลองฝาก 1 รายการ

---

## 12. ลำดับทำ

| PR | เนื้อหา | กลุ่ม | ต้องรอ |
|---|---|---|---|
| 01 | ย้าย repo, `.gitignore`, CI ขั้นต้น | A1 | — |
| 02 | `vercel.json` + แก้ 9.3 + deploy ครั้งแรก + ทดสอบ 9.4 | A2 | 01 |
| 03 | migration 0015 + `escrow_chain` + reconcile + worker + `ESCROW_CONFIRMATIONS` | A3, A4 | 01 |
| 04 | `project_state.py` + แยก `work.py` | A3 | 03 |
| 05 | `escrowActions.js` + `useEscrowChain` + `contractService` | A3 | 01 (คู่กับ 03 ได้) |
| 06 | ส่งงาน / ขอแก้ / อนุมัติ / ปล่อยเงิน | A3 | 04, 05 |
| 07 | คืนเงิน / เบิกเอง / ถอน + หน้า Wallet | A3 | 04, 05 |
| 08 | สัญญาเวลาสั้น + deadline ขั้นต่ำ | A4 | 03 |
| 09 | บั๊กข้อ 7 | A5 | 04 |
| 10 | ข้อพิพาทแบบย่อ | B1 | 06, 07 |
| 11 | แจ้งเตือน + ข้อความค้าง + verify Etherscan | B2, B3 | 06, 07 |
| 12 | ชุดสำหรับอาจารย์ + ซ้อมทั้งเส้นทาง | A6 | 02–09 |

**แบ่งคน:** 1 = 03, 04, 09 (backend/chain) · 2 = 05, 06, 07 (หน้าเว็บ) · 3 = 01, 02, 08, 12 (deploy/เดโม) · ใครว่าง = 10, 11
**ไฟล์ที่ชนกันง่าย:** `marketplace.py`, `models.py`, `constants/index.js` ให้ PR 04 เข้าก่อน

ทุก PR เพิ่มบันทึกบนสุดของ `backend/IMPLEMENTATION_LOG.md`

### ถ้าเวลาไม่พอ
ตัดจากล่างขึ้นบน: B2 → B1 → A5 ข้อ 7, 8 → A5 ข้อ 5, 6 อย่าตัด PR 02, 08, 12 เพราะเป็นส่วนที่ทำให้อาจารย์ตรวจได้

---

## 13. เก็บไว้เป็นไอเดีย / ไม่ทำในเดโม

**ไอเดียที่เก็บไว้:** รวมปุ่ม "อนุมัติงาน" (หน้าตรวจรับงาน) กับ "ปล่อยเงินงวดนี้" (หน้าข้อตกลงและการจ่ายเงิน) เป็นปุ่มเดียว เพื่อไม่ให้โครงการขึ้นว่าเสร็จทั้งที่ยังไม่จ่าย หลังต่อ `submitWork` แล้วความเสี่ยงลดลง เพราะฟรีแลนซ์เบิกเองได้เมื่อพ้นช่วงตรวจ

**เขียนในรายงานเป็นงานต่อยอด:** contract V3 (ผู้ตัดสินสำรอง, คืนค่าธรรมเนียม, รอบแก้ต่องาน), audit, ยืนยันอีเมล/ลืมรหัสผ่าน/2FA, Terms/PDPA, เตือน 72/24 ชม., rate limit, backup, monitoring, แบ่งหน้า API, แชต realtime, ไฟล์แนบข้อเสนอ, แอดมินถอดประกาศ, หลักฐานข้อพิพาทเต็มรูปแบบ, งานรายชั่วโมง

**ไม่ทำ:** ย้าย `src/` ไป `frontend/`, เปลี่ยนชื่อ `smart-contact/`, เปลี่ยน framework, ERC-20 / หลายเชน / รับเงินบาทจริง

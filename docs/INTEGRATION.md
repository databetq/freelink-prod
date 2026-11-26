# Integration Checklist — Backend & Solidity

เอกสารนี้สำหรับเพื่อนร่วมทีมที่รับผิดชอบ **Backend, Database และ Solidity Smart Contract**
Frontend เรียก FastAPI REST API ผ่าน service layer ข้อมูลจำลองสำหรับทดสอบอยู่ใน `tests/fixtures/`

> ⚠️ Endpoint, response shape, ABI, address, chain id และชื่อฟังก์ชันทั้งหมดในตอนนี้เป็น **ข้อเสนอ/placeholder** ยังไม่ได้รับการยืนยัน ห้ามถือว่าเป็นสัญญาที่ตกลงแล้ว

---

## 1. สิ่งที่ต้องส่งให้ Frontend

### Backend
- [ ] Base URL ของ API แต่ละ environment (dev / staging / prod)
- [ ] API documentation หรือ OpenAPI/Swagger
- [ ] รูปแบบ Authentication (Bearer token? cookie? OAuth callback?)
- [ ] Response envelope ที่ใช้จริง เช่น `{ data, meta }` หรือ raw object
- [ ] Error format มาตรฐาน (code, message, field errors)
- [ ] Pagination / filter / sort contract ของ `GET /jobs`
- [ ] Role & permission rules (client / freelancer / admin)
- [ ] URL ของไฟล์อัปโหลด, วิธีการส่ง (Multipart/form-data หรือ Signed URL), และข้อจำกัดขนาด/ชนิดไฟล์
- [ ] CORS ที่อนุญาต origin ของ frontend (ระบุ list ของ domain ที่อนุญาต)

### Smart Contract
- [ ] Contract Address (แยกตาม network)
- [ ] ABI (ไฟล์ JSON หรือ artifact)
- [ ] Chain ID / Network name / RPC URL สาธารณะ
- [ ] ชื่อฟังก์ชันและ parameter ของ escrow ทุกตัว
- [ ] Event definitions และชื่อ event (เช่น `EscrowFunded`, `WorkSubmitted`, `PaymentReleased`)
- [ ] สกุลเงินที่ใช้ (native หรือ ERC-20) + address + decimals
- [ ] เงื่อนไขการฝาก / ปล่อยเงิน / คืนเงิน / dispute
- [ ] ผู้มีสิทธิ์เรียกฟังก์ชัน (client, freelancer, platform, admin)
- [ ] ค่าธรรมเนียมแพลตฟอร์ม (ถ้ามี) และวิธีคิด
- [ ] Block explorer URL สำหรับลิงก์ transaction
- [ ] **Event-to-UI Mapping:** รายการ Event ที่ Frontend จะใช้ trigger การอัปเดต UI (เช่น เมื่อเกิด `PaymentReleased` ให้เปลี่ยนสถานะโปรเจกต์เป็น `completed`)

---

## 2. Environment Variables

ไฟล์ `.env.example` มีค่าเหล่านี้แล้ว:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_CHAIN_ID=
VITE_CONTRACT_ADDRESS=
VITE_EXPLORER_URL=
```

> Smart Contract ใช้ FreelinkEscrow v2 บน Sepolia และ ABI อยู่ที่ `src/config/FreelinkEscrow.abi.json` (สำเนาจาก `smart-contact/abi/`) FastAPI ใช้ `ESCROW_THB_PER_ETH` และส่งยอด wei ของข้อตกลงให้หน้าเว็บ ตาม [วิธีตั้งค่า backend](../backend/README.md)

- `VITE_*` ถูกฝังใน browser ทั้งหมด → **ห้ามใส่ secret**
- โหมด dev ใช้ `http://localhost:8000` ถ้าไม่ระบุ URL ให้ตั้ง `VITE_API_BASE_URL` ก่อน build สำหรับระบบที่ deploy

---

## 3. Service Layer ที่ต้องแก้

| ไฟล์ | หน้าที่ | สถานะ |
| --- | --- | --- |
| `src/services/api/apiClient.js` | Axios instance, session cookie, error normalize | พร้อมใช้ |
| `src/services/api/endpoints.js` | แผนที่ endpoint | **DRAFT — ต้องยืนยัน** |
| `src/services/api/authService.js` | `/auth/me`, `/auth/logout`, Google URL | **DRAFT** |
| `src/services/api/jobService.js` | งาน / ประกาศ | เรียก REST API |
| `src/services/api/proposalService.js` | ข้อเสนอ | เรียก REST API |
| `src/services/api/projectService.js` | โครงการ / ส่งงาน / ตรวจรับ | เรียก REST API |
| `src/services/api/profileService.js` | โปรไฟล์ / รีวิว | เรียก REST API |
| `src/services/api/notificationService.js` | การแจ้งเตือน | เรียก REST API |
| `src/services/api/transactionService.js` | ธุรกรรม / ถอนเงิน | เรียก REST API |
| `src/services/auth/authService.js` | Google Login และ session | เรียก REST API |
| `tests/fixtures/` | ข้อมูลจำลอง | สำหรับทดสอบ |

ตัวอย่างการเรียก REST API

```js
// ตัวอย่างที่มีอยู่แล้วในทุก service
assertApiConfigured()
return apiClient.get(endpoints....).then((r) => r.data)
```

เมื่อ endpoint/response เปลี่ยน ให้แก้ที่ service + `endpoints.js` โดย **ไม่ต้องแก้ UI**

---

## 4. Endpoint ที่ Frontend คาดว่าจะใช้ (ข้อเสนอ)

### Auth
| Method | Path | ใช้ที่ |
| --- | --- | --- |
| `GET` | `/auth/me` | โหลด session |
| `POST` | `/auth/logout` | ออกจากระบบ |
| `GET` | `/auth/google` | เริ่ม Google OAuth (ยังไม่ผูก callback) |

### Jobs
| Method | Path | ใช้ที่ |
| --- | --- | --- |
| `GET` | `/jobs` | Browse Jobs, Freelancer Jobs |
| `GET` | `/jobs/:id` | Job Details |
| `GET` | `/clients/:clientId/jobs` | Manage Jobs |
| `POST` | `/jobs` | Create Job |
| `PATCH` | `/jobs/:id` | Edit Job |
| `DELETE` | `/jobs/:id` | Delete Job |

### Proposals
| Method | Path | ใช้ที่ |
| --- | --- | --- |
| `GET` | `/jobs/:jobId/proposals` | Job Applicants / Compare |
| `GET` | `/freelancers/:id/proposals` | My Proposals |
| `GET` | `/proposals/:id` | รายละเอียดข้อเสนอ |
| `POST` | `/proposals/:id/hire` | จ้างงาน |

### Projects
| Method | Path | ใช้ที่ |
| --- | --- | --- |
| `GET` | `/projects` | Active Projects |
| `GET` | `/projects/:id` | Project Details |
| `POST` | `/projects/:id/submissions` | Submit Work |
| `POST` | `/projects/:id/approve` | Review Work |
| `POST` | `/projects/:id/request-revision` | Request Revision |

### Profiles
`GET /freelancers`, `GET`/`PATCH /freelancers/:id`, `GET`/`PATCH /clients/:id`
(ยังไม่มี `GET /freelancers/:id/reviews` — รอโฟลว์ปิดโปรเจกต์และรีวิว)

### Notifications
`GET /notifications`, `PATCH /notifications/:id/read`, `PATCH /notifications/read-all`

### Transactions
`GET /transactions` (ว่างจนกว่าจะซิงก์ escrow) — `GET /transactions/:id` และ `POST /transactions/withdraw` ยังไม่เปิด

### Messages
`GET /messages/threads`, `GET /messages/threads/:id`, `POST /messages/threads/:id/messages`, `PATCH /messages/threads/:id/read`

> หาก path/ método ต่างจากนี้ ให้แจ้งเพื่อปรับ `endpoints.js`

---

## 5. Response Shape ที่ UI ใช้

ตรวจ response ของ endpoint ที่เปิดใช้งานจริงจาก OpenAPI ของ FastAPI
ตัวอย่างที่สำคัญ:

**Job**
```js
{
  id, title, description, category, skills: [],
  budgetType: 'fixed' | 'hourly',
  budgetMin, budgetMax, duration, experienceLevel,
  status: 'open' | 'in_progress' | 'closed' | 'draft',
  client: { id, name, company, avatarColor, rating, ... },
  proposalsCount, createdAt
}
```

**Proposal**
```js
{ id, jobId, freelancerId, freelancer, bidAmount, deliveryDays, coverLetter, status, createdAt }
```

**Project**
```js
{
  id, jobId, title, clientId, freelancerId,
  status: 'active' | 'in_review' | 'revision' | 'completed' | 'disputed',
  escrowStatus: 'unfunded' | 'funded' | 'released' | 'refunded',
  budget, milestones: [], submission, createdAt
}
```

**Transaction**
```js
{ id, type, status: 'pending' | 'confirmed' | 'failed', amount, txHash, projectId, createdAt }
```

หาก Backend ใช้รูปแบบอื่น แนะนำให้ map ที่ service layer เพื่อรักษา UI contract เดิม

---

## 6. Error Format ที่แนะนำ

`apiClient` normalize error เป็น:

```js
{
  message: 'ข้อความที่แสดงผู้ใช้ได้',
  status: 400,
  code: 'VALIDATION_ERROR',
  details: { field: 'ข้อความ' } | null,
  isApiError: true
}
```

- `message` ควรเป็นข้อความที่แสดงผู้ใช้ได้ (ภาษาไทยหรืออังกฤษ)
- `details` ใช้แสดง error ราย field ในฟอร์ม
- อย่าส่ง stack trace หรือข้อมูลภายในออกมา

---

## 7. Authentication

- FastAPI รับ Google OAuth callback และออก session cookie แบบ HttpOnly
- React อ่าน `GET /auth/me` ตอนเปิดแอป Response มี `role`, `profileId`, `name` และ `email`
- ตั้งค่า Google client และ callback ใน [backend/.env](../backend/.env.example) โดยใช้ host เดียวกันสำหรับ frontend และ API ในเครื่อง
- **ห้ามเก็บ password/secret ใน frontend**

---

## 8. Blockchain / Escrow

### ต้องเติมใน `src/config/contractConfig.js`
```js
chainId
chainName
contractAddress
abi
currency: { type, symbol, address, decimals }
methods: { depositEscrow, releasePayment, refundClient, getEscrow, openDispute }
explorerUrl
```

### พฤติกรรมปัจจุบัน
- `isContractConfigured()` เป็น false → ทุก write โยน `ContractNotConfiguredError`
- Wallet connect ทำงานจริงผ่าน `window.ethereum`
- Escrow page แสดงรายการที่ยังขาด (`getMissingContractConfig()`)
- ไม่มีการรายงานธุรกรรมสำเร็จหากไม่ได้รับ hash จาก wallet จริง

### สิ่งที่ต้องยืนยัน
- [x] ลำดับเรียก: v2 ใช้ native ETH ไม่มี `approve` → `depositEscrow` พร้อมแนบ `quote(amount).total`
- [ ] หน่วยเงินและ decimals
- [ ] ใครเรียก `releasePayment` ได้ (client / platform / multisig)
- [ ] เงื่อนไข `refundClient` และ dispute
- [ ] mapping สถานะ on-chain → `unfunded | funded | released | refunded`
- [ ] event ที่ใช้ติดตาม (`EscrowFunded`, `PaymentReleased`, ...)
- [ ] วิธี handle Error Case ต่อไปนี้ให้ UI แสดงผลได้ถูกต้อง:
    - `User rejected request` (ผู้ใช้กดยกเลิก transaction ใน wallet)
    - `Wrong network` (ผู้ใช้เชื่อมต่อผิด network/chain)
    - `Insufficient funds` (เงินไม่พอจ่าย gas หรือค่าจ้าง)
    - `Contract execution reverted` (ธุรกรรมล้มเหลวเนื่องจากเงื่อนไขใน contract ไม่ผ่าน)
- [ ] testnet ที่จะใช้ demo

---

## 9. ลำดับงานแนะนำ

1. ยืนยัน endpoint + response shape กับ Frontend
2. เปิด CORS และทำ `/auth/me` ให้ทดสอบได้
3. ทำ Jobs + Proposals ก่อน (workflow หลัก)
4. ทำ Projects + Review + Transactions
5. Deploy Contract บน testnet → ส่ง ABI/address/chain id
6. เชื่อม Escrow UI ทีละขั้น (deposit → release)
7. ทดสอบร่วมกับ checklist ด้านล่าง

---

## 10. Checklist ทดสอบร่วมกัน

- [ ] Login จริงได้ และ role ถูกต้อง
- [ ] Client สร้าง/แก้ไข/ปิดประกาศงานได้
- [ ] Freelancer เห็นงานใหม่และส่งข้อเสนอได้
- [ ] Client เห็นผู้สมัครและจ้างงานได้
- [ ] โครงการถูกสร้างด้วยสถานะ escrow `unfunded`
- [ ] Freelancer ส่งงานได้ (ลิงก์/ไฟล์)
- [ ] Client ตรวจรับ/ขอแก้ไขได้
- [ ] Transaction ฝาก/ปล่อยเงินแสดง pending → confirmed/failed ตาม wallet จริง
- [ ] Transaction hash ลิงก์ไป explorer ได้
- [ ] Notification เกิดจาก event จริง
- [ ] การแจ้งเตือน/ข้อความไม่รั่วข้ามผู้ใช้
- [ ] Error จาก API แสดงข้อความที่เข้าใจได้
- [ ] ไม่มีปุ่มที่กดแล้วเงียบหรือแจ้งสำเร็จปลอม

---

## 11. หมายเหตุด้านความปลอดภัย

- Frontend ไม่ควรเป็นผู้ตัดสินสิทธิ์ขั้นสุดท้าย — Backend/Contract ต้องตรวจสอบ role และเงื่อนไขซ้ำ
- อย่าเชื่อ `projectId`, `amount` หรือ `role` ที่ส่งมาจาก client โดยไม่ตรวจฝั่ง server
- หลีกเลี่ยงการเก็บ token ใน `localStorage` หากทีมเลือกใช้ httpOnly cookie
- ตรวจสอบ `chainId` ก่อนทำธุรกรรมทุกครั้ง
- Escrow address/ABI ควรโหลดจาก config ที่ถูกต้องของ environment ไม่ hardcode ใน component

# แผนพัฒนา Freelink Backend ด้วย FastAPI REST API

เป้าหมายรอบแรกคือให้ client และ freelancer ใช้บัญชีจริงคนละบัญชี แล้วทำงานครบหนึ่งเส้นทางบน Sepolia ตั้งแต่ลงงาน ส่งข้อเสนอ จ้าง ฝาก ETH ยอมรับงาน ส่งงาน จนถึงตรวจรับและปล่อยเงิน หลังรีเฟรชหน้าเว็บ ทั้งสองฝ่ายต้องเห็นข้อมูลจากฐานข้อมูลและสถานะเงินที่ตรงกับ smart contract

เดโมใช้ native ETH บน Sepolia และอัตราบาทต่อ ETH แบบคงที่ **หนึ่งงวดใช้หนึ่ง escrow ต่อรอบการฝาก** งานที่ไม่มีงวดแยกใช้ escrow ก้อนเดียว ใช้ [กติกา Escrow ฉบับละเอียด](../../smart-contact/docs/FREELINK_ESCROW_RULES_TH.md) เป็นข้ออ้างอิงของ v3 ส่วนสัญญา Sepolia ที่ใช้อยู่ปัจจุบันรองรับ `acceptEscrow` แบบ 4 พารามิเตอร์แล้ว

## กติกา v3 ที่ต้องรองรับ

| กติกา | งานฝั่ง smart contract | งานฝั่ง backend และ frontend |
| --- | --- | --- |
| D2 | Wallet สำรองตัดสินแทนหลังวันที่ 7 และแบ่งครึ่งเมื่อครบ 14 วัน | อ่านผู้ตัดสินและเวลาที่มีสิทธิ์จากสัญญา แจ้งแต่ละฝ่ายตามเวลา |
| D3 | คืนค่าธรรมเนียมเต็มเมื่อจบด้วยคำตัดสินหรือหมดเวลา การยอมแพ้และตกลงกันเองยังใช้กติกาปกติ | แสดงยอดแบ่งและค่าธรรมเนียมจาก event ที่ยืนยันแล้ว |
| D4 | ล็อกผู้ตัดสินหลักและ wallet สำรองตอนฝาก | แสดงทั้งสอง address ก่อนรับงาน และบันทึกข้อมูลอ้างอิงจาก escrow ที่ฝากจริง |
| รอบแก้งาน | กำหนด 0–5 รอบต่องาน ค่าเริ่มต้น 2 และให้ freelancer เพิ่มได้ทีละรอบ | เก็บรอบที่ตกลงก่อนฝาก และอัปเดตรอบที่ใช้หรือเพิ่มจากสัญญา |

ก่อนเปลี่ยนเว็บไป v3 ต้องมี chain ID, contract address, deployment block และ ABI ของ deployment เดียวกัน พร้อมทดสอบเรียกฟังก์ชันหลักบน Sepolia การยืนยัน Wallet และการเก็บข้อตกลงเริ่มทำได้ก่อน ส่วนธุรกรรม v3 ใช้ ABI และ deployment ใหม่ ข้อมูล escrow เดิมต้องเก็บ chain และ address เดิมไว้เพื่ออ่านประวัติ

## 1. ตั้งโครง FastAPI และฐานข้อมูล

- สร้าง `backend/` ที่โฟลเดอร์หลัก ใช้ FastAPI และ Pydantic สำหรับ REST API, PostgreSQL กับ SQLAlchemy สำหรับข้อมูล และ Alembic สำหรับ migration อ่าน Sepolia ผ่าน Ethereum JSON-RPC ด้วย `httpx` และถอดรหัส event ด้วย `eth-abi`
- แบ่ง router เป็น auth, jobs, proposals, projects และ escrow เปิด `GET /health`, `/docs` และ `/openapi.json` ตั้ง CORS ให้รับเฉพาะ origin ของ frontend ที่กำหนด
- ใช้ `application/json` สำหรับ API หลัก ใช้ชื่อฟิลด์เดิมที่ UI อ่าน เช่น `profileId`, `freelancerWalletAddress` และ `escrowStatus` ตรวจตัวอย่าง response และพฤติกรรมการกรองจาก [INTEGRATION.md](../INTEGRATION.md) และ [Axios services](../../src/services/api/) ก่อนยืนยันใน OpenAPI
- กำหนด error body เป็น `message`, `code` และ `errors` ให้ตรงกับ Axios interceptor ใช้ `401` เมื่อยังไม่เข้าสู่ระบบ, `403` เมื่อไม่มีสิทธิ์, `404` เมื่อไม่พบข้อมูล, `409` เมื่อสถานะขัดกับคำขอ และ `422` เมื่อข้อมูลที่ส่งมาไม่ผ่านการตรวจ จัดรูป FastAPI validation error ให้ frontend อ่านได้

| ข้อมูล | สิ่งที่ต้องเก็บ |
| --- | --- |
| ผู้ใช้ โปรไฟล์ และ session | Google subject, ชื่อ อีเมล บทบาท โปรไฟล์ และกระเป๋าที่ผ่านการยืนยัน |
| งานและข้อเสนอ | เจ้าของงาน งบ ผู้ยื่นข้อเสนอ ราคาเสนอ จำนวนวันส่งงาน และสถานะ |
| โปรเจกต์และข้อตกลง | คู่สัญญา ข้อเสนอที่ถูกจ้าง งวด ลำดับรอบฝาก รหัส `bytes32` ของงวดและรอบนั้น และข้อตกลงฉบับที่ใช้ฝากเงิน |
| งานที่ส่ง | รอบส่งงาน ข้อมูลอ้างอิงไฟล์ `workHash` และเวลา |
| Escrow และธุรกรรม | Chain ID, contract address, `escrowId`, `txHash`, สถานะ, event log และจุดที่อ่าน event ถึง |

**เกณฑ์ผ่าน** ฐานข้อมูลเปล่าสร้างได้จาก migration และ API เปิดเอกสาร OpenAPI ได้โดยใช้ค่า config ของเครื่องพัฒนา

## 2. ต่อ Login ลงงาน ส่งข้อเสนอ และจ้าง

เริ่มด้วย Google Login แบบ redirect และ callback ให้ FastAPI สร้าง session และให้ React โหลดผู้ใช้จาก `GET /auth/me` เมื่อเปิดแอป แผนนี้เสนอ session cookie แบบ `HttpOnly` เปิด `Secure` บน HTTPS ปรับ Axios ให้ส่ง credentials และเพิ่มการป้องกัน CSRF สำหรับคำขอที่เปลี่ยนข้อมูล ใช้ session ตรวจตัวตนและตรวจสิทธิ์การเข้าถึงงานหรือโปรเจกต์ทุกครั้งที่จำเป็น บทบาท admin กำหนดฝั่ง server

สำหรับแอดมินคนแรก ใช้ `npm run init:admin` จากเครื่อง backend และเพิ่มบัญชีถัดไปด้วย `npm run add:admin` แอดมินยืนยันตัวตนด้วย username กับรหัสผ่าน ส่วน client และ freelancer ใช้ Google Login ทั้งสองเส้นทางใช้ `GET /auth/me` และ session cookie ของ FastAPI ตามเดิม [วิธีสร้างบัญชีแอดมิน](../../backend/README.md)

| วิธีและเส้นทาง | พฤติกรรมที่ต้องรองรับ |
| --- | --- |
| `GET /auth/google`, `GET /auth/google/callback` | เริ่ม Google Login ตรวจ OAuth state และสร้าง session หลังยืนยันตัวตน |
| `GET /auth/me`, `POST /auth/logout` | โหลดโปรไฟล์สำหรับ UI และยกเลิก session |
| `POST /auth/admin/login` | ตรวจรหัสผ่านแอดมินและออก session cookie |
| `GET /jobs`, `GET /jobs/{id}`, `GET /clients/{clientId}/jobs` | แสดงรายการงาน รายละเอียด และงานของ client ตามสิทธิ์ |
| `POST /jobs`, `PATCH /jobs/{id}`, `DELETE /jobs/{id}` | สร้าง แก้ และลบงานตามสิทธิ์เจ้าของและสถานะของงาน |
| `POST /jobs/{id}/proposals`, `GET /jobs/{id}/proposals` | ให้ freelancer ส่งข้อเสนอ และให้เจ้าของงานดูข้อเสนอของงานตัวเอง |
| `GET /freelancers/{id}/proposals`, `GET /proposals/{id}` | แสดงข้อเสนอให้ผู้มีสิทธิ์ |
| `POST /proposals/{id}/hire` | ตรวจว่างานยังเปิดอยู่ รับข้อเสนอ และสร้างโปรเจกต์ใน DB transaction เดียว |
| `GET /projects`, `GET /projects/{id}` | อ่านโปรเจกต์ตามสิทธิ์คู่สัญญา |

เมื่อกดจ้างซ้ำด้วยข้อเสนอเดิม ให้คืนโปรเจกต์เดิม ใช้ข้อจำกัดในฐานข้อมูลร่วมกับการตรวจสถานะภายใน transaction เพื่อให้การจ้างสองข้อเสนอพร้อมกันในงานเดียวสำเร็จเพียงรายการเดียว

**เกณฑ์ผ่าน** บัญชีสองฝั่งทำเส้นทางลงงานถึงจ้างผ่าน React ได้ ข้อมูลยังอยู่หลังรีเฟรช และบัญชีที่สามเปิดโปรเจกต์นั้นไม่ได้

## 3. ผูก Wallet และจัดทำข้อตกลงก่อนฝาก

ให้ผู้ใช้เชื่อม MetaMask และเซ็นข้อความที่ FastAPI ออกให้ ข้อความระบุบัญชี public address เครือข่าย และ nonce ใช้ครั้งเดียวที่หมดอายุได้ `GET /wallet/link` คืน wallet ที่ยืนยันของบัญชีปัจจุบัน `POST /wallet/challenges` ออกข้อความ และ `POST /wallet/verifications` ตรวจลายเซ็นแล้วผูก public address ใน DB transaction เดียว

เพิ่ม `POST /projects/{id}/escrow/prepare` ให้ client เตรียมข้อมูลฝากสำหรับงวดและรอบที่ระบุ แล้วให้คู่สัญญาอ่านข้อตกลงจาก `GET /projects/{id}/escrow`

1. ตรวจ wallet ที่ยืนยันแล้วของทั้งสองฝ่าย และบันทึก address ที่ใช้กับข้อตกลงนี้ การเปลี่ยน wallet ในโปรไฟล์ภายหลังไม่เปลี่ยนคู่สัญญาที่บันทึกไว้
2. แต่ละงวดมีรายการตรวจรับของตัวเอง ฝากงวดถัดไปหลังงวดก่อนผ่านการตรวจรับ สำหรับงานหลายงวด งวดแรกไม่เกิน 30% และงวดสุดท้ายไม่น้อยกว่า 30% กำหนดรหัสบน chain แยกตามโปรเจกต์ งวด และรอบฝาก เช่น `keccak256(utf8(project.id + ":" + milestoneNumber + ":" + attemptNumber))` เก็บรหัสนี้ใน DB เมื่อคืนเงินแล้วฝากใหม่ ให้เริ่มรอบใหม่และใช้รหัสใหม่
3. แปลงค่าจ้างเป็น wei ด้วยอัตราที่กำหนดและบันทึกยอดพร้อมอัตราที่ใช้ ส่งยอด wei ผ่าน JSON เป็นสตริง ส่ง deadline เป็น Unix seconds ให้ client และ freelancer ใช้ค่าเดียวกัน ให้คำขอเตรียมซ้ำคืนข้อตกลงเดิม
4. เก็บข้อตกลง JSON ฉบับเดียวตามข้อ 4.1 รวมขอบเขตงาน สิ่งที่ต้องส่ง รายการตรวจรับ รอบแก้ และ `tosVersion` ที่ทั้งสองฝ่ายเห็น ใช้ key เรียงตามตัวอักษร ไม่มี whitespace ส่วนเกิน ใช้ข้อความ UTF-8 แบบ NFC และตัวเลขเงินเป็นสตริง Frontend คำนวณ `termsHash` จากต้นฉบับที่นำมาแสดงให้ผู้ใช้ตรวจและดาวน์โหลด พร้อม checkbox ยอมรับ ToS ก่อนฝากและก่อนรับงาน
5. ให้ frontend เรียก `quote(amountWei)` ก่อนฝากเพื่อคำนวณค่าจ้างบวกค่าธรรมเนียม แล้วให้ client เซ็น `depositEscrow` ผ่าน MetaMask โดยใช้ข้อตกลงและ ABI ที่ตรงกับ deployment

**เกณฑ์ผ่าน** ทั้งสองฝั่งอ่าน hash ยอด และ deadline ชุดเดียวกัน Frontend ใช้ค่าจาก API ในเส้นทางฝาก แทนสูตรชั่วคราวใน [contractService.js](../../src/services/blockchain/contractService.js) รายละเอียดการออกแบบอยู่ใน [คู่มือ Escrow ข้อ 4.4–4.5 และ 4.10–4.12](../../smart-contact/docs/FREELINK_ESCROW_GUIDE_TH.md)

## 4. ตรวจธุรกรรมและซิงก์สถานะจาก Sepolia

เพิ่ม `POST /projects/{id}/escrow/transactions` เพื่อรับ `txHash` จากคู่สัญญา ตรวจ receipt ว่าธุรกรรมสำเร็จและ event `EscrowFunded` ถูกปล่อยจาก contract ที่บันทึกไว้ จากนั้นเทียบรหัสของงวดและรอบฝาก, client, freelancer, `termsHash`, ค่าจ้าง และ deadline กับข้อตกลงก่อนผูก `escrowId` ผู้ฝากคนอื่นสามารถใช้รหัสเดียวกันได้ จึงต้องเทียบข้อมูลทั้งหมดก่อนบันทึกว่าโปรเจกต์นี้ฝากเงินแล้ว

- คืน `202 Accepted` เมื่อรับ hash แล้วและกำลังรอ receipt หรือ confirmation ให้หน้าเว็บติดตามจาก `GET /projects/{id}/escrow` เมื่อ event ผ่านการยืนยันแล้วจึงบันทึก `escrowId` และแสดง `Funded`
- worker อ่าน event ของ escrow แต่ละรอบโดยกรอง contract address และ `escrowId` เริ่มตั้งแต่บล็อกที่สร้างข้อตกลงและบันทึกจุดที่อ่านถึงใน DB transaction เดียวกับผลการประมวลผล เพื่อให้เปิดใหม่แล้วอ่านต่อได้แม้ผู้ใช้ปิดเว็บก่อนส่ง hash
- ประมวลผล event ตามลำดับบล็อกและ log index เก็บ `txHash` ต่อข้อตกลงแบบไม่ซ้ำ เก็บ block hash และเทียบกับบล็อก canonical ก่อนรับ event จากบล็อก `finalized` ธุรกรรมที่ยังไม่ถึง finality จะค้างสถานะรอยืนยัน
- เมื่อ RPC ล้มเหลว ให้ retry และคงสถานะล่าสุดที่ยืนยันแล้ว เมื่อธุรกรรม revert ให้รายงานความล้มเหลวโดยคงสถานะเงินตาม chain

**เกณฑ์ผ่าน** ส่ง hash ซ้ำแล้วได้ผลเดิม สัญญาคนละ address หรือข้อมูลคู่สัญญาที่ไม่ตรงไม่ทำให้โปรเจกต์ขึ้น `Funded` และ worker อ่าน event ที่ค้างได้หลัง restart

## 5. ต่อการยอมรับงาน ส่งงาน และตรวจรับ

| การกระทำ | สิ่งที่ frontend และ backend ต้องทำ |
| --- | --- |
| Freelancer ยอมรับ | แสดงยอด ค่าธรรมเนียม deadline ผู้ตัดสิน และรอบแก้จากสัญญาที่ใช้งานให้เทียบกับข้อตกลง ให้เซ็น `acceptEscrow(escrowId, termsHash, expectedAmount, expectedDeadline)` และแสดง `Active` หลังยืนยัน `EscrowAccepted` |
| Freelancer ส่งงาน | บันทึกข้อมูลส่งผ่าน `POST /projects/{id}/submissions` พร้อม `workHash` แล้วให้ผู้ใช้เซ็น `submitWork` อัปเดตรอบส่งและ `reviewEndsAt` จาก `WorkSubmitted` |
| Client ตรวจรับและปล่อยเงิน | ให้เซ็น `releasePayment` จากหน้าตรวจรับ แล้วอัปเดตเป็น `Released` เมื่อยืนยัน `PaymentReleased` |

แยกสถานะงานใน DB กับสถานะเงินบน chain ใน API การเก็บข้อมูลส่งงานเริ่มได้ก่อนเซ็น และยึด event สำหรับสถานะส่งงานบน chain และช่วงตรวจรับ เก็บไฟล์และหลักฐานไว้นอก chain และ hash ต้นฉบับ หลังเส้นทางหลักผ่านให้ต่อขอแก้ ให้รอบเพิ่ม คืนเงิน เบิกเมื่อหมดเวลาตรวจรับ และข้อพิพาทตามกติกา v3

**เกณฑ์ผ่าน** ใช้กระเป๋า client กับ freelancer คนละใบ และต่างจาก arbiter ทดสอบบน Sepolia ครบตั้งแต่จ้างถึงปล่อยเงิน รายการบนหน้าเว็บตรงกับสัญญาหลังรีเฟรช

## 6. ตั้งค่าและเปิดใช้งาน frontend

| ฝั่ง | ค่าและที่มา |
| --- | --- |
| FastAPI | `DATABASE_URL` จาก PostgreSQL, `FRONTEND_ORIGIN` จาก URL ของ React, ค่า Google OAuth จาก Google Cloud และค่าที่ใช้กับ session ตามวิธีที่เลือก |
| FastAPI สำหรับ Sepolia | `ESCROW_RPC_URL` จากผู้ให้บริการ, `ESCROW_CHAIN_ID=11155111`, `ESCROW_CONTRACT_ADDRESS` จาก deployment และ `ESCROW_THB_PER_ETH` ที่ทีมกำหนด ใช้ผล `finalized` จาก RPC เป็นเกณฑ์ยืนยัน |
| React | `VITE_API_BASE_URL`, `VITE_CHAIN_ID=11155111`, `VITE_CONTRACT_ADDRESS` |

เก็บ OAuth Client Secret, session secret และ RPC URL ที่มี API key ฝั่ง server การตรวจ receipt และ event ใช้ RPC โดยไม่ต้องใช้ private key ของ deployer Frontend เรียก REST API โดยตรง ส่วน fixture สำหรับทดสอบอยู่ใน `tests/fixtures/` [ตัวอย่าง env ของ frontend](../../.env.example) · [วิธีส่งมอบ ABI และ address](../../smart-contact/README.md)

## ลำดับลงมือ

1. FastAPI, migration, รูปแบบ response และ Login
2. API ลงงาน ส่งข้อเสนอ จ้าง และดูโปรเจกต์จาก DB
3. ยืนยัน Wallet ด้วยลายเซ็นจาก MetaMask แล้วสร้างข้อตกลงและคีย์ฝากแยกตามงวดและรอบ
4. ตรวจ `EscrowFunded` ตั้งแต่อ่าน receipt ไปจนถึงซิงก์ event จาก Sepolia
5. ต่อหน้ารับงาน ส่งงาน และตรวจรับกับสัญญาที่ใช้งาน แล้วทดสอบตั้งแต่ต้นจนจบ
6. ทดสอบ v3 สำหรับรอบแก้งาน การผูกผู้ตัดสิน ข้อพิพาทปกติ และ timeout

# Freelink REST API

ใช้ PostgreSQL 17 ผ่าน Docker Compose สำหรับพัฒนาในเครื่อง Docker สร้างฐานข้อมูล `freelink` ตอนเปิดครั้งแรก แล้ว Alembic สร้างตารางจาก migration ข้อมูลอยู่ใน Docker volume `freelink-dev_postgres_data` การหยุดและเปิด container ใหม่จะใช้ข้อมูลเดิม [PostgreSQL Docker image](https://hub.docker.com/_/postgres)

## เปิดใช้บน Windows

เปิด Docker Desktop แล้วรันจากโฟลเดอร์หลักของโปรเจกต์

```powershell
cd backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait db
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

เปิด [FastAPI Swagger UI](http://127.0.0.1:8000/docs) หรือเรียก [GET /health](http://127.0.0.1:8000/health) เพื่อเช็กว่า API เชื่อมฐานข้อมูลได้ เมื่อ PostgreSQL พร้อมจะได้ HTTP 200 และ `{"status":"ok","database":"ok"}`

## ฐานข้อมูล

- `DATABASE_URL` ใน `.env` ชี้ไปที่ PostgreSQL บน `127.0.0.1:5432` ค่าใน `.env.example` ใช้สำหรับพัฒนาในเครื่อง หากเปลี่ยนพอร์ตให้ตั้ง `POSTGRES_PORT` และพอร์ตใน `DATABASE_URL` ให้ตรงกัน
- ตรวจรายการตารางด้วย `docker compose exec db psql -U freelink -d freelink -c '\dt'` หรือเชื่อมผ่านโปรแกรมจัดการฐานข้อมูลโดยใช้ค่า host, port, user และ database จาก `.env`
- Migration สร้าง `users`, `profiles`, `login_sessions`, `jobs`, `proposals`, `projects`, `notifications`, `message_threads` และ `messages` รัน `.\.venv\Scripts\python.exe -m alembic upgrade head` หลังดึง migration ใหม่
- หยุด PostgreSQL ด้วย `docker compose stop db` แล้วเปิดใหม่ด้วย `docker compose up -d --wait db`

## Google Login

1. สร้าง OAuth Client ชนิด Web application ใน Google Cloud ตั้ง authorized redirect URI เป็น `http://localhost:8000/auth/google/callback` ตาม [คู่มือ Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
2. เพิ่ม `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` และ `SESSION_SECRET` ใน `backend/.env` ดูชื่อค่าจาก [.env.example](.env.example) ใช้ session secret แบบสุ่มอย่างน้อย 32 ตัวอักษร เปิด `SESSION_COOKIE_SECURE=true` เมื่อใช้ HTTPS
3. ใช้ `localhost` ทั้งหน้าเว็บและ API ในเครื่อง หน้า `/login` เรียก `/auth/google` เพื่อเข้าบัญชีเดิม หน้า `/register` เพิ่ม `?role=client` หรือ `?role=freelancer` สำหรับบัญชีใหม่ Backend ใช้บทบาทที่บันทึกไว้สำหรับบัญชีเดิม
4. คำขอที่สร้างหรือแก้ข้อมูลต้องส่ง session cookie และ `Origin` ที่ตรงกับ `FRONTEND_ORIGIN` ฝั่ง React ใช้ Google redirect, `GET /auth/me` และ Axios `withCredentials` แล้ว ตั้ง `VITE_API_BASE_URL=http://localhost:8000` สำหรับเครื่องพัฒนา

## API และ log

### สมัครและเข้าสู่ระบบด้วยอีเมล

ที่ `/register` ผู้ใช้เลือกบทบาทคนจ้างหรือคนรับงาน กรอกชื่อ อีเมล และรหัสผ่าน 8–128 ตัวอักษร ระบบสร้างบัญชีแล้วเข้าสู่ระบบให้ ใช้ `/login` ด้วยอีเมลเดิมในครั้งถัดไป อีเมลเป็นข้อมูลที่ผู้ใช้กรอกเองในรอบนี้ ส่วนการยืนยันอีเมลและกู้รหัสผ่านต้องต่อบริการส่งอีเมลในภายหลัง

`POST /auth/register` และ `POST /auth/login` ใช้ session cookie ชุดเดียวกับ Google Login รหัสผ่านเก็บเป็น Argon2id ใน `user_credentials` และบัญชีแอดมินยังใช้ `/admin/login` บัญชีที่สร้างด้วย Google ใช้วิธีเดิม ส่วนการผูกสองวิธีเข้ากับบัญชีเดียวต้องมีขั้นตอนยืนยันตัวตนเพิ่ม

### สร้างบัญชีจากเทอร์มินัล

เปิด PostgreSQL และรัน Alembic migration จนถึง `head` ก่อน จากโฟลเดอร์หลักของโปรเจกต์ รัน

```powershell
cd backend
$env:DEMO_PASSWORD = "ตั้งรหัสผ่านเอง 8 ตัวขึ้นไป"
.\.venv\Scripts\python.exe -m app.create_account --demo
```

โหมด `--demo` ใช้สำหรับฐานข้อมูลพัฒนาที่กำหนดใน `DATABASE_URL` ทั้งสามบัญชีใช้รหัสผ่านจาก `DEMO_PASSWORD` ซึ่งไม่เก็บใน repo

| บทบาท | อีเมลหรือ username | หน้าเข้าสู่ระบบ |
| --- | --- | --- |
| client | `demo-client@example.net` | `/login` |
| freelancer | `demo-freelancer@example.net` | `/login` |
| admin | `demo-admin` | `/admin/login` |

ถ้าต้องการกำหนดข้อมูลบัญชีเอง ให้รันจากโฟลเดอร์ `backend` ดังนี้

```powershell
.\.venv\Scripts\python.exe -m app.create_account
```

คำสั่งจะถามบทบาทและสร้างทีละบัญชี หรือระบุบทบาทต่อท้ายเป็น `client`, `freelancer` หรือ `admin` ได้เลย คำสั่งใช้ฐานข้อมูลเดียวกับ backend ตาม `DATABASE_URL` และซ่อนรหัสผ่านขณะพิมพ์

- `client` (ผู้จ้าง) และ `freelancer` (ผู้รับงาน) เข้าสู่ระบบที่ `/login` ด้วยอีเมลและรหัสผ่าน
- `admin` เข้าสู่ระบบที่ `/admin/login` ด้วย username และรหัสผ่าน ถ้ามีแอดมินอยู่แล้ว ให้ระบุ `admin --add`

### สร้างบัญชีแอดมินด้วย npm

ติดตั้ง dependencies และรัน Alembic migration จนถึง `head` ก่อน จากโฟลเดอร์หลักของโปรเจกต์ เปิด PowerShell แล้วรัน

```powershell
npm run init:admin
```

กรอก username ชื่อที่แสดง อีเมลติดต่อ และรหัสผ่าน 15–128 ตัวอักษร รหัสผ่านถูกซ่อนขณะพิมพ์และเก็บเป็น Argon2id hash จากนั้นเปิด [หน้าเข้าสู่ระบบแอดมิน](http://localhost:5173/admin/login) บัญชีนี้ใช้ session cookie ของ FastAPI โดยมีอายุ 8 ชั่วโมงและล็อกการลองรหัสชั่วคราว 10 นาทีหลังผิด 5 ครั้ง [การตรวจรหัสผ่านด้วย Argon2](https://argon2-cffi.readthedocs.io/en/stable/howto.html)

เมื่อต้องเพิ่มแอดมินคนถัดไป ผู้ดูแลที่เข้าถึงเครื่อง backend ใช้ `npm run add:admin` ได้ คำสั่ง init จะปฏิเสธหากมี admin อยู่แล้ว และทั้งสองคำสั่งปฏิเสธ username ที่ซ้ำ ผู้ใช้ marketplace ใช้ Google Login ตามเดิม

### การตรวจสอบ API และ request log

Swagger มีเส้นทาง Google Login, session, งาน, ข้อเสนอและโปรเจกต์ ดูขอบเขตและผลการทดสอบใน [บันทึกงาน](IMPLEMENTATION_LOG.md)

แอดมินเปิดหน้า `/admin/users` และ `/admin/jobs` เพื่อดูข้อมูลจาก PostgreSQL บัญชีแอดมินสามารถระงับและคืนสถานะของ client หรือ freelancer พร้อมระบุเหตุผล การระงับยกเลิกทุก session ของบัญชีเป้าหมายทันทีเมื่อบันทึกสำเร็จ

ในหน้า `/admin/users` กด **จัดการ** เพื่อระงับหรือคืนสถานะ ส่งคำเตือน หรือบันทึก Flag ภายในทีม พร้อมดูประวัติของบัญชีนั้น ผู้ใช้จะเห็นเฉพาะคำเตือนของตนในแดชบอร์ด เมื่อคำขอที่ต้องใช้ session ได้ `401 LOGIN_REQUIRED` หน้าเว็บจะล้างสถานะบัญชีและพาออกจากหน้าที่ต้องล็อกอิน

### ผูก Wallet กับบัญชี

เข้า `/wallet` ด้วยบัญชีคนจ้างหรือคนรับงาน เชื่อม MetaMask แล้วกด **ยืนยันและผูก Wallet** เพื่อเซ็นข้อความระบบ ข้อความใช้ได้ครั้งเดียวและหมดอายุภายใน 5 นาที ลายเซ็นนี้ใช้ตรวจเจ้าของ public address และไม่ส่งธุรกรรมหรือเสีย gas Backend บันทึก address, chain และเวลายืนยัน โดยใช้ `ESCROW_CHAIN_ID` ค่าเริ่มต้น `11155111` ให้ตั้งสอดคล้องกับ frontend หากใช้เครือข่ายอื่น

Backend พิมพ์ request ID, HTTP method, route template, status และเวลาที่ใช้ลง console พร้อมคืน `X-Request-ID` ใน response ใช้ `--no-access-log` ตามคำสั่งด้านบนเพื่อให้ log ใช้ route template และเมื่อจำเป็นต้องเก็บ log ลงไฟล์ ให้ต่อ `2>&1 | Tee-Object -FilePath backend-runtime.log` ท้ายคำสั่งเปิด Uvicorn

### ข้อตกลงรายงวดและตรวจธุรกรรม Sepolia

ตั้ง `ESCROW_CHAIN_ID`, `ESCROW_CONTRACT_ADDRESS`, `ESCROW_THB_PER_ETH` และ `ESCROW_RPC_URL` ใน `backend/.env` ให้ address กับ chain ID ตรงกับ frontend อัตราเป็นจำนวนบาทต่อ 1 ETH แบบคงที่ของเดโมและจะถูกบันทึกพร้อมข้อตกลง RPC ใช้สำหรับอ่าน Sepolia โดยไม่ใช้ private key

จาก `backend/` รัน migration และเปิด worker ในเทอร์มินัลแยกจาก Uvicorn

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.escrow_worker
```

ทั้งสองฝ่ายยืนยัน Wallet จากหน้า `/wallet` แล้วไปที่รายละเอียดโครงการและเปิดหน้า **ข้อตกลงและการจ่ายเงิน** คนจ้างเตรียมข้อตกลง กดยอมรับ และเซ็นฝากผ่าน MetaMask คนรับงานเปิดดูและดาวน์โหลด JSON ต้นฉบับฉบับเดียวกันได้ ยอดจะเข้า `escrowStatus` และประวัติเมื่อ FastAPI ตรวจ event จากบล็อกที่ Sepolia ระบุว่า `finalized` แล้ว ในช่วงรอ `POST /projects/{id}/escrow/transactions` จะคืน `202` ถ้าปิดเว็บก่อนส่ง hash worker จะค้นจาก log และอ่านต่อจากบล็อกที่บันทึกไว้ ถ้าปิด worker สามารถนำ hash มากดตรวจซ้ำในหน้า Escrow ได้

รอบนี้หน้าเว็บใช้ ABI ของ v2 และจำนวนรอบแก้จากสัญญาที่ deploy อยู่ การยืนยันรับงาน ส่งงาน และสัญญา v3 ยังเป็นงานถัดไป รายการฝากจากโฟลว์เดิมยังเปิดอ่านจาก Wallet ที่เคยฝากได้บนหน้า Escrow

รันทดสอบจาก `backend/` ด้วย `.\.venv\Scripts\python.exe -m unittest tests.test_marketplace -v` ต้องเปิด PostgreSQL ก่อน การทดสอบใช้ฐานข้อมูลชั่วคราวและลบเมื่อเสร็จ

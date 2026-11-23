#!/usr/bin/env python
"""
Freelink flow tracer — เดินข้อมูลจริงจาก Frontend → Backend → Database → Smart Contract แล้วบอกว่าแต่ละขั้นแตะชั้นไหน

รัน (จากโฟลเดอร์หลักของโปรเจกต์ ต้องเปิด backend, Postgres และ `npm run dev` ไว้ก่อน):

    backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py                      # เดินถึงจุดที่ต้องใช้ MetaMask ฝากเงิน
    backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py --simulate-funding   # จำลองว่าฝากเงินแล้ว เพื่อดูส่งงาน/ตรวจรับต่อ
    backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py --report trace.md    # เก็บผลเป็นไฟล์ (ใช้ทำสไลด์/รายงาน)
    backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py --cleanup            # ลบข้อมูลทดสอบที่สคริปต์นี้สร้างไว้

อะไรที่สคริปต์ทำ / ไม่ทำ
  - Frontend : รันโค้ด service ของ React จริง (ผ่าน Vite SSR) เพื่อจับ request ที่จะส่งไป backend และเรียก hashTerms() ตัวจริง
               ไม่ได้เปิดเบราว์เซอร์/MetaMask — ส่วนที่ต้องกดในหน้าเว็บสคริปต์จะบอกว่าอยู่ตรงไหน
  - Backend  : เรียก REST API ตัวที่รันอยู่จริง พร้อม Origin และ session cookie เหมือนเบราว์เซอร์
  - Database : อ่านกลับ (SELECT) หลังแต่ละขั้นเพื่อให้เห็นว่าข้อมูลลงตารางไหน ไม่แก้อะไรเลย ยกเว้น --simulate-funding และ --cleanup
  - Contract : อ่านอย่างเดียวผ่าน RPC (eth_call) ไม่ส่งธุรกรรม ไม่ใช้ private key ไม่เสียแก๊ส
ข้อมูลทดสอบใช้อีเมล flowtest-*@example.net เพื่อให้ล้างออกได้ด้วย --cleanup
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
    from eth_abi import decode, encode
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_utils import keccak
except ImportError as error:  # pragma: no cover - friendly hint only
    sys.exit(f"ขาดไลบรารี ({error.name}) — ให้รันด้วย Python ของ backend: backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py")
try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TEST_EMAIL_LIKE = "flowtest-%@example.net"
CHAIN_STATUS = ["unfunded", "funded", "active", "submitted", "disputed", "released", "refunded", "resolved"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# ฟังก์ชันของ contract ที่ผู้ใช้เรียก → (ใครเรียก, ชื่อที่ UI ใช้เรียก ถ้ามี)
CONTRACT_WRITES = [
    ("depositEscrow", "client"), ("acceptEscrow", "freelancer"), ("submitWork", "freelancer"),
    ("releasePayment", "client"), ("requestRevision", "client"), ("claimAfterReview", "freelancer"),
    ("refundClient", "client"), ("openDispute", "client/freelancer"), ("resolveDispute", "arbiter"),
    ("settleExpiredDispute", "client/freelancer"), ("withdraw", "ผู้รับเงินที่จ่ายอัตโนมัติไม่สำเร็จ"),
]
CONTRACT_EVENTS = ["EscrowFunded", "EscrowAccepted", "WorkSubmitted", "RevisionRequested", "PaymentReleased",
                   "EscrowRefunded", "DisputeOpened", "DisputeResolved", "PayoutDeferred", "Withdrawn"]


class Abort(Exception):
    """หยุดการเดินขั้นถัดไป เพราะขั้นนี้ต้องผ่านก่อน"""


# --------------------------------------------------------------------------- output

class Out:
    COLORS = {"FE": "36", "FE→BE": "32", "BE": "32", "DB": "33", "CHAIN": "35", "WALLET": "34", "SIM": "31"}
    CONTRACT = {"none": "2", "read": "35", "write": "1;31", "gap": "33"}

    def __init__(self, color: bool):
        self.color = color
        self.buffer: list[str] = []

    def paint(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text

    def raw(self, text: str = "") -> None:
        print(text, flush=True)
        self.buffer.append(ANSI.sub("", text))

    def line(self, tag: str, text: str, indent: int = 2) -> None:
        label = self.paint(self.COLORS.get(tag, "37"), f"[{tag}]".ljust(8))
        self.raw(f"{' ' * indent}{label} {text}")

    def mark(self, ok: bool | None, text: str, indent: int = 4) -> None:
        symbol = {True: self.paint("32", "✔"), False: self.paint("1;31", "✘"), None: self.paint("33", "⚠")}[ok]
        self.raw(f"{' ' * indent}{symbol} {text}")


@dataclass
class StepRecord:
    no: str
    title: str
    layers: str
    contract_kind: str
    contract_text: str
    failures: int = 0
    warnings: int = 0
    skipped: str = ""


def fmt(value) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)[:8]
    if isinstance(value, datetime):
        return value.astimezone().strftime("%H:%M:%S")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    text = str(value)
    return text[:41] + "…" if len(text) > 44 else text


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("\"'")
    return values


def eth(wei: int) -> str:
    return f"{Decimal(wei) / Decimal(10**18):.6f} ETH"


# --------------------------------------------------------------------------- adapters

class Db:
    def __init__(self, url: str):
        self.conn = psycopg.connect(url.replace("+psycopg", "", 1), autocommit=True, connect_timeout=3)

    def rows(self, sql: str, params=()) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            names = [d.name for d in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]

    def execute(self, sql: str, params=()) -> int:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


class Chain:
    """อ่าน Sepolia ผ่าน RPC ของ backend/.env — read-only ไม่มี private key"""

    def __init__(self, url: str, contract: str, abi: list[dict]):
        self.url, self.contract = url, contract.lower()
        self.http = httpx.Client(timeout=15)
        components = next(item for item in abi if item.get("name") == "getEscrow")["outputs"][0]["components"]
        self.escrow_type = "(" + ",".join(item["type"] for item in components) + ")"
        self.escrow_fields = [item["name"] for item in components]

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc

    def rpc(self, method: str, params: list | None = None):
        response = self.http.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body["result"]

    def read(self, signature: str, arg_types: list[str], args: list, out_types: list[str]) -> tuple:
        data = keccak(text=signature)[:4] + (encode(arg_types, args) if arg_types else b"")
        result = self.rpc("eth_call", [{"to": self.contract, "data": "0x" + data.hex()}, "latest"])
        return decode(out_types, bytes.fromhex(result[2:]))

    def escrow(self, escrow_id: str) -> dict:
        (values,) = self.read("getEscrow(bytes32)", ["bytes32"], [bytes.fromhex(escrow_id[2:])], [self.escrow_type])
        return dict(zip(self.escrow_fields, values))


@dataclass
class Actor:
    name: str
    role: str
    email: str
    password: str
    http: httpx.Client
    user_id: str = ""
    profile_id: str = ""
    wallet: object = None

    @property
    def token(self) -> str:
        return self.http.cookies.get("freelink_session") or ""


# --------------------------------------------------------------------------- the flow

class Flow:
    def __init__(self, args: argparse.Namespace, out: Out):
        self.args, self.out = args, out
        self.fe_env = load_env(ROOT / ".env")
        self.be_env = load_env(BACKEND / ".env")
        self.api = (args.api or self.fe_env.get("VITE_API_BASE_URL") or "http://localhost:8000").rstrip("/")
        self.origin = self.be_env.get("FRONTEND_ORIGIN", "http://localhost:5173")
        self.chain_id = int(self.be_env.get("ESCROW_CHAIN_ID", "11155111"))
        self.contract = (self.be_env.get("ESCROW_CONTRACT_ADDRESS") or "").lower()
        self.run_id = datetime.now().strftime("%m%d%H%M%S") + secrets.token_hex(1)
        self.steps: list[StepRecord] = []
        self.cur: StepRecord | None = None
        self.notes: list[str] = []
        self.probe: dict | None = None
        self.db: Db | None = None
        self.chain: Chain | None = None
        self.abi = json.loads((ROOT / "src/config/FreelinkEscrow.abi.json").read_text(encoding="utf-8"))
        self.anon = self.new_http()
        self.client = self.new_actor("client", "client")
        self.freelancer = self.new_actor("freelancer", "freelancer")
        self.job_id = self.proposal_id = self.project_id = self.agreement = None

    # ---- plumbing ----------------------------------------------------------

    def new_http(self) -> httpx.Client:
        # Origin ถูกส่งทุกคำขอเหมือนที่เบราว์เซอร์ทำเมื่อหน้าเว็บ (5173) เรียก API (8000) ข้ามต้นทาง
        # ต่อผ่าน 127.0.0.1 แทน localhost: Windows ลอง IPv6 (::1) ก่อนแล้วรอ ~2 วินาทีค่อยถอยไป IPv4 ซึ่งจะทำให้เวลาที่วัดได้ดูช้ากว่าจริง
        # (backend ตาม README ฟังที่ 127.0.0.1 อยู่แล้ว; cookie เป็นของ host ที่สคริปต์ใช้เอง ไม่เกี่ยวกับ cookie ในเบราว์เซอร์)
        return httpx.Client(base_url=self.api.replace("//localhost", "//127.0.0.1"), headers={"Origin": self.origin}, timeout=30)

    def new_actor(self, name: str, role: str) -> Actor:
        return Actor(name, role, f"flowtest-{self.run_id}-{name}@example.net", "Flow-" + secrets.token_urlsafe(9), self.new_http())

    def begin(self, no: str, title: str, layers: str, contract: tuple[str, str]) -> None:
        kind, text = contract
        self.out.raw()
        self.out.raw(self.out.paint("1", f"━━ ขั้นที่ {no} · {title}"))
        self.out.raw(self.out.paint("2", f"   ชั้นที่เกี่ยวข้อง : {layers}"))
        self.out.raw(f"   Smart Contract    : {self.out.paint(Out.CONTRACT[kind], text)}")
        self.cur = StepRecord(no, title, layers, kind, text)
        self.steps.append(self.cur)

    def skip(self, step: tuple, reason: str) -> None:
        no, title, layers, (kind, text) = step
        self.out.raw()
        self.out.raw(self.out.paint("2", f"━━ ขั้นที่ {no} · {title}   ⏭ ข้าม: {reason}"))
        self.out.raw(self.out.paint("2", f"   ชั้น: {layers}  ·  Smart Contract: ") + self.out.paint(Out.CONTRACT[kind], text))
        self.steps.append(StepRecord(no, title, layers, kind, text, skipped="ข้าม"))

    def check(self, ok: bool | None, text: str) -> bool | None:
        self.out.mark(ok, text)
        if self.cur and ok is False:
            self.cur.failures += 1
        elif self.cur and ok is None:
            self.cur.warnings += 1
        return ok

    def note(self, text: str) -> None:
        self.out.raw(f"      {self.out.paint('2', text)}")

    def call(self, actor: Actor | None, method: str, path: str, *, json=None, expect=None, soft=False,
             headers=None, tag: str = "FE→BE") -> httpx.Response:
        client = (actor or Actor("anonymous", "", "", "", self.anon)).http
        label = actor.name if actor else "anonymous"
        started = time.perf_counter()
        try:
            response = client.request(method, path, json=json, headers=headers)
        except httpx.HTTPError as error:
            self.out.line(tag, f"{label:<10} {method:<6} {path} → เชื่อมต่อไม่ได้ ({type(error).__name__})")
            raise Abort(f"เรียก {self.api}{path} ไม่ได้ — backend เปิดอยู่ไหม") from None
        elapsed = (time.perf_counter() - started) * 1000
        request_id = response.headers.get("x-request-id", "")[:8]
        self.out.line(tag, f"{label:<10} {method:<6} {path} → {response.status_code} ({elapsed:.0f} ms, req={request_id})")
        if expect is not None:
            wanted = expect if isinstance(expect, tuple) else (expect,)
            if response.status_code not in wanted:
                detail = self.body(response)
                code = detail.get("code") if isinstance(detail, dict) else ""
                message = detail.get("message") if isinstance(detail, dict) else str(detail)[:120]
                self.check(False, f"คาด {'/'.join(map(str, wanted))} แต่ได้ {response.status_code} {code} {message}")
                if not soft:
                    raise Abort(f"{method} {path} ล้มเหลว ({response.status_code} {code})")
        return response

    @staticmethod
    def body(response: httpx.Response):
        try:
            return response.json()
        except ValueError:
            return response.text

    def db_show(self, table: str, sql: str, params=(), limit: int = 4) -> list[dict]:
        if not self.db:
            return []
        rows = self.db.rows(sql, params)
        if not rows:
            self.out.line("DB", f"{table}: (ไม่พบแถว)")
        for row in rows[:limit]:
            self.out.line("DB", f"{table:<20} " + "  ".join(f"{key}={fmt(value)}" for key, value in row.items()))
        return rows

    def node(self, command: str, payload: dict | None = None) -> dict | None:
        try:
            done = subprocess.run(
                ["node", str(ROOT / "scripts/flow_trace_frontend.mjs"), command], cwd=ROOT, input=json.dumps(payload or {}),
                capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.check(None, f"รัน node ไม่ได้ ({type(error).__name__}) — ข้ามการตรวจโค้ด frontend")
            return None
        if done.returncode != 0:
            self.check(None, "โหลดโค้ด frontend ผ่าน Vite ไม่สำเร็จ: " + (done.stderr.strip().splitlines() or ["?"])[0][:140])
            return None
        return json.loads(done.stdout)

    # ---- steps --------------------------------------------------------------

    def step_topology(self) -> None:
        self.begin("0", "ตรวจว่า 3 ชั้นพร้อมและต่อกันถูกที่", "FE · BE · DB · CHAIN", ("read", "อ่านอย่างเดียว (RPC eth_call / eth_getCode ไม่เสียแก๊ส)"))
        health = self.call(None, "GET", "/health", tag="BE")
        self.check(health.status_code == 200 and self.body(health) == {"status": "ok", "database": "ok"},
                   "Backend ตอบ /health และต่อ PostgreSQL ได้")
        try:
            page = httpx.get(self.origin, timeout=4)
            self.out.line("FE", f"GET {self.origin} → {page.status_code}")
            self.check(page.status_code == 200 and 'id="root"' in page.text, "Vite dev server ของ frontend ตอบหน้า React")
        except httpx.HTTPError:
            self.check(None, f"เปิด {self.origin} ไม่ได้ (รัน npm run dev หรือยัง?) — ข้ามเฉพาะการตรวจหน้าเว็บ")

        if psycopg and self.be_env.get("DATABASE_URL"):
            try:
                self.db = Db(self.be_env["DATABASE_URL"])
                self.out.line("DB", "ต่อ PostgreSQL ตรงจากสคริปต์ได้ (ใช้อ่านกลับเพื่อโชว์ว่าข้อมูลลงตารางไหน)")
            except psycopg.Error:
                self.check(None, "ต่อ PostgreSQL ตรงไม่ได้ — จะไม่แสดงบรรทัด [DB] แต่ยังเดินผ่าน API ได้")

        if not self.args.skip_frontend:
            self.probe = self.node("probe")
        fe = (self.probe or {}).get("config")
        if fe:
            self.out.line("FE", f"ค่าที่เบราว์เซอร์จะใช้: api={fe['apiBaseUrl']} chain={fe['chainId']} contract={fe['contractAddress']}")
            same_host = lambda url: url.rstrip("/").replace("127.0.0.1", "localhost")  # noqa: E731
            self.check(same_host(fe["apiBaseUrl"]) == same_host(self.api), "VITE_API_BASE_URL ของ frontend ชี้มาที่ backend ตัวนี้")
            self.check(fe["chainId"] == self.chain_id, f"chain id ตรงกัน (frontend {fe['chainId']} / backend {self.chain_id})")
            self.check((fe["contractAddress"] or "").lower() == self.contract and bool(self.contract),
                       "Contract Address ของ frontend = ESCROW_CONTRACT_ADDRESS ของ backend")
        same_abi = self.abi == json.loads((ROOT / "smart-contact/abi/FreelinkEscrow.abi.json").read_text(encoding="utf-8"))
        self.check(same_abi, "ABI ใน src/config เหมือน smart-contact/abi (ไม่มีใครลืม copy หลังแก้ contract)")

        for method in ("POST", "PATCH", "DELETE"):
            pre = self.anon.request("OPTIONS", "/jobs", headers={"Access-Control-Request-Method": method,
                                                                "Access-Control-Request-Headers": "content-type"})
            allowed = pre.headers.get("access-control-allow-origin") == self.origin and \
                pre.headers.get("access-control-allow-credentials") == "true"
            self.check(allowed, f"CORS preflight {method} จาก {self.origin} ผ่าน (ส่ง cookie ข้ามพอร์ตได้)")
        evil = self.anon.request("OPTIONS", "/jobs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
        self.check("access-control-allow-origin" not in evil.headers, "ต้นทางแปลกปลอม (evil.example) ไม่ได้รับอนุญาต CORS")

        rpc_url = self.be_env.get("ESCROW_RPC_URL", "")
        if self.args.skip_chain or not (rpc_url and self.contract):
            self.check(None, "ไม่มี ESCROW_RPC_URL / ESCROW_CONTRACT_ADDRESS ใน backend/.env — ข้ามการอ่านเชน")
            return
        try:
            self.chain = Chain(rpc_url, self.contract, self.abi)
            remote_chain = int(self.chain.rpc("eth_chainId"), 16)
            block = int(self.chain.rpc("eth_blockNumber"), 16)
            self.out.line("CHAIN", f"RPC {self.chain.host} → chain {remote_chain}, block ล่าสุด {block}")
            self.check(remote_chain == self.chain_id, "RPC อยู่เครือข่ายเดียวกับที่ตั้งค่าไว้")
            code = self.chain.rpc("eth_getCode", [self.contract, "latest"])
            self.check(code not in ("0x", None), f"มี Smart Contract อยู่ที่ {self.contract} (bytecode {(len(code) - 2) // 2} bytes)")
            (arbiter,) = self.chain.read("arbiter()", [], [], ["address"])
            (fee_bps,) = self.chain.read("feeBps()", [], [], ["uint16"])
            (revisions,) = self.chain.read("maxRevisions()", [], [], ["uint8"])
            (review,) = self.chain.read("reviewPeriod()", [], [], ["uint64"])
            (max_duration,) = self.chain.read("MAX_DURATION()", [], [], ["uint64"])
            self.out.line("CHAIN", f"นโยบายที่ฝังใน contract: arbiter={arbiter} fee={fee_bps / 100:g}% "
                                   f"แก้งานได้ {revisions} ครั้ง ตรวจรับ {review // 86400} วัน duration สูงสุด {max_duration // 86400} วัน")
        except Exception as error:  # noqa: BLE001 — สคริปต์วินิจฉัย: รายงานชนิด error แล้วเดินต่อโดยไม่มีเชน
            self.chain = None
            self.check(False, f"อ่านเชนไม่สำเร็จ ({type(error).__name__}: {str(error)[:100]})")

    def step_frontend_contract(self) -> None:
        self.begin("1", "Frontend เรียก endpoint ที่ Backend มีจริงหรือไม่", "FE → BE (ตรวจสัญญา ไม่มีข้อมูลไหลจริง)", ("none", "ไม่เกี่ยว"))
        if not self.probe:
            self.check(None, "ไม่มีผล probe ของ frontend (--skip-frontend หรือโหลดไม่ได้) — ข้ามขั้นนี้")
            self.cur.skipped = "ข้าม"
            return
        spec = self.anon.get("/openapi.json").json()

        def norm(path: str) -> str:
            return re.sub(r"\{[^}]*\}", "{}", path)

        operations = {(method.upper(), norm(path)) for path, item in spec["paths"].items() for method in item
                      if method in ("get", "post", "patch", "put", "delete")}
        paths = {path for _, path in operations}
        used, missing = set(), []
        for call in self.probe["calls"]:
            for request in call["requests"]:
                key = (request["http"], norm(request["path"]))
                used.add(key)
                if key not in operations:
                    reason = "path มีแต่ method ไม่ตรง (405)" if key[1] in paths else "backend ไม่มี route นี้ (404)"
                    missing.append((call["service"], key, reason))
                elif self.args.verbose:
                    self.out.line("FE→BE", f"{call['service']:<34} {key[0]:<6} {request['path']}")
        total = len(used)
        self.out.line("FE", f"โค้ด service ของ frontend ส่ง request ได้ {total} แบบ จาก {len(self.probe['calls'])} เมธอด")
        if missing:
            self.check(None, f"ตรงกับ backend {total - len(missing)}/{total} — ที่เหลือจะได้ 404/405 ถ้าผู้ใช้กดเมนูนั้น:")
        else:
            self.check(True, f"ทุก request ของ frontend มี route รองรับใน backend ({total}/{total})")
        for service, (method, path), reason in missing:
            self.out.raw(f"        - {service:<32} {method} {path}  → {reason}")
            self.notes.append(f"Frontend เรียก {method} {path} ({service}) แต่ {reason}")
        unused = sorted(operations - used)
        self.note("Backend มีอีก " + str(len(unused)) + " route ที่ไม่ผ่าน axios ของ service layer (เข้าด้วย redirect/ลิงก์/health เช่น Google login, ดาวน์โหลดไฟล์): "
                  + ", ".join(f"{m} {p}" for m, p in unused))

    def register(self, actor: Actor) -> None:
        response = self.call(actor, "POST", "/auth/register", expect=204,
                             json={"name": f"FlowTest {actor.name.title()}", "email": actor.email,
                                   "password": actor.password, "role": actor.role})
        cookie = next((c for c in response.headers.get_list("set-cookie") if c.startswith("freelink_session=")), "")
        flags = ";".join(part.strip() for part in cookie.split(";")[1:] if part.strip().split("=")[0].lower() in ("httponly", "samesite", "max-age"))
        self.out.line("BE", f"Set-Cookie: freelink_session={actor.token[:6]}…; {flags}", indent=4)
        me = self.call(actor, "GET", "/auth/me", expect=200).json()
        actor.user_id, actor.profile_id = me["id"], me["profileId"]
        self.check(me["role"] == actor.role and me["email"] == actor.email, f"/auth/me คืนบัญชี {actor.role} ที่เพิ่งสมัคร")
        self.db_show("users", "SELECT id, email, role, status FROM users WHERE id = %s", (actor.user_id,))
        self.db_show("user_credentials", "SELECT user_id, substr(password_hash, 1, 26) || '…' AS password_hash FROM user_credentials WHERE user_id = %s", (actor.user_id,))
        rows = self.db_show("login_sessions", "SELECT left(token_hash, 12) AS token_hash, expires_at FROM login_sessions WHERE user_id = %s", (actor.user_id,))
        if rows:
            digest = hashlib.sha256(actor.token.encode()).hexdigest()[:12]
            self.check(rows[0]["token_hash"] == digest, "DB เก็บเฉพาะ sha256 ของ token (cookie ตัวจริงไม่อยู่ใน DB) และรหัสผ่านเป็น Argon2id")

    def step_accounts(self) -> None:
        self.begin("2", "สมัครสมาชิก 2 บัญชี (client / freelancer)", "FE → BE → DB", ("none", "ไม่เกี่ยว"))
        self.note(f"ใช้อีเมล flowtest-{self.run_id}-*@example.net — เข้าสู่ระบบในหน้าเว็บด้วยบัญชีนี้เพื่อดูข้อมูลเดียวกันได้ (ดูท้ายรายงาน)")
        self.register(self.client)
        self.register(self.freelancer)

    def job_payload(self) -> dict:
        return {
            "title": f"[FLOWTEST {self.run_id}] ออกแบบโลโก้ร้านกาแฟ",
            "description": "งานทดสอบจาก scripts/flow_trace.py — ลบได้ด้วย --cleanup",
            "category": "ออกแบบ", "skills": ["Illustrator", "Branding"], "deliverables": ["ไฟล์โลโก้ AI/PNG", "คู่มือการใช้งานโลโก้"],
            "budgetMin": 1000, "budgetMax": 2000, "budgetType": "fixed", "duration": "1-2 สัปดาห์", "experience": "intermediate",
        }

    def step_job(self) -> None:
        self.begin("3", "Client ประกาศงาน → ทุกคนเห็นในหน้า Browse Jobs", "FE → BE → DB", ("none", "ไม่เกี่ยว"))
        job = self.call(self.client, "POST", "/jobs", expect=201, json=self.job_payload()).json()
        self.job_id = job["id"]
        self.db_show("jobs", "SELECT id, status, budget_min, budget_max, client_id FROM jobs WHERE id = %s", (self.job_id,))
        listing = self.call(None, "GET", f"/jobs?q=FLOWTEST%20{self.run_id}", expect=200).json()
        self.check(any(item["id"] == self.job_id for item in listing), "ผู้ใช้ที่ยังไม่ล็อกอินค้นเจองานนี้ (ข้อมูลเดียวกับหน้า Browse Jobs)")
        client_card = self.call(None, "GET", f"/jobs/{self.job_id}", expect=200).json()["client"]
        self.check(client_card.get("jobsPosted") is not None and client_card.get("hireRate") is not None,
                   "หน้า Job Details ได้สถิติของลูกค้า (jobsPosted/hireRate) ไม่ใช่ช่องว่าง")
        self.check(not {"email", "bio", "contactName"} & client_card.keys(), "หน้า public ไม่เปิดเผยอีเมล/ข้อมูลบริษัทของลูกค้า")

    def step_proposal(self) -> None:
        self.begin("4", "Freelancer ยื่นข้อเสนอ → Client ได้การแจ้งเตือน", "FE → BE → DB", ("none", "ไม่เกี่ยว"))
        proposal = self.call(self.freelancer, "POST", f"/jobs/{self.job_id}/proposals", expect=201, json={
            "bidAmount": 1500, "deliveryDays": 10, "coverLetter": "สนใจงานนี้ครับ เคยทำงานแบรนด์ร้านอาหารมาหลายเจ้า", "attachments": [],
        }).json()
        self.proposal_id = proposal["id"]
        self.db_show("proposals", "SELECT id, status, bid_amount, delivery_days FROM proposals WHERE id = %s", (self.proposal_id,))
        duplicate = self.call(self.freelancer, "POST", f"/jobs/{self.job_id}/proposals", expect=409, soft=True,
                              json={"bidAmount": 1500, "deliveryDays": 10, "coverLetter": "ยื่นซ้ำ"})
        self.check(self.body(duplicate).get("code") == "DUPLICATE_PROPOSAL", "ยื่นซ้ำถูกปฏิเสธ DUPLICATE_PROPOSAL (กันด้วย unique constraint ใน DB ด้วย)")
        applicant = self.call(self.client, "GET", f"/jobs/{self.job_id}/proposals", expect=200).json()[0]["freelancer"]
        self.check(applicant.get("name") and applicant.get("skills") is not None and applicant.get("completedJobs") is not None,
                   "หน้าเปรียบเทียบข้อเสนอได้ข้อมูลฟรีแลนซ์ (name/skills/completedJobs) ไม่ใช่ช่องว่าง")
        inbox = self.call(self.client, "GET", "/notifications", expect=200).json()
        self.check(any(item["type"] == "proposal" for item in inbox), f"Client เห็นแจ้งเตือน “{inbox[0]['title']}” (ระฆังบน Navbar)" if inbox else "ไม่มีแจ้งเตือน")
        self.db_show("notifications", "SELECT type, title, read_at IS NOT NULL AS read FROM notifications WHERE user_id = %s ORDER BY created_at", (self.client.user_id,))

    def step_hire(self) -> None:
        self.begin("5", "Client คัดเลือกและจ้าง → เกิด Project + ห้องแชท", "FE → BE → DB", ("none", "ไม่เกี่ยว — ยังไม่มีเงินเข้า contract"))
        self.call(self.client, "PATCH", f"/proposals/{self.proposal_id}", expect=200, json={"status": "shortlisted"})
        hired = self.call(self.client, "POST", f"/proposals/{self.proposal_id}/hire", expect=200).json()
        self.project_id = hired["project"]["id"]
        self.check(hired["job"]["status"] == "in_progress", "งานเปลี่ยนเป็น in_progress (หายจากหน้า Browse Jobs)")
        project = hired["project"]
        self.check(bool((project.get("freelancer") or {}).get("name") and (project.get("client") or {}).get("name") and project.get("startDate")),
                   "หน้าโปรเจกต์ได้ชื่อทั้งสองฝ่ายและวันเริ่มงาน ไม่ขึ้น “—”")
        self.db_show("projects", "SELECT id, status, budget, due_at FROM projects WHERE id = %s", (self.project_id,))
        self.db_show("proposals", "SELECT id, status FROM proposals WHERE id = %s", (self.proposal_id,))
        self.db_show("message_threads", "SELECT id, project_id FROM message_threads WHERE project_id = %s", (self.project_id,))
        news = self.call(self.freelancer, "GET", "/notifications", expect=200).json()
        self.check(any(item["title"] == "คุณได้รับงานแล้ว" for item in news), "Freelancer ได้แจ้งเตือน “คุณได้รับงานแล้ว”")

    def link_wallet(self, actor: Actor) -> str:
        actor.wallet = Account.create()
        address = actor.wallet.address
        challenge = self.call(actor, "POST", "/wallet/challenges", expect=201, json={"address": address, "chainId": self.chain_id}).json()
        first = challenge["message"].splitlines()
        self.out.line("BE", f"ข้อความให้เซ็น: “{first[0]}” / “{first[2][:62]}…”", indent=4)
        signature = actor.wallet.sign_message(encode_defunct(text=challenge["message"])).signature
        self.out.line("WALLET", f"{actor.name} เซ็นข้อความในเครื่อง (เหมือนกด Sign ใน MetaMask) — ไม่มีธุรกรรม ไม่เสียแก๊ส", indent=4)
        link = self.call(actor, "POST", "/wallet/verifications", expect=200,
                         json={"challengeId": challenge["challengeId"], "signature": "0x" + bytes(signature).hex()}).json()
        self.check(link["address"] == address.lower(), f"Backend กู้ address จากลายเซ็นได้ตรง ({address[:8]}…{address[-4:]})")
        self.db_show("wallet_links", "SELECT user_id, address, chain_id FROM wallet_links WHERE user_id = %s", (actor.user_id,))
        return address.lower()

    def step_wallets(self) -> None:
        self.begin("6", "ผูก Wallet กับบัญชี (เซ็นข้อความพิสูจน์ความเป็นเจ้าของ)", "FE → WALLET → BE → DB",
                   ("none", "ไม่เกี่ยว — เป็นลายเซ็นนอกเชน ไม่เรียก contract ไม่เสียแก๊ส"))
        self.link_wallet(self.client)
        self.link_wallet(self.freelancer)

    def step_prepare(self) -> None:
        self.begin("7", "เตรียมข้อตกลง Escrow (terms + hash + escrowId)", "FE → BE → CHAIN(อ่าน) → DB",
                   ("read", "อ่านอย่างเดียว — backend ถาม RPC: chainId, block ล่าสุด, arbiter(), maxRevisions(), MAX_DURATION(), getEscrow()"))
        self.agreement = self.call(self.client, "POST", f"/projects/{self.project_id}/escrow/prepare", expect=200,
                                   json={"milestoneNumber": 1, "confidential": True}).json()
        terms = json.loads(self.agreement["termsJson"])
        wei = int(terms["amountWei"])
        self.out.line("BE", f"สร้างข้อตกลง: {terms['amountThb']} THB ÷ {terms['thbPerEth']} THB/ETH = {eth(wei)} ({wei} wei)", indent=4)
        self.out.line("BE", f"deadline={datetime.fromtimestamp(terms['deadline'], timezone.utc):%Y-%m-%d %H:%M}Z "
                            f"client={terms['client'][:10]}… freelancer={terms['freelancer'][:10]}… แก้ได้ {terms['revisionPolicy']['maxRevisions']} ครั้ง", indent=4)
        self.out.line("BE", f"projectKey={terms['projectKey'][:14]}…  termsHash={self.agreement['termsHash'][:14]}…  expectedEscrowId={self.agreement['expectedEscrowId'][:14]}…", indent=4)
        self.db_show("escrow_agreements", "SELECT id, status, milestone_number AS m, attempt_number AS a, left(terms_hash, 12) AS terms_hash, "
                     "left(expected_escrow_id, 12) AS escrow_id, client_consented_at, next_scan_block FROM escrow_agreements WHERE project_id = %s", (self.project_id,))
        self.check(self.agreement["status"] == "prepared" and self.agreement["escrowId"] is None, "สถานะ prepared (ยังไม่มีเงินบนเชน escrowId ยังเป็น null)")

    def step_crosscheck(self) -> None:
        self.begin("8", "ตรวจว่า 3 ชั้นคำนวณค่าเดียวกัน (Python ↔ Frontend ↔ Contract)", "FE · BE · CHAIN(อ่าน)",
                   ("read", "อ่านอย่างเดียว — computeEscrowId(), getEscrow(), quote()"))
        agreement, terms = self.agreement, json.loads(self.agreement["termsJson"])
        py_hash = "0x" + keccak(agreement["termsJson"].encode("utf-8")).hex()
        self.check(py_hash == agreement["termsHash"], "terms hash: keccak256 ที่คำนวณในสคริปต์ = ค่าที่ backend เก็บ")
        fe = self.node("hash", {"termsJson": agreement["termsJson"]}) if not self.args.skip_frontend else None
        if fe:
            self.check(fe["hash"] == agreement["termsHash"],
                       "terms hash: hashTerms() ตัวจริงของ frontend = backend (ถ้าไม่ตรง หน้า Escrow จะขึ้น “ตรวจ hash ไม่ได้” และกดฝากไม่ได้)")
        project_key = bytes.fromhex(terms["projectKey"][2:])
        py_id = "0x" + keccak(encode(["address", "bytes32"], [terms["client"], project_key])).hex()
        self.check(py_id == agreement["expectedEscrowId"], "escrowId: คำนวณเองจาก (client, projectKey) = ค่าที่ backend เก็บ")
        thb = int(Decimal(terms["amountThb"]) * 100)
        self.check(thb * 10**18 // int(Decimal(terms["thbPerEth"]) * 100) == int(terms["amountWei"]), "ยอด wei: แปลง THB→ETH ซ้ำเองได้ค่าเดียวกัน")
        self.check(terms["contract"] == self.contract and terms["chainId"] == self.chain_id,
                   "terms ผูกกับ contract และ chain ของ backend (หน้าเว็บจะเทียบค่านี้กับ .env ของตัวเอง)")
        if not self.chain:
            self.check(None, "ไม่มีการเชื่อมต่อเชน — ข้ามการเทียบกับ contract")
            return
        try:
            (onchain_id,) = self.chain.read("computeEscrowId(address,bytes32)", ["address", "bytes32"], [terms["client"], project_key], ["bytes32"])
            self.check("0x" + onchain_id.hex() == agreement["expectedEscrowId"], "escrowId: contract.computeEscrowId() ตอบค่าเดียวกับ backend")
            state = self.chain.escrow(agreement["expectedEscrowId"])
            self.out.line("CHAIN", f"getEscrow(expectedEscrowId) → status={CHAIN_STATUS[state['status']]} client={state['client'][:10]}…", indent=4)
            self.check(state["status"] == 0, "บนเชนยังไม่มีเงินฝากสำหรับข้อตกลงนี้ (สถานะ unfunded) ตรงกับ DB = prepared")
            fee, total = self.chain.read("quote(uint256)", ["uint256"], [int(terms["amountWei"])], ["uint256", "uint256"])
            self.out.line("CHAIN", f"quote({terms['amountWei']}) → ค่าจ้าง {eth(int(terms['amountWei']))} + ค่าธรรมเนียม {eth(fee)} = ต้องส่ง msg.value {eth(total)}", indent=4)
            self.deposit_value = total
        except Exception as error:  # noqa: BLE001
            self.check(False, f"อ่าน contract ไม่สำเร็จ ({type(error).__name__}: {str(error)[:100]})")

    def step_consent(self) -> None:
        self.begin("9", "Client ยอมรับข้อตกลง (ขั้นสุดท้ายก่อนเซ็นฝากเงิน)", "FE → BE → DB", ("none", "ไม่เกี่ยว — บันทึกการยอมรับใน DB เท่านั้น"))
        terms = json.loads(self.agreement["termsJson"])
        base = {"agreementId": self.agreement["id"], "tosVersion": terms["tosVersion"], "accepted": True}
        wrong = self.call(self.client, "POST", f"/projects/{self.project_id}/escrow/consent", expect=409, soft=True,
                          json={**base, "termsHash": "0x" + "00" * 32})
        self.check(self.body(wrong).get("code") == "ESCROW_TERMS_CHANGED", "ส่ง hash ผิด → ถูกปฏิเสธ ESCROW_TERMS_CHANGED (กันข้อตกลงถูกสลับ)")
        agreement = self.call(self.client, "POST", f"/projects/{self.project_id}/escrow/consent", expect=200,
                              json={**base, "termsHash": self.agreement["termsHash"]}).json()
        self.check(agreement["clientConsentedAt"] is not None, "บันทึกเวลายอมรับข้อตกลงแล้ว")
        self.db_show("escrow_agreements", "SELECT id, status, client_consented_at FROM escrow_agreements WHERE id = %s", (self.agreement["id"],))

    def step_deposit(self) -> bool:
        self.begin("10", "ฝากเงินเข้า Escrow  ← จุดที่ต้องใช้ MetaMask", "FE → WALLET → CHAIN(เขียน) → BE(อ่านเชน) → DB",
                   ("write", "เขียนลง contract — depositEscrow() payable เสียแก๊สและ ETH จริงบน Sepolia"))
        terms = json.loads(self.agreement["termsJson"])
        total = getattr(self, "deposit_value", None)
        self.out.line("FE", "หน้า EscrowPayment จะเรียก contract.depositEscrow(...) ผ่าน MetaMask ด้วยค่าเหล่านี้ (สคริปต์ไม่ส่งให้):", indent=4)
        self.note(f"depositEscrow(projectKey={terms['projectKey'][:12]}…, freelancer={terms['freelancer'][:10]}…, deadline={terms['deadline']}, "
                  f"termsHash={self.agreement['termsHash'][:12]}…, amount={terms['amountWei']})  value={total if total else '?'} wei")
        self.note("จากนั้นหน้าเว็บ POST /projects/{id}/escrow/transactions ส่ง tx hash → backend อ่าน receipt/event EscrowFunded จาก RPC")
        self.note("รอบล็อกถึงสถานะ finalized (Sepolia ≈ 13 นาที) แล้ว escrow_worker จึงเปลี่ยน DB prepared → funded")
        if not self.args.simulate_funding:
            self.cur.skipped = "หยุดที่นี่"
            self.out.raw(self.out.paint("33", "    ⏸  หยุดเดินที่นี่ — ขั้นต่อไปต้องมีเงินจริงบนเชน ใช้ --simulate-funding เพื่อจำลองแล้วดูขั้นตอนส่งงาน/ตรวจรับต่อ"))
            return False
        if not self.db:
            raise Abort("--simulate-funding ต้องต่อ PostgreSQL ตรงได้")
        self.out.line("SIM", "จำลอง: UPDATE escrow_agreements SET status='funded' ← ไม่มีธุรกรรมบนเชนจริง ใช้เพื่อดูขั้นตอนหลังฝากเงินเท่านั้น", indent=4)
        self.db.execute("UPDATE escrow_agreements SET status = 'funded' WHERE id = %s AND status = 'prepared'", (self.agreement["id"],))
        project = self.call(self.client, "GET", f"/projects/{self.project_id}", expect=200).json()
        self.check(project["escrowStatus"] == "funded" and project["canSubmitWork"], "API รายงาน escrowStatus=funded และ canSubmitWork=true (หน้า Submit Work เปิดให้กด)")
        return True

    WORK_STEP = ("11", "Freelancer ส่งงาน → Client ขอแก้ → ส่งใหม่", "FE → BE → DB",
                 ("gap", "ยังไม่ผูก — submitWork()/requestRevision() บน contract ไม่ถูกเรียก ทั้งหมดเป็น DB อย่างเดียว"))
    APPROVE_STEP = ("12", "Client อนุมัติงาน → เงินถูกปล่อยหรือยัง?", "FE → BE → DB → (CHAIN ควรเกี่ยวแต่ยังไม่ผูก)",
                    ("gap", "ยังไม่ผูก — approve ไม่เรียก releasePayment() เงินยังค้างใน contract"))

    def step_work(self) -> None:
        self.begin(*self.WORK_STEP)
        payload = b"FLOWTEST deliverable v1\n"
        sent = self.call(self.freelancer, "POST", f"/projects/{self.project_id}/submissions", expect=201, json={
            "title": "โลโก้ร้านกาแฟ เวอร์ชัน 1", "description": "ส่งไฟล์โลโก้รอบแรก พร้อมคู่มือการใช้งานฉบับย่อ", "link": "https://example.net/flowtest",
            "files": [{"name": "logo-v1.txt", "content": base64.b64encode(payload).decode()}],
        }).json()
        first = sent["submissions"][0]
        self.check(sent["status"] == "in_review", "สถานะโปรเจกต์เปลี่ยนเป็น in_review")
        self.db_show("projects", "SELECT id, status FROM projects WHERE id = %s", (self.project_id,))
        self.db_show("work_submissions", "SELECT id, status, title FROM work_submissions WHERE project_id = %s", (self.project_id,))
        self.db_show("work_attachments", "SELECT name, length(content) AS bytes FROM work_attachments WHERE submission_id = %s", (first["id"],))
        download = self.call(self.client, "GET", f"/projects/{self.project_id}/work-files/{first['files'][0]['id']}", expect=200)
        self.check(download.content == payload, "Client ดาวน์โหลดไฟล์ได้ตรงกับที่ส่ง (เก็บเป็น bytea ใน DB ไม่ใช่บนเชน)")
        self.call(self.client, "POST", f"/projects/{self.project_id}/request-revision", expect=200,
                  json={"submissionId": first["id"], "feedback": "ช่วยปรับสีให้เข้มขึ้นอีกนิดครับ"})
        self.db_show("work_submissions", "SELECT id, status, feedback FROM work_submissions WHERE id = %s", (first["id"],))
        again = self.call(self.freelancer, "POST", f"/projects/{self.project_id}/submissions", expect=201, json={
            "title": "โลโก้ร้านกาแฟ เวอร์ชัน 2", "description": "ปรับสีตามที่ขอแล้ว ส่งไฟล์ใหม่ทั้งชุด", "files": [],
        }).json()
        self.second_submission = again["submissions"][0]["id"]
        self.check(again["status"] == "in_review", "ส่งรอบแก้แล้ว กลับเป็น in_review")

    def step_approve(self) -> None:
        self.begin(*self.APPROVE_STEP)
        done = self.call(self.client, "POST", f"/projects/{self.project_id}/approve", expect=200, json={"submissionId": self.second_submission}).json()
        self.check(done["status"] == "completed", "โปรเจกต์เป็น completed")
        rows = self.db_show("escrow_agreements", "SELECT id, status FROM escrow_agreements WHERE id = %s", (self.agreement["id"],))
        self.out.line("BE", f"escrowStatus={done['escrowStatus']} releasedAmount={done['releasedAmount']} escrowAmount={done['escrowAmount']}", indent=4)
        stuck = bool(rows) and rows[0]["status"] == "funded" and done["releasedAmount"] == 0
        self.check(None if stuck else True,
                   "อนุมัติแล้ว แต่ escrow ยัง “funded” ไม่ใช่ “released” — approve เป็นแค่สถานะใน DB; "
                   "เงินจะขยับก็ต่อเมื่อ client เซ็น releasePayment() บน MetaMask แล้ว backend อ่านเจอ event PaymentReleased"
                   if stuck else "escrow เปลี่ยนเป็น released แล้ว")
        if stuck:
            self.notes.append("Backend approve งานแล้วโปรเจกต์เป็น completed แต่เงินใน escrow ยัง funded (ต้องเซ็น releasePayment ต่างหาก)")

    def step_social(self) -> None:
        self.begin("13", "แชทและการแจ้งเตือนที่เกิดจากขั้นก่อนหน้า", "FE → BE → DB", ("none", "ไม่เกี่ยว"))
        thread = self.call(self.client, "GET", "/messages/threads", expect=200).json()[0]
        self.call(self.client, "POST", f"/messages/threads/{thread['id']}/messages", expect=201, json={"text": "ขอบคุณสำหรับงานครับ"})
        inbox = self.call(self.freelancer, "GET", "/messages/threads", expect=200).json()[0]
        self.check(inbox["unread"] and inbox["lastMessage"]["text"] == "ขอบคุณสำหรับงานครับ", "Freelancer เห็นข้อความใหม่ (unread=true) ในกล่องข้อความ")
        for actor in (self.client, self.freelancer):
            titles = [item["title"] for item in self.call(actor, "GET", "/notifications", expect=200).json()]
            self.out.line("BE", f"แจ้งเตือนของ {actor.name}: " + " · ".join(titles), indent=4)

    def step_guards(self) -> None:
        self.begin("14", "ด่านความปลอดภัยของ API", "FE → BE", ("none", "ไม่เกี่ยว"))
        def denied(response: httpx.Response, status: int, code: str, text: str) -> None:
            self.check(response.status_code == status and self.body(response).get("code") == code, text)
        denied(self.call(None, "GET", "/projects", soft=True, expect=401), 401, "LOGIN_REQUIRED", "ไม่ล็อกอิน → 401 LOGIN_REQUIRED")
        # ส่ง payload ที่ถูกต้อง เพราะ FastAPI ตรวจ body (422) ก่อนเข้า handler ที่เช็กบทบาท ถ้าส่ง {} จะไม่ได้ทดสอบสิทธิ์จริง
        denied(self.call(self.client, "POST", "/jobs", soft=True, expect=403, headers={"Origin": "http://evil.example"}, json=self.job_payload()),
               403, "INVALID_ORIGIN", "ต้นทางแปลกปลอมพร้อม cookie จริง → 403 INVALID_ORIGIN (กัน CSRF)")
        denied(self.call(self.freelancer, "POST", "/jobs", soft=True, expect=403, json=self.job_payload()),
               403, "FORBIDDEN", "Freelancer ประกาศงานไม่ได้ → 403")
        denied(self.call(self.freelancer, "POST", f"/projects/{self.project_id}/approve", soft=True, expect=403,
                         json={"submissionId": str(uuid.uuid4())}), 403, "FORBIDDEN", "Freelancer อนุมัติงานของตัวเองไม่ได้ → 403")
        denied(self.call(self.freelancer, "POST", f"/projects/{self.project_id}/escrow/prepare", soft=True, expect=403, json={}),
               403, "FORBIDDEN", "Freelancer เตรียมข้อตกลงเงินฝากไม่ได้ → 403")
        self.call(self.client, "POST", "/auth/logout", expect=204)
        self.check(self.call(self.client, "GET", "/auth/me").status_code == 401, "ออกจากระบบแล้ว session ถูกลบ → /auth/me ได้ 401")
        self.call(self.client, "POST", "/auth/login", expect=204, json={"email": self.client.email, "password": self.client.password})
        self.check(self.call(self.client, "GET", "/auth/me").status_code == 200, "เข้าสู่ระบบด้วยอีเมล/รหัสผ่านอีกครั้งได้")

    # ---- static map of the contract ----------------------------------------

    def contract_map(self) -> None:
        self.out.raw()
        self.out.raw(self.out.paint("1", "━━ แผนที่ Smart Contract: ฟังก์ชัน/event ไหนถูกใช้โดยระบบจริง (วิเคราะห์จากโค้ดในโปรเจกต์)"))
        abi_functions = {item["name"] for item in self.abi if item["type"] == "function"}
        abi_events = {item["name"] for item in self.abi if item["type"] == "event"}
        service = ROOT / "src/services/blockchain/contractService.js"
        wired: set[str] = set()
        for path in list((ROOT / "src").rglob("*.js*")):
            if path == service or "services/blockchain" in path.as_posix() or path.suffix not in (".js", ".jsx"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"import\s+\*\s+as\s+(\w+)\s+from\s+['\"][^'\"]*blockchain/contractService['\"]", text):
                wired.update(name for name in abi_functions if re.search(rf"\b{match.group(1)}\.{name}\s*\(", text))
            for match in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"][^'\"]*blockchain/contractService['\"]", text):
                names = {part.split(" as ")[0].strip() for part in match.group(1).split(",")}
                wired.update(name for name in names if name in abi_functions)
        chain_py = (BACKEND / "app/escrow_chain.py").read_text(encoding="utf-8")
        listened = set(re.findall(r'Event\("(\w+)"', chain_py))
        self.out.raw(self.out.paint("2", "   ฟังก์ชันเขียน (ใครเรียก)          UI หน้าเว็บเรียกอยู่ไหม"))
        for name, who in CONTRACT_WRITES:
            if name not in abi_functions:
                continue
            state = self.out.paint("32", "✔ ผูกแล้ว") if name in wired else self.out.paint("33", "✘ ยังไม่มีปุ่ม/โค้ดเรียก")
            self.out.raw(f"   {name:<22} {who:<26} {state}")
        self.out.raw(self.out.paint("2", "   event ที่ contract ปล่อย            Backend (escrow_worker) อ่านอยู่ไหม"))
        for name in CONTRACT_EVENTS:
            if name not in abi_events:
                continue
            state = self.out.paint("32", "✔ ใช้อัปเดต DB") if name in listened else self.out.paint("33", "✘ ไม่ได้ฟัง")
            self.out.raw(f"   {name:<34} {state}")
        sol = (ROOT / "smart-contact/contracts/FreelinkEscrow.sol").read_text(encoding="utf-8")
        body = re.search(r"function releasePayment\b.*?(?=\n    function )", sol, re.S)
        needs_active = bool(body and "Status.Active" in body.group(0))
        if needs_active and "releasePayment" in wired and "acceptEscrow" not in wired:
            page = (ROOT / "src/pages/client/EscrowPayment.jsx").read_text(encoding="utf-8")
            gate = " หน้า EscrowPayment เปิดปุ่มปล่อยเงินเฉพาะเมื่อสถานะบนเชนเป็น active/submitted" \
                if re.search(r"\['active',\s*'submitted'\]", page) else ""
            note = ("contract.releasePayment() ต้องการสถานะบนเชน active/submitted ซึ่งเข้าได้ทางเดียวคือ acceptEscrow() โดย freelancer "
                    "แต่ UI ไม่มีที่เรียก acceptEscrow/submitWork → หลังฝากเงินสถานะบนเชนค้างที่ funded" + gate + " จึงยังปล่อยเงินผ่านหน้าเว็บครบวงจรไม่ได้ "
                    "(README ของ backend ระบุว่า “ยืนยันรับงาน ส่งงาน และ v3 เป็นงานถัดไป”)")
            self.out.mark(None, note, indent=3)
            self.notes.append(note)

    # ---- orchestration -------------------------------------------------------

    def run(self) -> None:
        stages = [self.step_topology, self.step_frontend_contract, self.step_accounts, self.step_job, self.step_proposal,
                  self.step_hire, self.step_wallets, self.step_prepare, self.step_crosscheck, self.step_consent]
        try:
            for stage in stages:
                stage()
            if self.step_deposit():
                self.step_work()
                self.step_approve()
            else:
                for step in (self.WORK_STEP, self.APPROVE_STEP):
                    self.skip(step, "ต้องมีเงินฝากใน escrow ก่อน (ใช้ --simulate-funding)")
            self.step_social()
            self.step_guards()
        except Abort as error:
            self.out.mark(False, f"หยุดเดินต่อ: {error}", indent=2)
            if self.cur:
                self.cur.failures += 1 if not self.cur.failures else 0
        except KeyError as error:
            self.out.mark(False, f"response ไม่มี field {error} ที่คาดไว้ — shape ของ API เปลี่ยนไปหรือเปล่า", indent=2)
            if self.cur:
                self.cur.failures += 1
        self.contract_map()
        self.summary()

    def summary(self) -> None:
        self.out.raw()
        self.out.raw(self.out.paint("1", "━━ สรุป: ขั้นตอน · ชั้นที่แตะ · เกี่ยวกับ Smart Contract ไหม · ผล"))
        for step in self.steps:
            result = ("✘ ไม่ผ่าน" if step.failures else "⚠ มีข้อสังเกต" if step.warnings else "⏸ " + step.skipped if step.skipped else "✔ ผ่าน")
            self.out.raw(f"  {step.no:>2}. {step.title}")
            self.out.raw(f"      ชั้น: {step.layers}")
            self.out.raw(f"      Contract: {self.out.paint(Out.CONTRACT[step.contract_kind], step.contract_text)}   →  {result}")
        if self.notes:
            self.out.raw()
            self.out.raw(self.out.paint("33", "ข้อสังเกตที่สคริปต์พบ (ไม่ใช่บั๊กของสคริปต์):"))
            for item in dict.fromkeys(self.notes):
                self.out.raw(f"  • {item}")
        if self.steps and any(s.no == "2" for s in self.steps) and self.client.user_id:
            self.out.raw()
            self.out.raw(self.out.paint("1", "ดูข้อมูลชุดนี้ในหน้าเว็บ: เปิด " + self.origin + "/login แล้วเข้าสู่ระบบด้วย"))
            for actor in (self.client, self.freelancer):
                self.out.raw(f"  {actor.role:<10} {actor.email}   รหัสผ่าน {actor.password}")
            self.out.raw(self.out.paint("2", "ลบข้อมูลทดสอบทั้งหมด:  backend\\.venv\\Scripts\\python.exe scripts\\flow_trace.py --cleanup"))
        failed = sum(step.failures for step in self.steps)
        self.out.raw()
        self.out.raw(self.out.paint("1;31" if failed else "1;32", f"ผล: {'พบ ' + str(failed) + ' รายการที่ไม่ผ่าน (✘)' if failed else 'ไม่มีรายการที่ล้มเหลว (✘)'}"))
        self.failed = failed

    def write_report(self, path: Path) -> None:
        lines = ["# Freelink flow trace", "", f"สร้างเมื่อ {datetime.now():%Y-%m-%d %H:%M:%S} · API {self.api} · chain {self.chain_id} · contract `{self.contract}`", "",
                 "| # | ขั้นตอน | ชั้นที่เกี่ยว | Smart Contract |", "|---|---|---|---|"]
        lines += [f"| {s.no} | {s.title} | {s.layers} | {s.contract_text} |" for s in self.steps]
        lines += ["", "## บันทึกเต็ม", "", "```text", *self.out.buffer, "```", ""]
        path.write_text("\n".join(lines), encoding="utf-8")


def cleanup(args: argparse.Namespace, out: Out) -> int:
    env = load_env(BACKEND / ".env")
    if not psycopg or not env.get("DATABASE_URL"):
        out.raw("ต้องมี psycopg และ DATABASE_URL ใน backend/.env")
        return 1
    db = Db(env["DATABASE_URL"])
    users = db.rows("SELECT id, email FROM users WHERE email LIKE %s", (TEST_EMAIL_LIKE,))
    if not users:
        out.raw("ไม่พบข้อมูลทดสอบ (flowtest-*@example.net)")
        return 0
    out.raw(f"จะลบข้อมูลของ {len(users)} บัญชีทดสอบ และงาน/ข้อเสนอ/โปรเจกต์/ข้อความ/ข้อตกลง Escrow ที่เกี่ยวข้อง:")
    for user in users:
        out.raw(f"  - {user['email']}")
    ids = [user["id"] for user in users]
    profiles = [row["id"] for row in db.rows("SELECT id FROM profiles WHERE user_id = ANY(%s)", (ids,))]
    projects = "SELECT id FROM projects WHERE client_id = ANY(%(p)s) OR freelancer_id = ANY(%(p)s)"
    statements = [
        ("messages", f"DELETE FROM messages WHERE thread_id IN (SELECT id FROM message_threads WHERE project_id IN ({projects}))"),
        ("message_threads", f"DELETE FROM message_threads WHERE project_id IN ({projects})"),
        ("work_attachments", f"DELETE FROM work_attachments WHERE submission_id IN (SELECT id FROM work_submissions WHERE project_id IN ({projects}))"),
        ("work_submissions", f"DELETE FROM work_submissions WHERE project_id IN ({projects})"),
        ("escrow_transactions", f"DELETE FROM escrow_transactions WHERE agreement_id IN (SELECT id FROM escrow_agreements WHERE project_id IN ({projects}))"),
        ("escrow_agreements", f"DELETE FROM escrow_agreements WHERE project_id IN ({projects})"),
        ("projects", f"DELETE FROM projects WHERE id IN ({projects})"),
        ("proposals", "DELETE FROM proposals WHERE freelancer_id = ANY(%(p)s) OR job_id IN (SELECT id FROM jobs WHERE client_id = ANY(%(p)s))"),
        ("jobs", "DELETE FROM jobs WHERE client_id = ANY(%(p)s)"),
        ("profiles", "DELETE FROM profiles WHERE id = ANY(%(p)s)"),
        ("users", "DELETE FROM users WHERE id = ANY(%(u)s)"),  # cascade: wallet_links, login_sessions, credentials, notifications
    ]
    with db.conn.transaction():
        for table, sql in statements:
            with db.conn.cursor() as cur:
                cur.execute(sql, {"p": profiles, "u": ids})
                out.raw(f"  ลบ {table:<20} {cur.rowcount} แถว")
    out.raw(out.paint("1;32", "เรียบร้อย"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", help="Base URL ของ backend (ค่าเริ่มต้น: VITE_API_BASE_URL ใน .env)")
    parser.add_argument("--simulate-funding", action="store_true", help="จำลองสถานะ funded ใน DB (ไม่มีธุรกรรมจริง) เพื่อเดินต่อถึงส่งงาน/อนุมัติ")
    parser.add_argument("--cleanup", action="store_true", help="ลบข้อมูลทดสอบ flowtest-*@example.net แล้วจบ")
    parser.add_argument("--skip-frontend", action="store_true", help="ไม่รันโค้ด frontend ผ่าน Vite/Node")
    parser.add_argument("--skip-chain", action="store_true", help="สคริปต์ไม่ถาม RPC เอง (backend ยังถามตามปกติตอน prepare)")
    parser.add_argument("--report", type=Path, help="เขียนผลเป็นไฟล์ Markdown")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="แสดงรายการ endpoint ของ frontend ทั้งหมด")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if os.name == "nt":
        os.system("")  # เปิด ANSI escape ใน console ของ Windows
    out = Out(color=sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ)

    if args.cleanup:
        return cleanup(args, out)
    flow = Flow(args, out)
    out.raw(out.paint("1", f"Freelink flow trace · run {flow.run_id} · API {flow.api}"))
    try:
        flow.run()
    except KeyboardInterrupt:
        out.raw("\nยกเลิกโดยผู้ใช้")
        return 130
    if args.report:
        flow.write_report(args.report)
        out.raw(f"บันทึกรายงานที่ {args.report}")
    return 1 if getattr(flow, "failed", 0) else 0


if __name__ == "__main__":
    sys.exit(main())

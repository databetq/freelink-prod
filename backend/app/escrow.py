import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from unicodedata import normalize
from uuid import UUID

import httpx
from eth_abi.exceptions import DecodingError
from fastapi import APIRouter, Depends, Response
from pydantic import Field, PositiveInt, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentIdentity, Db, trusted_origin
from app.config import get_settings
from app.errors import api_error
from app.escrow_chain import EVENTS, FUNDED, REFUNDED, RELEASED, RESOLVED, EscrowChain, escrow_id, hex_hash
from app.marketplace import close_paid_job, get_job, plan_released, require_owner
from app.models import EscrowAgreement, EscrowTransaction, Profile, Project, Proposal, WalletLink, WorkSubmission
from app.schemas import ApiModel, PositiveMoney

router = APIRouter(prefix="/projects/{project_id}/escrow", tags=["escrow"])
write = [Depends(trusted_origin)]
TOS_VERSION = "freelink-demo-escrow-v2-1"
TOS = (
    "ยอดชำระถูกล็อกเป็น ETH ตามข้อตกลง เงินบาทใช้แสดงเป็นค่าอ้างอิง "
    "ข้อมูลธุรกรรมบน Sepolia เป็นข้อมูลสาธารณะและลบไม่ได้ "
    "ทั้งสองฝ่ายตรวจงานตามรายการที่ตกลงกันและใช้ช่องทางข้อพิพาทของสัญญาเมื่อจำเป็น "
    "สิทธิ์ในงานโอนเมื่อชำระค่าจ้างครบตามข้อตกลง และห้ามเผยแพร่งานที่ระบุว่าเป็นความลับ"
)
MIN_DEADLINE_DAYS = 7
SECONDS_PER_DAY = 86400
Hash = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{64}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class MilestoneInput(ApiModel):
    title: ShortText
    amount_thb: PositiveMoney
    checklist: list[ShortText] = Field(min_length=1, max_length=30)
    deadline: PositiveInt | None = Field(default=None, le=253402300799)  # End of year 9999 UTC.


class PrepareRequest(ApiModel):
    milestone_number: PositiveInt = 1
    deadline: PositiveInt | None = None
    milestones: list[MilestoneInput] | None = Field(default=None, min_length=1, max_length=12)
    confidential: bool = True


class TxView(ApiModel):
    tx_hash: str
    status: str
    event: str | None
    block_number: int | None
    fee_wei: str | None
    error: str | None


class AgreementView(ApiModel):
    id: UUID
    milestone_number: int
    attempt_number: int
    terms_json: str
    terms_hash: str
    expected_escrow_id: str
    escrow_id: str | None
    status: str
    client_consented_at: datetime | None
    transactions: list[TxView]


class EscrowView(ApiModel):
    agreements: list[AgreementView]
    approved_agreement_ids: list[UUID]
    deliverables: list[str]
    proposed_delivery_days: int
    min_deadline_days: int = MIN_DEADLINE_DAYS
    tos_version: str = TOS_VERSION
    tos_text: str = TOS


class ReleaseProgress(ApiModel):
    status: Literal["awaiting_release", "checking_transaction", "awaiting_finality", "syncing", "released"]
    tx_hash: str | None = None
    tx_block: int | None = None
    finalized_block: int | None = None


class ConsentRequest(ApiModel):
    agreement_id: UUID
    terms_hash: Hash
    tos_version: str
    accepted: Literal[True]


class TransactionRequest(ApiModel):
    agreement_id: UUID
    tx_hash: Hash


def project_access(db: Session, project_id: UUID, identity: CurrentIdentity, *, lock: bool = False) -> Project:
    project = db.get(Project, project_id, with_for_update=lock or None)
    if project is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "ไม่พบโปรเจกต์")
    if identity.profile.id not in (project.client_id, project.freelancer_id):
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์ดูโปรเจกต์")
    return project


def project_agreements(db: Session, project_id: UUID) -> list[EscrowAgreement]:
    return list(db.scalars(select(EscrowAgreement).where(EscrowAgreement.project_id == project_id)
                           .order_by(EscrowAgreement.milestone_number, EscrowAgreement.attempt_number)))


def agreement_view(db: Session, agreement: EscrowAgreement) -> AgreementView:
    transactions = db.scalars(select(EscrowTransaction).where(EscrowTransaction.agreement_id == agreement.id)
                              .order_by(EscrowTransaction.created_at, EscrowTransaction.id))
    confirmed = agreement.status in ("funded", "released", "refunded", "resolved")
    return AgreementView(
        id=agreement.id, milestone_number=agreement.milestone_number, attempt_number=agreement.attempt_number,
        terms_json=agreement.terms_json, terms_hash=agreement.terms_hash, status=agreement.status,
        expected_escrow_id=agreement.expected_escrow_id,
        escrow_id=agreement.expected_escrow_id if confirmed else None,
        client_consented_at=agreement.client_consented_at,
        transactions=[TxView.model_validate(tx) for tx in transactions],
    )


def get_agreement(db: Session, project_id: UUID, agreement_id: UUID, *, lock: bool = False) -> EscrowAgreement:
    agreement = db.get(EscrowAgreement, agreement_id, with_for_update=lock or None, populate_existing=lock)
    if agreement is None or agreement.project_id != project_id:
        raise api_error(404, "ESCROW_AGREEMENT_NOT_FOUND", "ไม่พบข้อตกลงการฝากเงิน")
    return agreement


@router.get("", response_model=EscrowView)
def read_escrow(project_id: UUID, db: Db, identity: CurrentIdentity):
    project = project_access(db, project_id, identity)
    return EscrowView(
        agreements=[agreement_view(db, item) for item in project_agreements(db, project_id)],
        approved_agreement_ids=list(db.scalars(select(WorkSubmission.agreement_id).where(
            WorkSubmission.project_id == project_id, WorkSubmission.status == "approved",
        ).distinct())),
        deliverables=get_job(db, project.job_id).deliverables,
        proposed_delivery_days=db.get(Proposal, project.proposal_id).delivery_days,
    )


def build_milestones(payload: PrepareRequest, project: Project, deliverables: list[str]) -> list[dict]:
    items = payload.milestones
    if items is None:
        return [{"title": project.title, "amountThb": format(project.budget, ".2f"),
                 "checklist": deliverables or ["ตรวจงานตามขอบเขตที่ระบุในประกาศ"]}]
    amounts = [item.amount_thb for item in items]
    if sum(amounts) != project.budget:
        raise api_error(422, "ESCROW_MILESTONE_TOTAL", "ยอดทุกงวดรวมกันต้องเท่ากับค่าจ้างที่ตกลง")
    if len(items) > 1 and (amounts[0] * 10 > project.budget * 3 or amounts[-1] * 10 < project.budget * 3):
        raise api_error(422, "ESCROW_MILESTONE_SHARE", "งวดแรกต้องไม่เกิน 30% และงวดสุดท้ายต้องไม่น้อยกว่า 30%")
    deadlines = [item.deadline for item in items]
    if len(items) > 1:
        if None in deadlines:
            raise api_error(422, "ESCROW_DEADLINE_REQUIRED", "กรุณาระบุวันและเวลาส่งงานของทุกงวด")
        if any(previous >= following for previous, following in zip(deadlines, deadlines[1:])):
            raise api_error(422, "ESCROW_DEADLINE_ORDER", "กำหนดส่งของแต่ละงวดต้องอยู่หลังงวดก่อนหน้า")
    if deadlines[0] is not None and payload.deadline not in (None, deadlines[0]):
        raise api_error(422, "ESCROW_DEADLINE_MISMATCH", "กำหนดส่งของงวดแรกไม่ตรงกับแผนแบ่งจ่าย")
    milestones = []
    for item in items:
        milestone = {"title": item.title, "amountThb": format(item.amount_thb, ".2f"), "checklist": item.checklist}
        if item.deadline is not None:
            milestone["deadline"] = item.deadline
        milestones.append(milestone)
    return milestones


@router.post("/prepare", response_model=AgreementView, dependencies=write)
def prepare(project_id: UUID, payload: PrepareRequest, db: Db, identity: CurrentIdentity):
    project = project_access(db, project_id, identity, lock=True)
    require_owner(identity, project.client_id)
    items = project_agreements(db, project.id)
    latest = {item.milestone_number: item for item in items}
    number = payload.milestone_number
    current = latest.get(number)
    if current is not None and current.status not in ("refunded", "expired"):
        return agreement_view(db, current)
    if project.status in ("cancelled", "completed"):
        raise api_error(409, "ESCROW_PROJECT_CLOSED", "โปรเจกต์นี้ปิดแล้ว")
    if number > 1 and (number - 1 not in latest or latest[number - 1].status != "released"):
        raise api_error(409, "ESCROW_MILESTONE_LOCKED", "ต้องยืนยันการจ่ายงวดก่อนหน้าก่อนเตรียมงวดถัดไป")
    settings = get_settings()
    if not settings.escrow_contract_address or settings.escrow_thb_per_eth is None:
        raise api_error(503, "ESCROW_CONFIG_REQUIRED", "ยังไม่ได้ตั้งค่า Contract Address หรืออัตราบาทต่อ ETH ฝั่งเซิร์ฟเวอร์")
    contract = settings.escrow_contract_address.lower()
    job = get_job(db, project.job_id)
    original = json.loads(items[0].terms_json) if items else None
    if original and payload.milestones is not None:
        raise api_error(409, "ESCROW_PLAN_LOCKED", "แผนงวดนี้ถูกบันทึกไว้แล้ว")
    milestones = original["milestones"] if original else build_milestones(payload, project, job.deliverables)
    if number > len(milestones):
        raise api_error(422, "ESCROW_MILESTONE_UNKNOWN", "ไม่พบงวดนี้ในข้อตกลง")
    selected = milestones[number - 1]
    deadline = payload.deadline
    if deadline is None and current is None:
        deadline = selected.get("deadline")
    if deadline is None and items:
        raise api_error(422, "ESCROW_DEADLINE_REQUIRED", "กรุณาระบุวันและเวลาส่งงานของงวดนี้")
    parties = db.execute(select(Profile.id, WalletLink).join(WalletLink, Profile.user_id == WalletLink.user_id)
                         .where(Profile.id.in_((project.client_id, project.freelancer_id)))).all()
    links = {profile_id: link for profile_id, link in parties}
    for profile_id, role in ((project.client_id, "คนจ้าง"), (project.freelancer_id, "คนรับงาน")):
        link = links.get(profile_id)
        if link is None or link.chain_id != settings.escrow_chain_id:
            raise api_error(409, "ESCROW_WALLETS_REQUIRED", f"{role}ต้องยืนยัน Wallet บนเครือข่าย Escrow ก่อน")
    client, freelancer = links[project.client_id].address, links[project.freelancer_id].address
    attempt = current.attempt_number + 1 if current else 1
    key = hex_hash(f"{project.id}:{number}:{attempt}".encode())
    expected = escrow_id(client, key)
    rate = settings.escrow_thb_per_eth
    satang = int(Decimal(selected["amountThb"]) * 100)
    amount_wei = satang * 10**18 // int(rate * 100)
    if amount_wei <= 0:
        raise api_error(422, "ESCROW_AMOUNT_TOO_SMALL", "ยอดของงวดนี้แปลงเป็น ETH แล้วต่ำเกินไป")
    with httpx.Client(timeout=5) as http:
        chain = EscrowChain(http, settings.escrow_chain_id)
        latest_block = chain.block("latest")
        timestamp = int(latest_block["timestamp"], 16)
        arbiter, revisions, max_duration = chain.policy(contract)
        if deadline is None:
            proposed_days = db.get(Proposal, project.proposal_id).delivery_days
            deadline = timestamp + max(proposed_days, MIN_DEADLINE_DAYS) * SECONDS_PER_DAY
        if not timestamp + MIN_DEADLINE_DAYS * SECONDS_PER_DAY <= deadline <= timestamp + max_duration:
            if original and payload.deadline is None:
                raise api_error(422, "ESCROW_PLANNED_DEADLINE", "กำหนดส่งตามแผนใช้กับรอบนี้ไม่ได้ กรุณาเลือกวันและเวลาส่งงานใหม่")
            raise api_error(422, "ESCROW_DEADLINE",
                            f"กำหนดส่งต้องห่างอย่างน้อย {MIN_DEADLINE_DAYS} วัน และไม่เกินระยะเวลาที่สัญญารองรับ")
        if arbiter in (client, freelancer):
            raise api_error(409, "ESCROW_ARBITER_CONFLICT", "Wallet ของคู่สัญญาต้องต่างจาก Wallet ผู้ตัดสิน")
        if not items and chain.is_occupied(contract, escrow_id(client, hex_hash(str(project.id).encode()))):
            raise api_error(409, "ESCROW_LEGACY_EXISTS", "มีเงินฝากจากขั้นตอนเดิมสำหรับ Wallet นี้แล้ว กรุณาตรวจรายการเดิมก่อน")
        if chain.is_occupied(contract, expected):
            raise api_error(409, "ESCROW_KEY_OCCUPIED", "มีธุรกรรมใช้รหัสงวดและรอบนี้บนเครือข่ายแล้ว")
    terms = {
        "v": 1, "contractVersion": "v2", "chainId": settings.escrow_chain_id, "contract": contract,
        "projectId": str(project.id), "jobId": str(project.job_id), "projectKey": key,
        "milestoneNumber": number, "attemptNumber": attempt, "milestones": milestones,
        "client": client, "freelancer": freelancer, "arbiterAtPreparation": arbiter,
        "amountThb": selected["amountThb"], "thbPerEth": format(rate, ".2f"), "amountWei": str(amount_wei),
        "deadline": deadline, "scope": original["scope"] if original else job.description,
        "deliverables": original["deliverables"] if original else job.deliverables,
        "checklist": selected["checklist"], "revisionPolicy": {"maxRevisions": revisions},
        "ip": "transfer_after_full_payment", "confidential": original["confidential"] if original else payload.confidential,
        "tosVersion": TOS_VERSION,
    }
    canonical = normalize("NFC", json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    agreement = EscrowAgreement(
        project_id=project.id, milestone_number=number, attempt_number=attempt, chain_id=settings.escrow_chain_id,
        contract_address=contract, expected_escrow_id=expected, terms_json=canonical,
        terms_hash=hex_hash(canonical.encode()), next_scan_block=int(latest_block["number"], 16),
    )
    db.add(agreement)
    db.commit()
    return agreement_view(db, agreement)


@router.post("/consent", response_model=AgreementView, dependencies=write)
def accept_terms(project_id: UUID, payload: ConsentRequest, db: Db, identity: CurrentIdentity):
    project = project_access(db, project_id, identity)
    require_owner(identity, project.client_id)
    agreement = get_agreement(db, project_id, payload.agreement_id, lock=True)
    terms = json.loads(agreement.terms_json)
    if payload.terms_hash.lower() != agreement.terms_hash or payload.tos_version != terms["tosVersion"]:
        raise api_error(409, "ESCROW_TERMS_CHANGED", "ข้อตกลงที่ยอมรับไม่ตรงกับฉบับที่บันทึกไว้")
    if agreement.status != "prepared" or int(datetime.now(timezone.utc).timestamp()) >= terms["deadline"]:
        raise api_error(409, "ESCROW_NOT_PAYABLE", "ข้อตกลงนี้ไม่สามารถฝากได้แล้ว")
    if agreement.client_consented_at is None:
        agreement.client_consented_at = datetime.now(timezone.utc)
        db.commit()
    return agreement_view(db, agreement)


def receipt_event(agreement: EscrowAgreement, receipt: dict) -> tuple | None:
    terms = json.loads(agreement.terms_json)
    for log in receipt["logs"]:
        topics = log["topics"]
        if (log.get("removed") or log["address"].lower() != agreement.contract_address or len(topics) < 2
                or topics[1].lower() != agreement.expected_escrow_id):
            continue
        event = EVENTS.get(topics[0].lower())
        if event is None:
            continue
        _, *values = event.decode(log)
        if event == FUNDED:
            key, client, freelancer, amount, fee, deadline, terms_hash = values
            expected = (terms["projectKey"], terms["client"], terms["freelancer"], int(terms["amountWei"]),
                        terms["deadline"], agreement.terms_hash)
            if ("0x" + key.hex(), client, freelancer, amount, deadline, "0x" + terms_hash.hex()) == expected:
                return event, log, amount, fee
        elif event == RELEASED:
            freelancer, amount, fee = values
            if freelancer == terms["freelancer"] and amount == int(terms["amountWei"]):
                return event, log, amount, fee
        elif event == REFUNDED:
            client, amount = values
            if client == terms["client"]:
                return event, log, amount, 0
        elif event == RESOLVED:
            _, amount, _, fee, _ = values
            return event, log, amount, fee
    return None


@router.get("/release-progress", response_model=ReleaseProgress)
def read_release_progress(project_id: UUID, db: Db, identity: CurrentIdentity):
    project_access(db, project_id, identity)
    latest = {item.milestone_number: item for item in project_agreements(db, project_id)}
    if plan_released(latest):
        return ReleaseProgress(status="released")
    agreement = next((item for item in latest.values() if item.status != "released"), None)
    if agreement is None or agreement.status != "funded":
        return ReleaseProgress(status="awaiting_release")
    pending = db.scalars(select(EscrowTransaction.tx_hash).where(
        EscrowTransaction.agreement_id == agreement.id, EscrowTransaction.status == "pending",
    ).order_by(EscrowTransaction.created_at.desc()).limit(5)).all()
    if not pending:
        return ReleaseProgress(status="awaiting_release")

    with httpx.Client(timeout=5) as http:
        chain = EscrowChain(http, agreement.chain_id)
        finalized = int(chain.block()["number"], 16)
        for tx_hash in pending:
            receipt = chain.call("eth_getTransactionReceipt", tx_hash)
            if receipt and int(receipt["status"], 16) == 1:
                matched = receipt_event(agreement, receipt)
                if matched and matched[0] == RELEASED:
                    block = int(receipt["blockNumber"], 16)
                    return ReleaseProgress(status="awaiting_finality" if block > finalized else "syncing",
                                           tx_hash=tx_hash, tx_block=block, finalized_block=finalized)
    return ReleaseProgress(status="checking_transaction", finalized_block=finalized)


def get_transaction(db: Session, agreement: EscrowAgreement, tx_hash: str) -> EscrowTransaction:
    tx = db.scalar(select(EscrowTransaction).where(EscrowTransaction.agreement_id == agreement.id,
                                                   EscrowTransaction.tx_hash == tx_hash))
    if tx is None:
        tx = EscrowTransaction(agreement_id=agreement.id, tx_hash=tx_hash, status="pending")
        db.add(tx)
    return tx


def reconcile(db: Session, chain: EscrowChain, agreement: EscrowAgreement, tx: EscrowTransaction, finalized: dict) -> None:
    if tx.status != "pending":
        return
    receipt = chain.call("eth_getTransactionReceipt", tx.tx_hash)
    if receipt is None:
        return
    try:
        block_number = int(receipt["blockNumber"], 16)
        if block_number > int(finalized["number"], 16):
            return
        block = chain.block(hex(block_number))
        if (receipt["transactionHash"].lower() != tx.tx_hash
                or block["hash"].lower() != receipt["blockHash"].lower()):
            return
        if int(receipt["status"], 16) != 1:
            tx.status, tx.error = "rejected", "ESCROW_TX_REVERTED"
            return
        matched = receipt_event(agreement, receipt)
        if matched is None:
            tx.status, tx.error = "rejected", "ESCROW_EVENT_MISMATCH"
            return
        event, log, amount, fee = matched
        if event != FUNDED and agreement.status == "prepared":
            return  # Wait for the funding event to be processed before its settlement.
        if event == FUNDED and agreement.client_consented_at is None:
            tx.status, tx.error = "rejected", "ESCROW_CONSENT_REQUIRED"
            return
        tx.event = event.name
        tx.status = "confirmed"
        tx.log_index = int(log["logIndex"], 16)
        tx.block_number, tx.block_hash = block_number, receipt["blockHash"].lower()
        tx.confirmed_at = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc)
        tx.amount_wei, tx.fee_wei = str(amount), str(fee)
        if agreement.status in ("prepared", "funded"):
            agreement.status = {FUNDED: "funded", RELEASED: "released", REFUNDED: "refunded", RESOLVED: "resolved"}[event]
        if event == RELEASED:
            close_paid_job(db, agreement.project_id)
    except (KeyError, TypeError, ValueError, DecodingError):
        raise api_error(503, "ESCROW_RPC_UNAVAILABLE", "ข้อมูลธุรกรรมจาก RPC ไม่ครบ กรุณาลองใหม่") from None


@router.post("/transactions", response_model=TxView, dependencies=write)
def submit_transaction(project_id: UUID, payload: TransactionRequest, response: Response,
                       db: Db, identity: CurrentIdentity):
    project_access(db, project_id, identity)
    agreement = get_agreement(db, project_id, payload.agreement_id, lock=True)
    tx_hash = payload.tx_hash.lower()
    tx = get_transaction(db, agreement, tx_hash)
    if tx.status == "pending":
        db.commit()  # Keep the submitted hash even if the RPC request below fails.
        agreement = get_agreement(db, project_id, payload.agreement_id, lock=True)
        tx = get_transaction(db, agreement, tx_hash)
        with httpx.Client(timeout=5) as http:
            chain = EscrowChain(http, agreement.chain_id)
            reconcile(db, chain, agreement, tx, chain.block())
        db.commit()
    response.status_code = 202 if tx.status == "pending" else 200
    return tx

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID, uuid4

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys.exceptions import BadSignature
from fastapi import APIRouter, Depends
from pydantic import PositiveInt, StringConstraints
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.auth import CurrentIdentity, Db, trusted_origin
from app.config import get_settings
from app.errors import api_error
from app.models import WalletChallenge, WalletLink
from app.schemas import ApiModel

router = APIRouter(prefix="/wallet", tags=["wallet"])
CHALLENGE_LIFETIME = timedelta(minutes=5)
Address = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{40}$")]
Signature = Annotated[str, StringConstraints(pattern=r"^0x[0-9a-fA-F]{130}$")]


class WalletChallengeRequest(ApiModel):
    address: Address
    chain_id: PositiveInt


class WalletChallengeResponse(ApiModel):
    challenge_id: UUID
    message: str
    expires_at: datetime


class WalletVerificationRequest(ApiModel):
    challenge_id: UUID
    signature: Signature


class WalletLinkResponse(ApiModel):
    address: str
    chain_id: int
    verified_at: datetime


def wallet_user(identity: CurrentIdentity) -> UUID:
    if identity.user.role not in ("client", "freelancer"):
        raise api_error(403, "WALLET_ROLE_NOT_ALLOWED", "เมนูนี้สำหรับบัญชีคนจ้างและคนรับงาน")
    return identity.user.id


WalletUser = Annotated[UUID, Depends(wallet_user)]


@router.get("/link", response_model=WalletLinkResponse | None)
def read_link(db: Db, user_id: WalletUser):
    return db.get(WalletLink, user_id)


@router.post(
    "/challenges", response_model=WalletChallengeResponse, status_code=201,
    dependencies=[Depends(trusted_origin)],
)
def create_challenge(payload: WalletChallengeRequest, db: Db, user_id: WalletUser):
    settings = get_settings()
    if payload.chain_id != settings.escrow_chain_id:
        raise api_error(422, "WALLET_WRONG_CHAIN", "โปรดเลือกเครือข่ายที่ใช้กับ Freelink Escrow")
    address = payload.address.lower()
    if int(address, 16) == 0:
        raise api_error(422, "WALLET_INVALID_ADDRESS", "ไม่สามารถใช้ address ศูนย์ได้")
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + CHALLENGE_LIFETIME
    nonce = uuid4()
    message = "\n".join((
        "Freelink: Link a wallet to your account",
        "",
        "This signature only verifies your wallet address. It does not authorize a transaction.",
        "",
        f"Origin: {settings.frontend_origin}",
        f"Account: {user_id}",
        f"Address: {address}",
        f"Chain ID: {payload.chain_id}",
        f"Nonce: {nonce}",
        f"Issued At: {issued_at.isoformat()}",
        f"Expires At: {expires_at.isoformat()}",
    ))
    challenge_data = {
        "nonce": nonce, "address": address, "chain_id": payload.chain_id,
        "message": message, "expires_at": expires_at,
    }
    db.execute(
        insert(WalletChallenge).values(user_id=user_id, **challenge_data)
        .on_conflict_do_update(index_elements=[WalletChallenge.user_id], set_=challenge_data)
    )
    db.commit()
    return WalletChallengeResponse(challenge_id=nonce, message=message, expires_at=expires_at)


@router.post("/verifications", response_model=WalletLinkResponse, dependencies=[Depends(trusted_origin)])
def verify_wallet(payload: WalletVerificationRequest, db: Db, user_id: WalletUser):
    challenge = db.get(WalletChallenge, user_id, with_for_update=True)
    now = datetime.now(timezone.utc)
    if challenge is None or challenge.nonce != payload.challenge_id or challenge.expires_at <= now:
        raise api_error(409, "WALLET_CHALLENGE_INVALID", "ข้อความยืนยันนี้ใช้ไม่ได้ กรุณาขอข้อความใหม่")
    if challenge.chain_id != get_settings().escrow_chain_id:
        raise api_error(409, "WALLET_WRONG_CHAIN", "เครือข่ายเปลี่ยนไป กรุณาขอข้อความยืนยันใหม่")
    try:
        address = Account.recover_message(
            encode_defunct(text=challenge.message), signature=payload.signature,
        ).lower()
    except (ValueError, BadSignature):
        address = None
    if address != challenge.address:
        raise api_error(422, "WALLET_SIGNATURE_INVALID", "ลายเซ็นไม่ตรงกับ Wallet ที่ต้องการยืนยัน")

    values = {"address": address, "chain_id": challenge.chain_id, "verified_at": now}
    try:
        db.execute(
            insert(WalletLink).values(user_id=user_id, **values)
            .on_conflict_do_update(index_elements=[WalletLink.user_id], set_=values)
        )
        db.delete(challenge)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_wallet_links_address":
            raise api_error(409, "WALLET_ALREADY_LINKED", "Wallet นี้ผูกกับบัญชีอื่นอยู่แล้ว") from exc
        raise
    return WalletLinkResponse(**values)

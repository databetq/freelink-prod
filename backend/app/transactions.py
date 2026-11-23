from datetime import datetime
from decimal import Decimal
from json import loads
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.auth import CurrentIdentity, Db
from app.errors import api_error
from app.models import EscrowAgreement, EscrowTransaction, Project
from app.schemas import ApiModel

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionResponse(ApiModel):
    id: UUID
    type: str
    status: str
    amount: float
    note: str
    tx_hash: str | None
    project_id: UUID | None
    created_at: datetime


def transaction_query(profile_id: UUID):
    return (select(EscrowTransaction, EscrowAgreement, Project)
            .join(EscrowAgreement, EscrowTransaction.agreement_id == EscrowAgreement.id)
            .join(Project, EscrowAgreement.project_id == Project.id)
            .where(EscrowTransaction.status == "confirmed",
                   or_(Project.client_id == profile_id, Project.freelancer_id == profile_id)))


def transaction_view(tx: EscrowTransaction, agreement: EscrowAgreement, project: Project,
                     profile_id: UUID) -> TransactionResponse | None:
    is_client = project.client_id == profile_id
    amount = int(tx.amount_wei)
    if tx.event == "EscrowFunded" and is_client:
        kind = "escrow_deposit"
        amount += int(tx.fee_wei)
    elif tx.event == "PaymentReleased":
        kind = "release" if is_client else "earning"
    elif tx.event == "EscrowRefunded" and is_client:
        kind = "refund"
    else:
        return None
    rate = Decimal(loads(agreement.terms_json)["thbPerEth"])
    return TransactionResponse(
        id=tx.id, type=kind, status="confirmed", amount=float(round(amount * rate / 10**18, 2)),
        note=f"{project.title} · งวด {agreement.milestone_number}", tx_hash=tx.tx_hash,
        project_id=project.id, created_at=tx.confirmed_at,
    )


@router.get("", response_model=list[TransactionResponse])
def list_transactions(db: Db, identity: CurrentIdentity):
    profile_id = identity.profile.id
    rows = db.execute(transaction_query(profile_id)
                      .order_by(EscrowTransaction.block_number.desc(), EscrowTransaction.log_index.desc()))
    return [view for row in rows if (view := transaction_view(*row, profile_id=profile_id)) is not None]


@router.get("/{transaction_id}", response_model=TransactionResponse)
def read_transaction(transaction_id: UUID, db: Db, identity: CurrentIdentity):
    profile_id = identity.profile.id
    row = db.execute(transaction_query(profile_id).where(EscrowTransaction.id == transaction_id)).one_or_none()
    view = transaction_view(*row, profile_id=profile_id) if row else None
    if view is None:
        raise api_error(404, "TRANSACTION_NOT_FOUND", "ไม่พบธุรกรรม")
    return view

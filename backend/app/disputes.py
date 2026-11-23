import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import or_, select

from app.auth import AdminIdentity, Db
from app.marketplace import submission_history
from app.models import EscrowAgreement, EscrowTransaction, Project
from app.profiles import client_cards, freelancer_cards
from app.schemas import ApiModel, WorkSubmissionResponse

router = APIRouter(prefix="/admin/disputes", tags=["admin"])
logger = logging.getLogger("uvicorn.error")


class DisputeView(ApiModel):
    agreement_id: UUID
    project_id: UUID
    project_title: str
    client_name: str
    freelancer_name: str
    milestone_number: int
    attempt_number: int
    escrow_id: str
    terms_json: str
    terms_hash: str
    status: str
    opened_at: datetime | None
    submissions: list[WorkSubmissionResponse]


@router.get("", response_model=list[DisputeView])
def list_disputes(request: Request, response: Response, db: Db, admin: AdminIdentity):
    response.headers["Cache-Control"] = "private, no-store"
    opened_event = select(EscrowTransaction.id).where(
        EscrowTransaction.agreement_id == EscrowAgreement.id,
        EscrowTransaction.event == "DisputeOpened",
    ).exists()
    rows = db.execute(
        select(EscrowAgreement, Project).join(Project, Project.id == EscrowAgreement.project_id).where(or_(
            opened_event,
            EscrowAgreement.status == "resolved",
        )).order_by(EscrowAgreement.status, EscrowAgreement.created_at.desc())
    ).all()
    projects = [project for _, project in rows]
    clients = client_cards(db, {project.client_id for project in projects})
    freelancers = freelancer_cards(db, {project.freelancer_id for project in projects})
    history = submission_history(db, [project.id for project in projects])
    opened = dict(db.execute(select(EscrowTransaction.agreement_id, EscrowTransaction.confirmed_at).where(
        EscrowTransaction.agreement_id.in_([agreement.id for agreement, _ in rows]),
        EscrowTransaction.event == "DisputeOpened",
    )).tuples().all())
    if rows:
        logger.info("event=disputes_viewed request_id=%s admin_id=%s count=%s",
                    request.state.request_id, admin.user.id, len(rows))
    return [DisputeView(
        agreement_id=agreement.id, project_id=project.id, project_title=project.title,
        client_name=clients[project.client_id].name, freelancer_name=freelancers[project.freelancer_id].name,
        milestone_number=agreement.milestone_number, attempt_number=agreement.attempt_number,
        escrow_id=agreement.expected_escrow_id, terms_json=agreement.terms_json, terms_hash=agreement.terms_hash,
        status=agreement.status, opened_at=opened.get(agreement.id),
        submissions=[item for item in history[project.id] if item.agreement_id == agreement.id],
    ) for agreement, project in rows]

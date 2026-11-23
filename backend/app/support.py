from datetime import datetime, timezone
from decimal import Decimal
from json import loads
import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AdminIdentity, CurrentIdentity, Db, Identity, trusted_origin
from app.errors import api_error
from app.escrow import project_agreements
from app.marketplace import get_project
from app.models import EscrowTransaction, Project, SupportProjectAccess, SupportReport, SupportReportMessage, User, WorkSubmission
from app.notifications import notify
from app.schemas import ApiModel


router = APIRouter(tags=["support"])
logger = logging.getLogger("uvicorn.error")
SupportTopic = Literal["general", "payment", "account", "report"]
SupportStatus = Literal["open", "waiting", "resolved"]
write = [Depends(trusted_origin)]


class SupportRequest(ApiModel):
    topic: SupportTopic
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=5000)]
    project_id: UUID | None = None


class ReportReceipt(ApiModel):
    id: UUID


class ReportStatusChange(ApiModel):
    status: Literal["resolved"]


class ReportResponse(ReportReceipt):
    target: str | None
    project_id: UUID | None
    topic: SupportTopic
    reason: str
    reporter: str
    contact: str
    status: SupportStatus
    created_at: datetime
    updated_at: datetime


class ReportMessageCreate(ApiModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    wait_for_reporter: bool = False


class ReportMessageResponse(ApiModel):
    id: UUID
    from_admin: bool
    body: str
    created_at: datetime


class ReportThread(ReportResponse):
    messages: list[ReportMessageResponse]


class ReportMilestoneView(ApiModel):
    number: int
    title: str
    amount_thb: Decimal
    escrow_status: Literal["unprepared", "prepared", "pending_verification", "funded", "released", "refunded", "resolved", "expired"]
    submission_status: Literal["pending", "revision", "approved"] | None = None
    submitted_at: datetime | None = None


class ReportProjectView(ApiModel):
    id: UUID
    status: str
    due_date: datetime
    milestones: list[ReportMilestoneView]


def report_views(db: Session, report_id: UUID | None = None, *, reporter_id: UUID | None = None) -> list[ReportResponse]:
    stmt = (select(SupportReport, User.name, User.email, Project.title)
            .join(User, User.id == SupportReport.reporter_id)
            .outerjoin(Project, Project.id == SupportReport.project_id)
            .order_by(SupportReport.updated_at.desc(), SupportReport.id))
    if report_id is not None:
        stmt = stmt.where(SupportReport.id == report_id)
    if reporter_id is not None:
        stmt = stmt.where(SupportReport.reporter_id == reporter_id)
    return [ReportResponse(id=report.id, target=title, project_id=report.project_id, topic=report.topic,
                           reason=report.reason, reporter=name, contact=email, status=report.status,
                           created_at=report.created_at, updated_at=report.updated_at)
            for report, name, email, title in db.execute(stmt)]


def get_report(db: Session, report_id: UUID, identity: Identity, *, lock: bool = False) -> SupportReport:
    report = db.get(SupportReport, report_id, with_for_update=lock or None)
    if report is None or (identity.user.role != "admin" and report.reporter_id != identity.user.id):
        raise api_error(404, "REPORT_NOT_FOUND", "ไม่พบรายงานปัญหา")
    return report


def report_thread(db: Session, report_id: UUID) -> ReportThread:
    report = report_views(db, report_id)[0]
    messages = db.scalars(select(SupportReportMessage).where(SupportReportMessage.report_id == report_id)
                          .order_by(SupportReportMessage.created_at, SupportReportMessage.id))
    return ReportThread(**report.model_dump(), messages=[ReportMessageResponse.model_validate(msg) for msg in messages])


def project_summary(db: Session, project: Project) -> ReportProjectView:
    agreements = project_agreements(db, project.id)
    if not agreements:
        return ReportProjectView(id=project.id, status=project.status, due_date=project.due_at, milestones=[
            ReportMilestoneView(number=1, title=project.title, amount_thb=project.budget, escrow_status="unprepared"),
        ])

    latest = {agreement.milestone_number: agreement for agreement in agreements}
    pending_ids = set(db.scalars(select(EscrowTransaction.agreement_id).where(
        EscrowTransaction.agreement_id.in_([item.id for item in latest.values() if item.status == "prepared"]),
        EscrowTransaction.status == "pending",
    )))
    submissions = db.execute(
        select(WorkSubmission.agreement_id, WorkSubmission.status, WorkSubmission.submitted_at)
        .where(WorkSubmission.project_id == project.id)
        .order_by(WorkSubmission.submitted_at.desc(), WorkSubmission.id)
    )
    milestone_numbers = {agreement.id: agreement.milestone_number for agreement in agreements}
    latest_submissions = {}
    for agreement_id, status, submitted_at in submissions:
        latest_submissions.setdefault(milestone_numbers[agreement_id], (status, submitted_at))

    milestones = []
    for number, item in enumerate(loads(agreements[0].terms_json)["milestones"], start=1):
        agreement = latest.get(number)
        escrow_status = agreement.status if agreement else "unprepared"
        if agreement and agreement.id in pending_ids:
            escrow_status = "pending_verification"
        submission_status, submitted_at = latest_submissions.get(number, (None, None))
        milestones.append(ReportMilestoneView(number=number, title=item["title"], amount_thb=item["amountThb"],
                                              escrow_status=escrow_status, submission_status=submission_status,
                                              submitted_at=submitted_at))
    return ReportProjectView(id=project.id, status=project.status, due_date=project.due_at, milestones=milestones)


@router.get("/admin/reports/{report_id}/project", response_model=ReportProjectView)
def read_report_project(report_id: UUID, request: Request, response: Response, db: Db, admin: AdminIdentity):
    report = get_report(db, report_id, admin, lock=True)
    if report.status == "resolved":
        raise api_error(409, "REPORT_CLOSED", "รายงานนี้ปิดแล้ว จึงเปิดดูสถานะโครงการไม่ได้")
    project = db.get(Project, report.project_id) if report.project_id else None
    if project is None:
        raise api_error(404, "REPORT_PROJECT_NOT_FOUND", "รายงานนี้ไม่มีโครงการที่เกี่ยวข้อง")
    view = project_summary(db, project)
    request_id = request.state.request_id
    db.add(SupportProjectAccess(report_id=report_id, project_id=project.id, admin_id=admin.user.id, request_id=request_id))
    db.commit()
    logger.info("event=support_project_viewed request_id=%s report_id=%s project_id=%s admin_id=%s",
                request_id, report_id, view.id, admin.user.id)
    response.headers["Cache-Control"] = "private, no-store"
    return view


@router.get("/support/reports", response_model=list[ReportResponse])
def list_my_reports(db: Db, identity: CurrentIdentity):
    return report_views(db, reporter_id=identity.user.id)


@router.get("/support/reports/{report_id}", response_model=ReportThread)
def read_report(report_id: UUID, db: Db, identity: CurrentIdentity):
    get_report(db, report_id, identity)
    return report_thread(db, report_id)


@router.post("/support/reports", response_model=ReportReceipt, status_code=201, dependencies=write)
def submit_report(payload: SupportRequest, db: Db, identity: CurrentIdentity):
    if payload.project_id is not None:
        get_project(db, payload.project_id, identity)
    report = SupportReport(reporter_id=identity.user.id, project_id=payload.project_id,
                           topic=payload.topic, reason=payload.message)
    db.add(report)
    db.flush()
    receipt = ReportReceipt(id=report.id)
    db.commit()
    return receipt


@router.post("/support/reports/{report_id}/messages", response_model=ReportThread, status_code=201, dependencies=write)
def reply_to_report(report_id: UUID, payload: ReportMessageCreate, db: Db, identity: CurrentIdentity):
    report = get_report(db, report_id, identity, lock=True)
    if report.status == "resolved":
        raise api_error(409, "REPORT_CLOSED", "รายงานนี้ปิดแล้ว")
    from_admin = identity.user.role == "admin"
    if payload.wait_for_reporter and not from_admin:
        raise api_error(403, "ADMIN_REQUIRED", "เฉพาะแอดมินที่ขอข้อมูลเพิ่มได้")
    now = datetime.now(timezone.utc)
    report.status = "waiting" if payload.wait_for_reporter else "open"
    report.updated_at = now
    db.add(SupportReportMessage(report_id=report_id, author_id=identity.user.id, from_admin=from_admin,
                                body=payload.body, created_at=now))
    if from_admin:
        title = "แอดมินขอข้อมูลเพิ่มเติม" if payload.wait_for_reporter else "แอดมินตอบเรื่องที่แจ้งแล้ว"
        notify(db, report.reporter_id, "support", title, "เปิดเรื่องที่แจ้งเพื่อดูข้อความ", f"/support/tickets/{report_id}")
    db.commit()
    return report_thread(db, report_id)


@router.patch("/admin/reports/{report_id}", response_model=ReportThread, dependencies=write)
def resolve_report(report_id: UUID, payload: ReportStatusChange, db: Db, admin: AdminIdentity):
    report = get_report(db, report_id, admin, lock=True)
    if report.status != payload.status:
        report.status = payload.status
        report.updated_at = datetime.now(timezone.utc)
        notify(db, report.reporter_id, "support", "ปิดเรื่องที่แจ้งแล้ว", "เปิดเรื่องที่แจ้งเพื่อดูประวัติและสถานะ",
               f"/support/tickets/{report_id}")
        db.commit()
    return report_thread(db, report_id)

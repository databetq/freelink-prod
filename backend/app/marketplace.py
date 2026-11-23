from base64 import b64decode
from binascii import Error as Base64Error
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
import logging
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BeforeValidator, Field
from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.orm import Session

from app.auth import CurrentIdentity, Db, Identity, OptionalIdentity, trusted_origin
from app.escrow_chain import hex_hash
from app.errors import api_error
from app.messages import open_project_thread
from app.models import EscrowAgreement, EscrowTransaction, FreelancerReview, Job, Profile, Project, Proposal, User, WorkAttachment, WorkSubmission
from app.notifications import notify
from app.profiles import client_cards, display_name, freelancer_cards
from app.schemas import (
    ClientCard, FreelancerReviewCreate, FreelancerReviewView, HireResponse, JobCreate, JobPatch, JobResponse, ProjectResponse,
    ProposalPatch, ProposalResponse, ProposalWrite,
    WORK_ATTACHMENT_LIMIT, WorkFileResponse, WorkLinkInput, WorkReviewRequest, WorkRevisionRequest, WorkSubmissionCreate,
    WorkSubmissionResponse,
)

router = APIRouter(tags=["marketplace"])
logger = logging.getLogger("uvicorn.error")
write = [Depends(trusted_origin)]
BudgetFilter = Annotated[Decimal, Field(ge=0)]


def empty_filter(value):
    return None if value == "" else value


# Freelink serves Thailand (UTC+7, no daylight saving), so a deadline's "today" is the Thai calendar day.
PLATFORM_TZ = timezone(timedelta(hours=7))


def platform_today() -> date:
    return datetime.now(PLATFORM_TZ).date()


def ensure_deadline_not_past(deadline: date | None) -> None:
    if deadline is not None and deadline < platform_today():
        raise api_error(422, "INVALID_DEADLINE", "กำหนดส่งต้องไม่เป็นวันที่ผ่านมาแล้ว")


def require_role(identity: Identity, role: str) -> None:
    if identity.user.role != role:
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์ทำรายการ")


def require_owner(identity: Identity, profile_id: UUID) -> None:
    if identity.profile.id != profile_id:
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์เข้าถึงรายการ")


def get_job(db: Session, job_id: UUID, *, lock: bool = False) -> Job:
    job = db.get(Job, job_id, with_for_update=True if lock else None)
    if job is None:
        raise api_error(404, "JOB_NOT_FOUND", "ไม่พบงาน")
    return job


PROPOSAL_DECISIONS = {
    "shortlisted": ("ข้อเสนอของคุณผ่านการคัดเลือก", "ถูกเลือกเข้ารอบแล้ว"),
    "rejected": ("ข้อเสนอของคุณไม่ผ่านการคัดเลือก", "ไม่ได้รับการคัดเลือก"),
}


def profile_user_id(db: Session, profile_id: UUID) -> UUID:
    return db.scalar(select(Profile.user_id).where(Profile.id == profile_id))


def get_proposal(db: Session, proposal_id: UUID) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise api_error(404, "PROPOSAL_NOT_FOUND", "ไม่พบข้อเสนอ")
    return proposal


proposal_count = (
    select(func.count(Proposal.id)).where(Proposal.job_id == Job.id).correlate(Job).scalar_subquery()
)
client_name = func.coalesce(Profile.display_name, User.name)
job_query = (
    select(Job, client_name, proposal_count)
    .join(Profile, Job.client_id == Profile.id)
    .join(User, User.id == Profile.user_id)
)


def job_view(job: Job, client_name: str, count: int) -> JobResponse:
    return JobResponse(
        id=job.id, client_id=job.client_id, client=ClientCard(id=job.client_id, name=client_name),
        title=job.title, description=job.description, category=job.category,
        skills=job.skills, deliverables=job.deliverables, budget_min=job.budget_min,
        budget_max=job.budget_max, budget_type=job.budget_type, duration=job.duration,
        experience=job.experience, deadline=job.deadline, status=job.status,
        created_at=job.created_at, proposals_count=count,
    )


def with_clients(db: Session, views: list[JobResponse]) -> list[JobResponse]:
    """Fill each job's `client` with the client's name, avatar and track record, loaded for all jobs at once."""
    cards = client_cards(db, {view.client_id for view in views})
    hired = [view.id for view in views if view.status in ("in_progress", "closed")]
    completed = db.execute(select(Project.id, Project.job_id).where(
        Project.job_id.in_(hired), Project.status == "completed",
    )).all() if hired else []
    completed_ids = {job_id for _, job_id in completed}
    plans = latest_agreements(db, [project_id for project_id, _ in completed])
    closed_ids = {job_id for project_id, job_id in completed if plan_released(plans.get(project_id, {}))}
    for view in views:
        view.client = cards.get(view.client_id, view.client)
        view.project_completed = view.id in completed_ids
        view.project_paid = view.id in closed_ids
        if view.id in closed_ids:
            view.status = "closed"
    return views


def job_details(db: Session, job_id: UUID) -> JobResponse:
    row = db.execute(job_query.where(Job.id == job_id)).one_or_none()
    if row is None:
        raise api_error(404, "JOB_NOT_FOUND", "ไม่พบงาน")
    return with_clients(db, [job_view(*row)])[0]


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    db: Db,
    q: str = Query("", max_length=200),
    category: str = "",
    budget_type: Annotated[
        Literal["fixed", "hourly"] | None, BeforeValidator(empty_filter), Query(alias="budgetType")
    ] = None,
    min_budget: Annotated[BudgetFilter | None, BeforeValidator(empty_filter), Query(alias="minBudget")] = None,
    max_budget: Annotated[BudgetFilter | None, BeforeValidator(empty_filter), Query(alias="maxBudget")] = None,
    status: Literal["open", "in_progress", "closed"] = "open",
    client_id: Annotated[UUID | None, Query(alias="clientId")] = None,
    sort: Literal["recent", "budget_desc", "budget_asc", "proposals"] = "recent",
    featured: bool = False,
):
    if featured:
        return []
    stmt = job_query.where(Job.status == status, User.status == "active")
    if q.strip():
        term = q.strip()
        stmt = stmt.where(or_(
            Job.title.icontains(term, autoescape=True),
            Job.description.icontains(term, autoescape=True),
            cast(Job.skills, String).icontains(term, autoescape=True),
            client_name.icontains(term, autoescape=True),
        ))
    if category:
        stmt = stmt.where(Job.category == category)
    if budget_type:
        stmt = stmt.where(Job.budget_type == budget_type)
    if min_budget is not None:
        stmt = stmt.where(Job.budget_min >= min_budget)
    if max_budget is not None:
        stmt = stmt.where(Job.budget_max <= max_budget)
    if client_id:
        stmt = stmt.where(Job.client_id == client_id)
    ordering = {
        "recent": Job.created_at.desc(), "budget_desc": Job.budget_max.desc(),
        "budget_asc": Job.budget_min.asc(), "proposals": proposal_count.desc(),
    }
    return with_clients(db, [job_view(*row) for row in db.execute(stmt.order_by(ordering[sort], Job.id))])


@router.get("/jobs/{job_id}", response_model=JobResponse)
def read_job(job_id: UUID, db: Db, identity: OptionalIdentity):
    job = job_details(db, job_id)
    if job.status == "draft" and (not identity or identity.profile.id != job.client_id):
        raise api_error(404, "JOB_NOT_FOUND", "ไม่พบงาน")
    return job


@router.get("/clients/{client_id}/jobs", response_model=list[JobResponse])
def client_jobs(client_id: UUID, db: Db, identity: CurrentIdentity):
    require_owner(identity, client_id)
    stmt = job_query.where(Job.client_id == client_id).order_by(Job.created_at.desc())
    return with_clients(db, [job_view(*row) for row in db.execute(stmt)])


@router.post("/jobs", response_model=JobResponse, status_code=201, dependencies=write)
def create_job(payload: JobCreate, db: Db, identity: CurrentIdentity):
    require_role(identity, "client")
    ensure_deadline_not_past(payload.deadline)
    job = Job(**payload.model_dump(), client_id=identity.profile.id)
    db.add(job)
    db.flush()
    job_id = job.id
    db.commit()
    return job_details(db, job_id)


def ensure_editable(db: Session, job: Job) -> None:
    if job.status == "in_progress" or db.scalar(select(Project.id).where(Project.job_id == job.id)):
        raise api_error(409, "JOB_ALREADY_HIRED", "งานนี้จ้าง freelancer แล้ว")


@router.patch("/jobs/{job_id}", response_model=JobResponse, dependencies=write)
def edit_job(job_id: UUID, payload: JobPatch, db: Db, identity: CurrentIdentity):
    job = get_job(db, job_id, lock=True)
    require_owner(identity, job.client_id)
    ensure_editable(db, job)
    changes = payload.model_dump(exclude_unset=True)
    # Only a new date is checked, so an overdue posting can still have its other fields edited.
    if "deadline" in changes and changes["deadline"] != job.deadline:
        ensure_deadline_not_past(changes["deadline"])
    if changes.get("budget_max", job.budget_max) < changes.get("budget_min", job.budget_min):
        raise api_error(422, "INVALID_BUDGET", "งบสูงสุดต้องไม่น้อยกว่างบต่ำสุด")
    for field, value in changes.items():
        setattr(job, field, value)
    db.commit()
    return job_details(db, job_id)


@router.delete("/jobs/{job_id}", status_code=204, dependencies=write)
def delete_job(job_id: UUID, db: Db, identity: CurrentIdentity):
    job = get_job(db, job_id, lock=True)
    require_owner(identity, job.client_id)
    ensure_editable(db, job)
    db.delete(job)
    db.commit()
    return Response(status_code=204)


def proposal_views(db: Session, proposals: list[Proposal]) -> list[ProposalResponse]:
    if not proposals:
        return []
    job_ids = {proposal.job_id for proposal in proposals}
    jobs = {row[0].id: job_view(*row) for row in db.execute(job_query.where(Job.id.in_(job_ids)))}
    with_clients(db, list(jobs.values()))
    profiles = freelancer_cards(db, {proposal.freelancer_id for proposal in proposals})
    return [
        ProposalResponse(
            id=item.id, job_id=item.job_id, freelancer_id=item.freelancer_id,
            freelancer=profiles[item.freelancer_id], job=jobs[item.job_id],
            bid_amount=item.bid_amount, delivery_days=item.delivery_days,
            cover_letter=item.cover_letter, attachments=item.attachments,
            status=item.status, created_at=item.created_at,
        )
        for item in proposals
    ]


@router.get("/jobs/{job_id}/proposals", response_model=list[ProposalResponse])
def job_proposals(job_id: UUID, db: Db, identity: CurrentIdentity):
    require_owner(identity, get_job(db, job_id).client_id)
    stmt = select(Proposal).where(Proposal.job_id == job_id).order_by(Proposal.created_at.desc())
    return proposal_views(db, list(db.scalars(stmt)))


@router.post("/jobs/{job_id}/proposals", response_model=ProposalResponse, status_code=201, dependencies=write)
def create_proposal(job_id: UUID, payload: ProposalWrite, db: Db, identity: CurrentIdentity):
    require_role(identity, "freelancer")
    job = get_job(db, job_id, lock=True)
    if job.status != "open":
        raise api_error(409, "JOB_NOT_OPEN", "งานนี้ปิดรับข้อเสนอแล้ว")
    if payload.bid_amount > job.budget_max:
        raise api_error(422, "BID_OVER_BUDGET", "ราคาเสนอต้องไม่เกินงบสูงสุดของงาน")
    existing = db.scalar(select(Proposal.id).where(
        Proposal.job_id == job_id, Proposal.freelancer_id == identity.profile.id,
    ))
    if existing:
        raise api_error(409, "DUPLICATE_PROPOSAL", "ส่งข้อเสนอสำหรับงานนี้แล้ว")
    proposal = Proposal(**payload.model_dump(), job_id=job_id, freelancer_id=identity.profile.id)
    db.add(proposal)
    notify(
        db, profile_user_id(db, job.client_id), "proposal", "มีข้อเสนอใหม่",
        f"{display_name(identity.profile, identity.user)} ส่งข้อเสนอสำหรับ “{job.title}”",
        f"/client/jobs/{job.id}/applicants",
    )
    db.commit()
    return proposal_views(db, [proposal])[0]


@router.get("/freelancers/{freelancer_id}/proposals", response_model=list[ProposalResponse])
def freelancer_proposals(freelancer_id: UUID, db: Db, identity: CurrentIdentity):
    require_owner(identity, freelancer_id)
    stmt = select(Proposal).where(Proposal.freelancer_id == freelancer_id).order_by(Proposal.created_at.desc())
    return proposal_views(db, list(db.scalars(stmt)))


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
def read_proposal(proposal_id: UUID, db: Db, identity: CurrentIdentity):
    proposal = get_proposal(db, proposal_id)
    if identity.profile.id not in (proposal.freelancer_id, get_job(db, proposal.job_id).client_id):
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์ดูข้อเสนอ")
    return proposal_views(db, [proposal])[0]


def lock_proposal_job(db: Session, proposal_id: UUID) -> tuple[Proposal, Job]:
    job_id = db.scalar(select(Proposal.job_id).where(Proposal.id == proposal_id))
    if job_id is None:
        raise api_error(404, "PROPOSAL_NOT_FOUND", "ไม่พบข้อเสนอ")
    job = get_job(db, job_id, lock=True)
    return get_proposal(db, proposal_id), job


def ensure_pending_proposal(proposal: Proposal, job: Job) -> None:
    if job.status != "open" or proposal.status not in ("pending", "shortlisted"):
        raise api_error(409, "PROPOSAL_NOT_ACTIVE", "ข้อเสนอนี้ดำเนินการต่อไม่ได้")


@router.patch("/proposals/{proposal_id}", response_model=ProposalResponse, dependencies=write)
def edit_proposal(proposal_id: UUID, payload: ProposalPatch, db: Db, identity: CurrentIdentity):
    proposal, job = lock_proposal_job(db, proposal_id)
    require_owner(identity, job.client_id)
    ensure_pending_proposal(proposal, job)
    if payload.status != proposal.status and payload.status in PROPOSAL_DECISIONS:
        title, outcome = PROPOSAL_DECISIONS[payload.status]
        notify(
            db, profile_user_id(db, proposal.freelancer_id), "proposal", title,
            f"ข้อเสนอสำหรับ “{job.title}” {outcome}", "/freelancer/proposals",
        )
    proposal.status = payload.status
    db.commit()
    return proposal_views(db, [proposal])[0]


@router.post("/proposals/{proposal_id}/withdraw", response_model=ProposalResponse, dependencies=write)
def withdraw_proposal(proposal_id: UUID, db: Db, identity: CurrentIdentity):
    proposal, job = lock_proposal_job(db, proposal_id)
    require_owner(identity, proposal.freelancer_id)
    ensure_pending_proposal(proposal, job)
    proposal.status = "withdrawn"
    db.commit()
    return proposal_views(db, [proposal])[0]


@router.post("/proposals/{proposal_id}/hire", response_model=HireResponse, dependencies=write)
def hire_proposal(proposal_id: UUID, db: Db, identity: CurrentIdentity):
    proposal, job = lock_proposal_job(db, proposal_id)
    require_owner(identity, job.client_id)
    project = db.scalar(select(Project).where(Project.job_id == job.id))
    if project:
        if project.proposal_id != proposal_id:
            raise api_error(409, "JOB_ALREADY_HIRED", "งานนี้จ้างจากข้อเสนออื่นแล้ว")
    else:
        ensure_pending_proposal(proposal, job)
        if db.get(User, profile_user_id(db, proposal.freelancer_id)).status != "active":
            raise api_error(409, "FREELANCER_UNAVAILABLE", "บัญชีฟรีแลนซ์นี้ยังรับงานไม่ได้")
        project = Project(
            job_id=job.id, proposal_id=proposal.id, client_id=job.client_id,
            freelancer_id=proposal.freelancer_id, title=job.title, budget=proposal.bid_amount,
            due_at=datetime.now(timezone.utc) + timedelta(days=proposal.delivery_days),
        )
        proposal.status = "hired"
        job.status = "in_progress"
        db.add(project)
        open_project_thread(db, project)
        notify(
            db, profile_user_id(db, proposal.freelancer_id), "job", "คุณได้รับงานแล้ว",
            f"ลูกค้าเลือกข้อเสนอของคุณสำหรับ “{job.title}”", f"/freelancer/projects/{project.id}",
        )
        db.execute(update(Proposal).where(
            Proposal.job_id == job.id, Proposal.id != proposal_id,
            Proposal.status.in_(("pending", "shortlisted")),
        ).values(status="rejected"))
        db.commit()
    return HireResponse(project=project_views(db, [project])[0], job=job_details(db, job.id))


def revision_limit(terms: dict) -> int:
    return terms.get("revisionPolicy", {}).get("maxRevisions", 2)


def submission_history(db: Session, project_ids: list[UUID]) -> dict[UUID, list[WorkSubmissionResponse]]:
    submissions = db.execute(select(WorkSubmission, EscrowAgreement.milestone_number, EscrowAgreement.terms_json)
                             .join(EscrowAgreement, EscrowAgreement.id == WorkSubmission.agreement_id)
                             .where(WorkSubmission.project_id.in_(project_ids))
                             .order_by(WorkSubmission.submitted_at.desc(), WorkSubmission.id)).all()
    history = defaultdict(list)
    if not submissions:
        return history
    files = defaultdict(list)
    attachments = db.scalars(select(WorkAttachment).where(WorkAttachment.submission_id.in_([s.id for s, _, _ in submissions]))
                             .order_by(WorkAttachment.name, WorkAttachment.id))
    for attachment in attachments:
        files[attachment.submission_id].append(WorkFileResponse.model_validate(attachment))
    revisions = Counter(submission.agreement_id for submission, _, _ in submissions if submission.status == "revision")
    for submission, milestone_number, terms_json in submissions:
        view = WorkSubmissionResponse.model_validate(submission)
        terms = loads(terms_json)
        view.milestone_number = milestone_number
        view.checklist = terms.get("checklist") or terms["milestones"][milestone_number - 1].get("checklist", [])
        view.revision_limit = revision_limit(terms)
        view.revisions_used = revisions[submission.agreement_id]
        if not view.links and submission.link:
            view.links = [WorkLinkInput(url=submission.link)]
        view.files = files[submission.id]
        history[submission.project_id].append(view)
    return history


def latest_agreements(db: Session, project_ids: list[UUID]) -> dict[UUID, dict[int, EscrowAgreement]]:
    plans = defaultdict(dict)
    if project_ids:
        agreements = db.scalars(select(EscrowAgreement).where(EscrowAgreement.project_id.in_(project_ids))
                                .order_by(EscrowAgreement.milestone_number, EscrowAgreement.attempt_number))
        for agreement in agreements:
            plans[agreement.project_id][agreement.milestone_number] = agreement
    return plans


def project_views(db: Session, projects: list[Project]) -> list[ProjectResponse]:
    if not projects:
        return []
    history = submission_history(db, [project.id for project in projects])
    reviewed_ids = set(db.scalars(select(FreelancerReview.project_id)
                                  .where(FreelancerReview.project_id.in_([p.id for p in projects]))))
    clients = client_cards(db, {project.client_id for project in projects})
    freelancers = freelancer_cards(db, {project.freelancer_id for project in projects})
    plans = latest_agreements(db, [p.id for p in projects])
    prepared_ids = [agreement.id for plan in plans.values() for agreement in plan.values()
                    if agreement.status == "prepared"]
    pending_ids = set(db.scalars(select(EscrowTransaction.agreement_id).where(
        EscrowTransaction.agreement_id.in_(prepared_ids), EscrowTransaction.status == "pending",
    ).distinct())) if prepared_ids else set()
    responses = []
    for project in projects:
        view = ProjectResponse.model_validate(project)
        view.client = clients.get(project.client_id)
        view.freelancer = freelancers.get(project.freelancer_id)
        view.submissions = history[project.id]
        view.freelancer_reviewed = project.id in reviewed_ids
        latest = plans.get(project.id)
        if latest:
            milestones = loads(latest[1].terms_json)["milestones"]
            next_number = 1
            for number, milestone in enumerate(milestones, 1):
                item = latest.get(number)
                state = item.status if item else "prepared"
                terms = loads(item.terms_json) if item else None
                amount = float(milestone["amountThb"])
                if state == "released":
                    view.released_amount += amount
                    next_number = number + 1
                if state == "funded":
                    view.escrow_amount += amount
                due = terms["deadline"] if terms else milestone.get("deadline")
                view.milestones.append({
                    "id": number, "title": milestone["title"], "amount": amount,
                    "status": {"released": "completed", "funded": "in_progress"}.get(state, "pending"),
                    "dueDate": datetime.fromtimestamp(due, timezone.utc) if due else None,
                })
            current = latest.get(next_number)
            if milestones_released(latest, len(milestones)):
                view.escrow_status = "released"
            elif current and current.status in ("funded", "refunded", "resolved"):
                view.escrow_status = current.status
            elif current and current.id in pending_ids:
                view.escrow_status = "pending_verification"
            view.can_submit_work = bool(current and current.status == "funded"
                                        and project.status in ("active", "revision")
                                        and not any(item.agreement_id == current.id and item.status == "approved"
                                                    for item in view.submissions))
        responses.append(view)
    return responses


def milestones_released(latest: dict[int, EscrowAgreement], total: int) -> bool:
    return total > 0 and all(latest.get(number) and latest[number].status == "released"
                             for number in range(1, total + 1))


def plan_released(latest: dict[int, EscrowAgreement]) -> bool:
    return 1 in latest and milestones_released(latest, len(loads(latest[1].terms_json)["milestones"]))


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(db: Db, identity: CurrentIdentity):
    profile_id = identity.profile.id
    stmt = select(Project).where(
        or_(Project.client_id == profile_id, Project.freelancer_id == profile_id)
    ).order_by(Project.created_at.desc())
    return project_views(db, list(db.scalars(stmt)))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def read_project(project_id: UUID, db: Db, identity: CurrentIdentity):
    return project_views(db, [get_project(db, project_id, identity)])[0]


@router.post("/freelancers/{freelancer_id}/reviews", status_code=201,
             response_model=FreelancerReviewView, dependencies=write)
def create_freelancer_review(freelancer_id: UUID, payload: FreelancerReviewCreate, request: Request,
                             db: Db, identity: CurrentIdentity):
    project = get_project(db, payload.project_id, identity, lock=True)
    require_role(identity, "client")
    require_owner(identity, project.client_id)
    if freelancer_id != project.freelancer_id:
        raise api_error(404, "PROJECT_FREELANCER_NOT_FOUND", "ฟรีแลนซ์นี้ไม่ได้รับงานในโครงการ")
    view = project_views(db, [project])[0]
    if view.status != "completed" or view.escrow_status != "released":
        raise api_error(409, "REVIEW_NOT_ELIGIBLE", "รีวิวได้หลังอนุมัติงานครบและยืนยันการจ่ายเงินงวดสุดท้ายแล้ว")
    if view.freelancer_reviewed:
        raise api_error(409, "REVIEW_ALREADY_EXISTS", "โครงการนี้มีรีวิวแล้ว")
    review = FreelancerReview(project_id=project.id, rating=payload.rating, comment=payload.comment,
                              request_id=request.state.request_id)
    db.add(review)
    db.flush()
    response = FreelancerReviewView.model_validate(review)
    db.commit()
    logger.info("event=freelancer_review_created request_id=%s review_id=%s project_id=%s client_id=%s freelancer_id=%s",
                request.state.request_id, response.id, payload.project_id, identity.profile.id, freelancer_id)
    return response


def get_project(db: Session, project_id: UUID, identity: Identity, *, lock: bool = False) -> Project:
    project = db.get(Project, project_id, with_for_update=lock or None)
    if project is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "ไม่พบโปรเจกต์")
    if identity.profile.id not in (project.client_id, project.freelancer_id):
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์ดูโปรเจกต์")
    return project


@router.post("/projects/{project_id}/submissions", response_model=ProjectResponse, status_code=201, dependencies=write)
def submit_work(project_id: UUID, payload: WorkSubmissionCreate, db: Db, identity: CurrentIdentity):
    require_owner(identity, get_project(db, project_id, identity).freelancer_id)
    # The escrow sync locks the agreement before the project, so this takes the same order.
    agreement = db.scalar(select(EscrowAgreement).where(EscrowAgreement.project_id == project_id)
                          .order_by(EscrowAgreement.milestone_number.desc(), EscrowAgreement.attempt_number.desc())
                          .limit(1).with_for_update())
    project = get_project(db, project_id, identity, lock=True)
    db.refresh(project)
    if project.status not in ("active", "revision"):
        raise api_error(409, "PROJECT_NOT_READY_FOR_SUBMISSION", "โครงการยังไม่พร้อมรับงานส่งมอบ")
    if agreement is None or agreement.status != "funded":
        raise api_error(409, "ESCROW_NOT_FUNDED", "รอให้ระบบยืนยันการฝากเงินเข้า Escrow ของงวดนี้ก่อนส่งงาน")
    if db.scalar(select(WorkSubmission.id).where(
        WorkSubmission.agreement_id == agreement.id, WorkSubmission.status == "approved",
    ).limit(1)):
        raise api_error(409, "WORK_ALREADY_APPROVED", "งานงวดนี้ผ่านการตรวจรับแล้ว")

    attachments = []
    size = 0
    for file in payload.files:
        if any(ord(char) < 32 or char in "/\\" for char in file.name):
            raise api_error(422, "INVALID_WORK_FILE", "ชื่อไฟล์แนบไม่ถูกต้อง")
        try:
            content = b64decode(file.content, validate=True)
        except (Base64Error, ValueError):
            raise api_error(422, "INVALID_WORK_FILE", "อ่านไฟล์แนบไม่สำเร็จ") from None
        size += len(content)
        if size > WORK_ATTACHMENT_LIMIT:
            raise api_error(413, "WORK_FILES_TOO_LARGE", "ขนาดไฟล์แนบรวมต้องไม่เกิน 5 MB")
        attachments.append((file.name, content))

    links = [link.model_dump(mode="json") for link in payload.links]
    first_link = links[0]["url"] if links else str(payload.link) if payload.link else None
    submission_id = uuid4()
    commitment = dumps({
        "submissionId": str(submission_id),
        "agreementId": str(agreement.id),
        "title": payload.title,
        "description": payload.description,
        "link": first_link,
        "links": links,
        "files": [{"name": name, "sha256": sha256(content).hexdigest()} for name, content in attachments],
    }, sort_keys=True, separators=(",", ":"))
    submission = WorkSubmission(id=submission_id, project_id=project_id, agreement_id=agreement.id,
                                title=payload.title, description=payload.description, link=first_link, links=links,
                                work_hash=hex_hash(commitment.encode("utf-8")))
    db.add(submission)
    db.flush()
    db.add_all(WorkAttachment(submission_id=submission.id, name=name, content=content) for name, content in attachments)
    project.status = "in_review"
    notify(db, profile_user_id(db, project.client_id), "submission", "มีงานรอยืนยันการส่งบน Sepolia", project.title,
           f"/client/projects/{project_id}/review")
    db.commit()
    return project_views(db, [project])[0]


@router.get("/projects/{project_id}/work-files/{file_id}", response_class=Response)
def download_work_file(project_id: UUID, file_id: UUID, db: Db, identity: CurrentIdentity):
    get_project(db, project_id, identity)
    attachment = db.scalar(select(WorkAttachment).join(WorkSubmission, WorkAttachment.submission_id == WorkSubmission.id)
                           .where(WorkAttachment.id == file_id, WorkSubmission.project_id == project_id))
    if attachment is None:
        raise api_error(404, "WORK_FILE_NOT_FOUND", "ไม่พบไฟล์แนบ")
    return Response(attachment.content, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.name, safe='')}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })


def review_submission(db: Session, project: Project, submission_id: UUID) -> WorkSubmission:
    submission = db.get(WorkSubmission, submission_id)
    if (project.status != "in_review" or submission is None or submission.project_id != project.id
            or submission.status != "pending"):
        raise api_error(409, "WORK_NOT_PENDING", "งานส่งมอบนี้ไม่ได้อยู่ระหว่างการตรวจรับแล้ว")
    if submission.work_hash and submission.chain_submitted_at is None:
        raise api_error(409, "WORK_NOT_ON_CHAIN", "รอให้ระบบยืนยันการส่งงานบน Sepolia ก่อนตรวจรับ")
    return submission


def funded_agreement(db: Session, submission: WorkSubmission) -> EscrowAgreement:
    agreement = db.get(EscrowAgreement, submission.agreement_id)
    if agreement.status != "funded":
        raise api_error(409, "ESCROW_NOT_FUNDED", "เงินของงวดนี้ไม่ได้อยู่ใน Escrow แล้ว")
    return agreement


@router.post("/projects/{project_id}/approve", response_model=ProjectResponse, dependencies=write)
def approve_work(project_id: UUID, payload: WorkReviewRequest, db: Db, identity: CurrentIdentity):
    project = get_project(db, project_id, identity, lock=True)
    require_owner(identity, project.client_id)
    submission = review_submission(db, project, payload.submission_id)
    funded_agreement(db, submission)
    submission.status = "approved"
    project.status = "active"
    notify(db, profile_user_id(db, project.freelancer_id), "submission", "ลูกค้าอนุมัติงานแล้ว", project.title,
           f"/freelancer/projects/{project_id}")
    db.commit()
    return project_views(db, [project])[0]


@router.post("/projects/{project_id}/request-revision", response_model=ProjectResponse, dependencies=write)
def request_work_revision(project_id: UUID, payload: WorkRevisionRequest, db: Db, identity: CurrentIdentity):
    project = get_project(db, project_id, identity, lock=True)
    require_owner(identity, project.client_id)
    submission = review_submission(db, project, payload.submission_id)
    agreement = funded_agreement(db, submission)
    if submission.chain_review_ends_at is not None and datetime.now(timezone.utc) > submission.chain_review_ends_at:
        raise api_error(409, "WORK_REVIEW_EXPIRED", "พ้นช่วงตรวจรับบน Sepolia แล้ว จึงขอแก้ไขไม่ได้")
    used = db.scalar(select(func.count()).select_from(WorkSubmission).where(
        WorkSubmission.agreement_id == agreement.id, WorkSubmission.status == "revision",
    ))
    if used >= revision_limit(loads(agreement.terms_json)):
        raise api_error(409, "WORK_REVISION_LIMIT_REACHED", "ใช้สิทธิ์ขอแก้ไขงานครบตามข้อตกลงแล้ว")
    submission.status = "revision"
    submission.feedback = payload.feedback
    project.status = "revision"
    notify(db, profile_user_id(db, project.freelancer_id), "submission", "ลูกค้าขอแก้ไขงาน", project.title,
           f"/freelancer/projects/{project_id}")
    db.commit()
    return project_views(db, [project])[0]

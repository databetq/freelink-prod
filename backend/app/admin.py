from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field, StringConstraints
from sqlalchemy import delete, select

from app.auth import AdminIdentity, Db, require_admin, trusted_origin
from app.errors import api_error
from app.marketplace import job_query, job_view, with_clients
from app.models import AdminUserNotice, AdminUserStatusEvent, Job, LoginSession, User
from app.schemas import ApiModel, JobResponse
from app.support import ReportResponse, report_views

router = APIRouter(prefix="/admin", tags=["admin"])
UserStatus = Literal["active", "suspended"]
NoticeKind = Literal["warning", "flag"]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AdminUserResponse(ApiModel):
    id: UUID
    name: str
    contact: str = Field(validation_alias="email")
    role: Literal["client", "freelancer", "admin"]
    status: UserStatus
    joined: datetime = Field(validation_alias="created_at")


class AdminOverview(ApiModel):
    users: list[AdminUserResponse]
    jobs: list[JobResponse]
    reports: list[ReportResponse]


class UserStatusChange(ApiModel):
    status: UserStatus
    reason: Reason


class UserNoticeCreate(ApiModel):
    kind: NoticeKind
    reason: Reason


class ModerationEntry(ApiModel):
    id: UUID
    kind: Literal["warning", "flag", "status"]
    reason: str
    actor_name: str
    created_at: datetime
    previous_status: UserStatus | None = None
    new_status: UserStatus | None = None


@router.get("/overview", response_model=AdminOverview, dependencies=[Depends(require_admin)])
def overview(db: Db):
    users = db.scalars(select(User).order_by(User.created_at.desc(), User.id))
    jobs = db.execute(job_query.order_by(Job.created_at.desc(), Job.id))
    return AdminOverview(
        users=[AdminUserResponse.model_validate(user) for user in users],
        jobs=with_clients(db, [job_view(*row) for row in jobs]),
        reports=report_views(db),
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse, dependencies=[Depends(trusted_origin)])
def change_user_status(user_id: UUID, payload: UserStatusChange, db: Db, admin: AdminIdentity):
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise api_error(404, "USER_NOT_FOUND", "ไม่พบบัญชีผู้ใช้")
    if user.role == "admin":
        raise api_error(403, "ADMIN_ACCOUNT_PROTECTED", "หน้านี้จัดการสถานะเฉพาะบัญชีคนจ้างและคนรับงาน")
    if user.status != payload.status:
        db.add(AdminUserStatusEvent(
            actor_id=admin.user.id, target_id=user.id, previous_status=user.status,
            new_status=payload.status, reason=payload.reason,
        ))
        user.status = payload.status
        if user.status == "suspended":
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        result = AdminUserResponse.model_validate(user)
        db.commit()
        return result
    return AdminUserResponse.model_validate(user)


@router.get("/users/{user_id}/moderation", response_model=list[ModerationEntry], dependencies=[Depends(require_admin)])
def moderation_history(user_id: UUID, db: Db):
    if db.get(User, user_id) is None:
        raise api_error(404, "USER_NOT_FOUND", "ไม่พบบัญชีผู้ใช้")
    notices = db.execute(
        select(AdminUserNotice, User.name).join(User, AdminUserNotice.actor_id == User.id)
        .where(AdminUserNotice.target_id == user_id)
    )
    changes = db.execute(
        select(AdminUserStatusEvent, User.name).join(User, AdminUserStatusEvent.actor_id == User.id)
        .where(AdminUserStatusEvent.target_id == user_id)
    )
    entries = [
        ModerationEntry(id=notice.id, kind=notice.kind, reason=notice.reason,
                        actor_name=name, created_at=notice.created_at)
        for notice, name in notices
    ]
    entries.extend(
        ModerationEntry(id=event.id, kind="status", reason=event.reason, actor_name=name,
                        created_at=event.created_at, previous_status=event.previous_status,
                        new_status=event.new_status)
        for event, name in changes
    )
    return sorted(entries, key=lambda entry: (entry.created_at, entry.id), reverse=True)


@router.post(
    "/users/{user_id}/notices", response_model=ModerationEntry, status_code=201,
    dependencies=[Depends(trusted_origin)],
)
def add_notice(user_id: UUID, payload: UserNoticeCreate, db: Db, admin: AdminIdentity):
    user = db.get(User, user_id)
    if user is None:
        raise api_error(404, "USER_NOT_FOUND", "ไม่พบบัญชีผู้ใช้")
    if user.role == "admin":
        raise api_error(403, "ADMIN_ACCOUNT_PROTECTED", "หน้านี้จัดการเฉพาะบัญชีคนจ้างและคนรับงาน")
    notice = AdminUserNotice(
        target_id=user.id, actor_id=admin.user.id, kind=payload.kind, reason=payload.reason,
    )
    db.add(notice)
    db.flush()
    result = ModerationEntry(id=notice.id, kind=notice.kind, reason=notice.reason,
                             actor_name=admin.user.name, created_at=notice.created_at)
    db.commit()
    return result

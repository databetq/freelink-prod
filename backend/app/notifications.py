from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import computed_field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import CurrentIdentity, Db, trusted_origin
from app.errors import api_error
from app.models import Notification
from app.schemas import ApiModel

router = APIRouter(prefix="/notifications", tags=["notifications"])
write = [Depends(trusted_origin)]
NotificationType = Literal["proposal", "submission", "message", "payment", "job", "support"]
LIST_LIMIT = 100


class NotificationResponse(ApiModel):
    id: UUID
    type: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None = None
    created_at: datetime

    @computed_field
    @property
    def read(self) -> bool:
        return self.read_at is not None


def notify(
    db: Session, user_id: UUID, kind: NotificationType, title: str, body: str, link: str | None = None,
) -> None:
    """Queue a notification in the caller's transaction so it is saved or lost with the event."""
    db.add(Notification(user_id=user_id, type=kind, title=title, body=body[:1000], link=link))


@router.get("", response_model=list[NotificationResponse])
def list_notifications(db: Db, identity: CurrentIdentity):
    stmt = (
        select(Notification).where(Notification.user_id == identity.user.id)
        .order_by(Notification.created_at.desc(), Notification.id).limit(LIST_LIMIT)
    )
    return list(db.scalars(stmt))


@router.patch("/read-all", status_code=204, dependencies=write)
def read_all_notifications(db: Db, identity: CurrentIdentity):
    db.execute(update(Notification).where(
        Notification.user_id == identity.user.id, Notification.read_at.is_(None),
    ).values(read_at=func.now()))
    db.commit()
    return Response(status_code=204)


@router.patch("/{notification_id}/read", response_model=NotificationResponse, dependencies=write)
def read_notification(notification_id: UUID, db: Db, identity: CurrentIdentity):
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != identity.user.id:
        raise api_error(404, "NOTIFICATION_NOT_FOUND", "ไม่พบการแจ้งเตือน")
    if notification.read_at is None:
        notification.read_at = func.now()
        db.commit()
        db.refresh(notification)
    return notification

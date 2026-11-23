from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import StringConstraints
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.auth import CurrentIdentity, Db, Identity, trusted_origin
from app.errors import api_error
from app.models import Message, MessageThread, Notification, Profile, Project, User
from app.notifications import notify
from app.profiles import display_name
from app.schemas import ApiModel

router = APIRouter(prefix="/messages", tags=["messages"])
write = [Depends(trusted_origin)]
Role = Literal["client", "freelancer"]


class MessageWrite(ApiModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class MessageResponse(ApiModel):
    id: UUID
    sender_id: UUID
    sender_role: Role
    text: str
    created_at: datetime


class ThreadParty(ApiModel):
    id: UUID
    name: str
    avatar_color: str | None
    title: str | None
    contact_name: str | None


class ThreadProject(ApiModel):
    id: UUID
    title: str


class ThreadResponse(ApiModel):
    id: UUID
    project: ThreadProject
    other: ThreadParty
    messages: list[MessageResponse]
    last_message: MessageResponse | None
    unread: bool
    created_at: datetime


class SendResponse(ApiModel):
    thread: ThreadResponse
    message: MessageResponse


def open_project_thread(db: Session, project: Project) -> None:
    """Give a newly hired project its conversation. Flushes so the project id exists."""
    db.flush()
    db.add(MessageThread(project_id=project.id, client_id=project.client_id, freelancer_id=project.freelancer_id))


def thread_link(thread_id: UUID) -> str:
    return f"/messages/{thread_id}"


def thread_views(db: Session, threads: list[MessageThread], me: Profile) -> list[ThreadResponse]:
    if not threads:
        return []
    ids = [thread.id for thread in threads]
    projects = {
        project_id: ThreadProject(id=project_id, title=title)
        for project_id, title in db.execute(select(Project.id, Project.title).where(
            Project.id.in_([thread.project_id for thread in threads])
        ))
    }
    others = {
        profile.id: ThreadParty(
            id=profile.id, name=display_name(profile, user), avatar_color=profile.avatar_color,
            title=profile.title, contact_name=profile.contact_name,
        )
        for profile, user in db.execute(
            select(Profile, User).join(User, User.id == Profile.user_id).where(Profile.id.in_(
                {thread.client_id for thread in threads} | {thread.freelancer_id for thread in threads}
            ))
        )
    }
    by_thread: dict[UUID, list[Message]] = {thread_id: [] for thread_id in ids}
    for message in db.scalars(
        select(Message).where(Message.thread_id.in_(ids)).order_by(Message.created_at, Message.id)
    ):
        by_thread[message.thread_id].append(message)

    views = []
    for thread in threads:
        is_client = thread.client_id == me.id
        read_at = thread.client_read_at if is_client else thread.freelancer_read_at
        messages = [
            MessageResponse(
                id=item.id, sender_id=item.sender_id, text=item.text, created_at=item.created_at,
                sender_role="client" if item.sender_id == thread.client_id else "freelancer",
            )
            for item in by_thread[thread.id]
        ]
        incoming = [item.created_at for item in messages if item.sender_id != me.id]
        views.append(ThreadResponse(
            id=thread.id, project=projects[thread.project_id],
            other=others[thread.freelancer_id if is_client else thread.client_id],
            messages=messages, last_message=messages[-1] if messages else None,
            unread=bool(incoming) and (read_at is None or max(incoming) > read_at),
            created_at=thread.created_at,
        ))
    return views


def my_threads_query(identity: Identity):
    return select(MessageThread).where(or_(
        MessageThread.client_id == identity.profile.id, MessageThread.freelancer_id == identity.profile.id,
    ))


def get_thread(db: Session, thread_id: UUID, identity: Identity) -> MessageThread:
    thread = db.get(MessageThread, thread_id)
    # Strangers get the same answer as a missing thread so ids cannot be probed.
    if thread is None or identity.profile.id not in (thread.client_id, thread.freelancer_id):
        raise api_error(404, "THREAD_NOT_FOUND", "ไม่พบบทสนทนา")
    return thread


def last_activity(view: ThreadResponse) -> datetime:
    return view.last_message.created_at if view.last_message else view.created_at


@router.get("/threads", response_model=list[ThreadResponse])
def list_threads(db: Db, identity: CurrentIdentity):
    threads = list(db.scalars(my_threads_query(identity)))
    return sorted(thread_views(db, threads, identity.profile), key=last_activity, reverse=True)


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
def read_thread(thread_id: UUID, db: Db, identity: CurrentIdentity):
    return thread_views(db, [get_thread(db, thread_id, identity)], identity.profile)[0]


@router.post("/threads/{thread_id}/messages", response_model=SendResponse, status_code=201, dependencies=write)
def send_message(thread_id: UUID, payload: MessageWrite, db: Db, identity: CurrentIdentity):
    thread = get_thread(db, thread_id, identity)
    is_client = thread.client_id == identity.profile.id
    recipient_id = thread.freelancer_id if is_client else thread.client_id
    db.add(Message(thread_id=thread.id, sender_id=identity.profile.id, text=payload.text))
    # One unread alert per conversation is enough; reading the thread clears it.
    link = thread_link(thread.id)
    recipient_user_id = db.scalar(select(Profile.user_id).where(Profile.id == recipient_id))
    already_alerted = db.scalar(select(Notification.id).where(
        Notification.user_id == recipient_user_id, Notification.type == "message",
        Notification.link == link, Notification.read_at.is_(None),
    ))
    if not already_alerted:
        notify(db, recipient_user_id, "message", "ข้อความใหม่",
               f"{display_name(identity.profile, identity.user)} ส่งข้อความถึงคุณ", link)
    db.commit()
    view = thread_views(db, [thread], identity.profile)[0]
    return SendResponse(thread=view, message=view.messages[-1])


@router.patch("/threads/{thread_id}/read", status_code=204, dependencies=write)
def mark_thread_read(thread_id: UUID, db: Db, identity: CurrentIdentity):
    thread = get_thread(db, thread_id, identity)
    column = "client_read_at" if thread.client_id == identity.profile.id else "freelancer_read_at"
    db.execute(update(MessageThread).where(MessageThread.id == thread.id).values({column: func.now()}))
    db.execute(update(Notification).where(
        Notification.user_id == identity.user.id, Notification.type == "message",
        Notification.link == thread_link(thread.id), Notification.read_at.is_(None),
    ).values(read_at=func.now()))
    db.commit()
    return Response(status_code=204)

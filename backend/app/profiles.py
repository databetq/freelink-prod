import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BeforeValidator, Field, StringConstraints, field_serializer, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.auth import CurrentIdentity, Db, Identity, OptionalIdentity, current_identity, trusted_origin
from app.errors import api_error
from app.models import FreelancerReview, Job, Profile, Project, User
from app.schemas import ApiModel, ClientCard, FreelancerCard, FreelancerReviewView, Label

router = APIRouter(tags=["profiles"])
write = [Depends(trusted_origin)]
DIRECTORY_LIMIT = 200

Availability = Literal["open", "limited", "unavailable"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Bio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
# Optional free text the person may clear again, so "" is a valid value.
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Website = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300, pattern=r"^(https?://\S+)?$")]
# Tailwind gradient classes such as "from-violet-500 to-indigo-600" picked by the UI.
ColorClasses = Annotated[str, StringConstraints(max_length=100, pattern=r"^[A-Za-z0-9 :/.\[\]#%-]+$")]


def empty_filter(value):
    return None if value == "" else value


class PortfolioItem(ApiModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    title: Name
    category: Label
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    accent: ColorClasses


class ProfilePatch(ApiModel):
    """PATCH body: send only the fields to change; a present field can never be null."""

    @model_validator(mode="after")
    def reject_null_fields(self):
        for key in self.model_fields_set:
            if getattr(self, key) is None:
                raise ValueError(f"{to_camel(key)} cannot be null")
        return self


class FreelancerPatch(ProfilePatch):
    name: Name | None = None
    title: Name | None = None
    location: Short | None = None
    hourly_rate: Annotated[Decimal, Field(gt=0, le=1_000_000, max_digits=10, decimal_places=2)] | None = None
    bio: Bio | None = None
    availability: Availability | None = None
    avatar_color: ColorClasses | None = None
    skills: list[Label] | None = Field(default=None, max_length=50)
    languages: list[Label] | None = Field(default=None, max_length=20)
    portfolio: list[PortfolioItem] | None = Field(default=None, max_length=50)


class ClientPatch(ProfilePatch):
    name: Name | None = None
    contact_name: Name | None = None
    title: Name | None = None
    industry: Short | None = None
    location: Short | None = None
    website: Website | None = None
    bio: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None
    avatar_color: ColorClasses | None = None


class FreelancerResponse(ApiModel):
    id: UUID
    name: str
    title: str | None
    location: str | None
    hourly_rate: Decimal | None
    bio: str | None
    availability: str
    avatar_color: str | None
    skills: list[str]
    languages: list[str]
    portfolio: list[PortfolioItem]
    rating: float = 0
    reviews_count: int = 0
    reviews: list[FreelancerReviewView] = Field(default_factory=list)
    completed_jobs: int
    success_rate: int | None
    member_since: datetime

    @field_serializer("hourly_rate")
    def serialize_rate(self, value: Decimal | None) -> float | None:
        return None if value is None else float(value)


class ClientResponse(ApiModel):
    id: UUID
    name: str
    contact_name: str | None
    title: str | None
    industry: str | None
    location: str | None
    website: str | None
    bio: str | None
    avatar_color: str | None
    member_since: datetime
    jobs_posted: int
    hire_rate: int
    rating: float = 0
    reviews: int = 0


def display_name(profile: Profile, user: User) -> str:
    return profile.display_name or user.name


def json_contains(column, term: str):
    # JSON columns are stored with ASCII escapes (Thai becomes \uXXXX), so escape the term the same way.
    return cast(column, String).icontains(json.dumps(term)[1:-1], autoescape=True)


def apply_changes(profile: Profile, changes: dict) -> None:
    for field, value in changes.items():
        setattr(profile, "display_name" if field == "name" else field, value)


# A profile shows up for other people once the fields a client needs to judge it are filled in.
listed = and_(Profile.title.is_not(None), Profile.bio.is_not(None), Profile.hourly_rate.is_not(None))


def project_outcomes(db: Session, freelancer_ids: list[UUID]) -> dict[UUID, tuple[int, int | None]]:
    """Per freelancer: (completed projects, success rate in percent or None before any project ended)."""
    outcomes: dict[UUID, dict[str, int]] = {}
    if freelancer_ids:
        counts = db.execute(
            select(Project.freelancer_id, Project.status, func.count())
            .where(Project.freelancer_id.in_(freelancer_ids), Project.status.in_(("completed", "cancelled")))
            .group_by(Project.freelancer_id, Project.status)
        )
        for freelancer_id, status, total in counts:
            outcomes.setdefault(freelancer_id, {})[status] = total
    summary = {}
    for freelancer_id in freelancer_ids:
        result = outcomes.get(freelancer_id, {})
        completed, finished = result.get("completed", 0), sum(result.values())
        summary[freelancer_id] = (completed, round(100 * completed / finished) if finished else None)
    return summary


def review_stats(db: Session, freelancer_ids: list[UUID]) -> dict[UUID, tuple[float, int]]:
    rows = db.execute(select(Project.freelancer_id, func.avg(FreelancerReview.rating), func.count())
                      .join(FreelancerReview, FreelancerReview.project_id == Project.id)
                      .where(Project.freelancer_id.in_(freelancer_ids)).group_by(Project.freelancer_id))
    return {freelancer_id: (round(float(avg), 1), count) for freelancer_id, avg, count in rows}


def freelancer_rows(db: Session, *conditions, limit: int | None = None) -> list[FreelancerResponse]:
    stmt = (
        select(Profile, User).join(User, User.id == Profile.user_id)
        .where(User.role == "freelancer", User.status == "active", *conditions)
        .order_by(User.created_at.desc(), Profile.id)
    )
    rows = db.execute(stmt.limit(limit) if limit else stmt).all()
    outcomes = project_outcomes(db, [profile.id for profile, _ in rows])
    reviews = review_stats(db, [profile.id for profile, _ in rows])
    views = []
    for profile, user in rows:
        completed, success_rate = outcomes[profile.id]
        rating, reviews_count = reviews.get(profile.id, (0, 0))
        views.append(FreelancerResponse(
            id=profile.id, name=display_name(profile, user), title=profile.title, location=profile.location,
            hourly_rate=profile.hourly_rate, bio=profile.bio, availability=profile.availability,
            avatar_color=profile.avatar_color, skills=profile.skills, languages=profile.languages,
            portfolio=profile.portfolio, completed_jobs=completed, success_rate=success_rate,
            member_since=user.created_at, rating=rating, reviews_count=reviews_count,
        ))
    return views


def freelancer_cards(db: Session, profile_ids) -> dict[UUID, FreelancerCard]:
    """Cards for the freelancers on a proposal or project, loaded in one pass.

    Unlike the directory, this does not require an active or listed profile: a freelancer who
    was suspended after applying must still show up with a name on the client's proposal list.
    """
    ids = list(set(profile_ids))
    if not ids:
        return {}
    rows = db.execute(select(Profile, User).join(User, User.id == Profile.user_id).where(Profile.id.in_(ids))).all()
    outcomes = project_outcomes(db, [profile.id for profile, _ in rows])
    reviews = review_stats(db, ids)
    return {
        profile.id: FreelancerCard(
            id=profile.id, name=display_name(profile, user), title=profile.title, avatar_color=profile.avatar_color,
            skills=profile.skills, completed_jobs=outcomes[profile.id][0], success_rate=outcomes[profile.id][1],
            rating=reviews.get(profile.id, (0, 0))[0], reviews_count=reviews.get(profile.id, (0, 0))[1],
        )
        for profile, user in rows
    }


def freelancer_not_found():
    return api_error(404, "FREELANCER_NOT_FOUND", "ไม่พบโปรไฟล์ฟรีแลนซ์")


def own_profile(identity: Identity | None, profile_id: UUID) -> bool:
    return identity is not None and identity.profile.id == profile_id


@router.get("/freelancers", response_model=list[FreelancerResponse])
def list_freelancers(
    db: Db,
    q: str = Query("", max_length=200),
    skill: str = Query("", max_length=100),
    availability: Annotated[Availability | None, BeforeValidator(empty_filter)] = None,
):
    conditions = [listed]
    if q.strip():
        term = q.strip()
        conditions.append(or_(
            func.coalesce(Profile.display_name, User.name).icontains(term, autoescape=True),
            Profile.title.icontains(term, autoescape=True),
            json_contains(Profile.skills, term),
        ))
    if skill.strip():
        conditions.append(json_contains(Profile.skills, skill.strip()))
    if availability:
        conditions.append(Profile.availability == availability)
    return freelancer_rows(db, *conditions, limit=DIRECTORY_LIMIT)


@router.get("/freelancers/{freelancer_id}", response_model=FreelancerResponse)
def read_freelancer(freelancer_id: UUID, db: Db, identity: OptionalIdentity):
    # Owners can always open their own profile; everyone else only sees finished, active ones.
    visibility = [Profile.id == freelancer_id]
    if not own_profile(identity, freelancer_id):
        visibility.append(listed)
    found = freelancer_rows(db, *visibility)
    if not found:
        raise freelancer_not_found()
    rows = db.execute(select(FreelancerReview, Project.client_id)
                      .join(Project, Project.id == FreelancerReview.project_id)
                      .where(Project.freelancer_id == freelancer_id)
                      .order_by(FreelancerReview.created_at.desc(), FreelancerReview.id)).all()
    clients = client_cards(db, {client_id for _, client_id in rows})
    view = found[0]
    view.reviews = [FreelancerReviewView.model_validate(review).model_copy(update={"client": clients.get(client_id)})
                    for review, client_id in rows]
    return view


@router.get("/freelancers/{freelancer_id}/reviews", response_model=list[FreelancerReviewView])
def read_freelancer_reviews(freelancer_id: UUID, db: Db, identity: OptionalIdentity):
    return read_freelancer(freelancer_id, db, identity).reviews


@router.patch("/freelancers/{freelancer_id}", response_model=FreelancerResponse, dependencies=write)
def edit_freelancer(freelancer_id: UUID, payload: FreelancerPatch, db: Db, identity: CurrentIdentity):
    if identity.profile.id != freelancer_id or identity.user.role != "freelancer":
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์แก้ไขโปรไฟล์นี้")
    apply_changes(identity.profile, payload.model_dump(exclude_unset=True))
    db.commit()
    return freelancer_rows(db, Profile.id == freelancer_id)[0]


def hire_percent(posted: int, hired: int) -> int:
    return round(100 * hired / posted) if posted else 0


def client_view(db: Session, profile: Profile, user: User) -> ClientResponse:
    posted = db.scalar(select(func.count(Job.id)).where(Job.client_id == profile.id, Job.status != "draft"))
    hired = db.scalar(select(func.count(Project.id)).where(Project.client_id == profile.id))
    return ClientResponse(
        id=profile.id, name=display_name(profile, user), contact_name=profile.contact_name,
        title=profile.title, industry=profile.industry, location=profile.location, website=profile.website,
        bio=profile.bio, avatar_color=profile.avatar_color, member_since=user.created_at,
        jobs_posted=posted, hire_rate=hire_percent(posted, hired),
    )


def client_cards(db: Session, profile_ids) -> dict[UUID, ClientCard]:
    """Cards for the clients on a job or project, loaded in one pass with the same counts as `client_view`.

    Only the name, avatar and track record are included: this feeds public job pages, while the
    company details stay behind `GET /clients/{id}`, which requires a login.
    """
    ids = list(set(profile_ids))
    if not ids:
        return {}
    rows = db.execute(select(Profile, User).join(User, User.id == Profile.user_id).where(Profile.id.in_(ids))).all()
    posted = dict(db.execute(
        select(Job.client_id, func.count()).where(Job.client_id.in_(ids), Job.status != "draft").group_by(Job.client_id)
    ).all())
    hired = dict(db.execute(
        select(Project.client_id, func.count()).where(Project.client_id.in_(ids)).group_by(Project.client_id)
    ).all())
    return {
        profile.id: ClientCard(
            id=profile.id, name=display_name(profile, user), avatar_color=profile.avatar_color,
            jobs_posted=posted.get(profile.id, 0),
            hire_rate=hire_percent(posted.get(profile.id, 0), hired.get(profile.id, 0)),
        )
        for profile, user in rows
    }


def client_profile(db: Session, client_id: UUID) -> tuple[Profile, User]:
    row = db.execute(
        select(Profile, User).join(User, User.id == Profile.user_id)
        .where(Profile.id == client_id, User.role == "client", User.status == "active")
    ).one_or_none()
    if row is None:
        raise api_error(404, "CLIENT_NOT_FOUND", "ไม่พบโปรไฟล์ลูกค้า")
    return row


@router.get("/clients/{client_id}", response_model=ClientResponse, dependencies=[Depends(current_identity)])
def read_client(client_id: UUID, db: Db):
    return client_view(db, *client_profile(db, client_id))


@router.patch("/clients/{client_id}", response_model=ClientResponse, dependencies=write)
def edit_client(client_id: UUID, payload: ClientPatch, db: Db, identity: CurrentIdentity):
    if identity.profile.id != client_id or identity.user.role != "client":
        raise api_error(403, "FORBIDDEN", "บัญชีนี้ไม่มีสิทธิ์แก้ไขโปรไฟล์นี้")
    apply_changes(identity.profile, payload.model_dump(exclude_unset=True))
    db.commit()
    return client_view(db, *client_profile(db, client_id))

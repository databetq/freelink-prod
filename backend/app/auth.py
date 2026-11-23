from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated, Literal, NamedTuple
from uuid import UUID

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from httpx import HTTPError
from joserfc.errors import JoseError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from app.config import get_settings
from app.db import get_db, get_engine
from app.errors import api_error
from app.models import AdminUserNotice, LoginSession, Profile, User
from app.schemas import ApiModel

COOKIE_NAME = "freelink_session"
SESSION_LIFETIME = timedelta(days=7)
router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()
settings = get_settings()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret.get_secret_value(),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
)

Db = Annotated[Session, Depends(get_db)]


class Identity(NamedTuple):
    user: User
    profile: Profile


class UserResponse(BaseModel):
    id: UUID
    profileId: UUID
    name: str
    email: str
    role: str


class AccountWarning(ApiModel):
    id: UUID
    reason: str
    created_at: datetime


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def optional_identity(request: Request, db: Db) -> Identity | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = db.execute(
            select(User, Profile)
            .join(Profile, Profile.user_id == User.id)
            .join(LoginSession, LoginSession.user_id == User.id)
            .where(
                LoginSession.token_hash == hash_token(token),
                LoginSession.expires_at > datetime.now(timezone.utc),
                User.status == "active",
            )
        ).one_or_none()
        if row:
            return Identity(*row)
    return None


OptionalIdentity = Annotated[Identity | None, Depends(optional_identity)]


def current_identity(identity: OptionalIdentity) -> Identity:
    if identity:
        return identity
    raise api_error(401, "LOGIN_REQUIRED", "กรุณาเข้าสู่ระบบ")


CurrentIdentity = Annotated[Identity, Depends(current_identity)]


def require_admin(identity: CurrentIdentity) -> Identity:
    if identity.user.role != "admin":
        raise api_error(403, "ADMIN_REQUIRED", "ต้องใช้บัญชีแอดมิน")
    return identity


AdminIdentity = Annotated[Identity, Depends(require_admin)]


def trusted_origin(request: Request) -> None:
    if request.headers.get("origin") != settings.frontend_origin:
        raise api_error(403, "INVALID_ORIGIN", "คำขอมาจากเว็บไซต์ที่ไม่ได้รับอนุญาต")


def require_oauth() -> None:
    if not (
        settings.google_client_id and settings.google_client_secret.get_secret_value()
        and len(settings.session_secret.get_secret_value()) >= 32
    ):
        raise api_error(503, "OAUTH_NOT_CONFIGURED", "ยังไม่ได้ตั้งค่า Google Login")


@router.get("/google")
async def google_login(request: Request, role: Literal["client", "freelancer"] | None = None):
    require_oauth()
    state = token_urlsafe(32)
    request.session.pop("google_signup", None)
    try:
        response = await oauth.google.authorize_redirect(request, settings.google_redirect_uri, state=state)
    except HTTPError as exc:
        raise api_error(502, "GOOGLE_UNAVAILABLE", "ติดต่อ Google ไม่สำเร็จ") from exc
    if role:
        request.session["google_signup"] = {"state": state, "role": role}
    return response


def create_login(db: Session, subject: str, email: str, name: str, role: str | None) -> str:
    if role is None:
        user = db.scalar(select(User).where(User.google_subject == subject).with_for_update())
        if user is None:
            raise api_error(404, "GOOGLE_ACCOUNT_NOT_FOUND", "ยังไม่มีบัญชี Freelink")
        if user.status != "active":
            raise api_error(403, "ACCOUNT_SUSPENDED", "บัญชีนี้ถูกระงับ")
        user.email = email
        user.name = name
        return create_session(db, user.id)

    upsert = insert(User).values(google_subject=subject, email=email, name=name, role=role)
    user_id = db.execute(
        upsert.on_conflict_do_update(
            index_elements=[User.google_subject],
            set_={"email": email, "name": name},
            where=User.status == "active",
        ).returning(User.id)
    ).scalar_one_or_none()
    if user_id is None:
        raise api_error(403, "ACCOUNT_SUSPENDED", "บัญชีนี้ถูกระงับ")
    db.execute(insert(Profile).values(user_id=user_id).on_conflict_do_nothing(index_elements=[Profile.user_id]))
    return create_session(db, user_id)


def create_session(db: Session, user_id: UUID, lifetime: timedelta = SESSION_LIFETIME) -> str:
    token = token_urlsafe(32)
    db.add(LoginSession(
        token_hash=hash_token(token),
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + lifetime,
    ))
    db.commit()
    return token


@router.get("/google/callback")
async def google_callback(request: Request):
    require_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except (OAuthError, JoseError) as exc:
        raise api_error(400, "GOOGLE_LOGIN_FAILED", "ยืนยันตัวตนกับ Google ไม่สำเร็จ") from exc
    except HTTPError as exc:
        raise api_error(502, "GOOGLE_UNAVAILABLE", "ติดต่อ Google ไม่สำเร็จ") from exc
    info = token.get("userinfo") or {}
    signup = request.session.pop("google_signup", {})
    role = signup.get("role") if signup.get("state") == request.query_params.get("state") else None
    if role not in (None, "client", "freelancer") or not (
        info.get("sub") and info.get("email") and info.get("email_verified") is True
    ):
        raise api_error(400, "INVALID_GOOGLE_IDENTITY", "ข้อมูลยืนยันตัวตนไม่ครบ")

    def save_login() -> str:
        with Session(get_engine()) as db:
            return create_login(db, info["sub"], info["email"], (info.get("name") or info["email"])[:200], role)

    try:
        session_token = await run_in_threadpool(save_login)
    except HTTPException as exc:
        if not isinstance(exc.detail, dict):
            raise
        error = {
            "GOOGLE_ACCOUNT_NOT_FOUND": "account-not-found",
            "ACCOUNT_SUSPENDED": "account-suspended",
        }.get(exc.detail.get("code"))
        if error is None:
            raise
        return RedirectResponse(
            f"{settings.frontend_origin.rstrip('/')}/login?error={error}", status_code=303,
        )
    response = RedirectResponse(settings.frontend_origin, status_code=303)
    set_session_cookie(response, session_token)
    return response


def set_session_cookie(response: Response, token: str, lifetime: timedelta = SESSION_LIFETIME) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=int(lifetime.total_seconds()),
        httponly=True, secure=settings.session_cookie_secure, samesite="lax",
    )


@router.get("/me", response_model=UserResponse)
def me(identity: CurrentIdentity):
    return UserResponse(
        id=identity.user.id, profileId=identity.profile.id, role=identity.user.role,
        name=identity.profile.display_name or identity.user.name, email=identity.user.email,
    )


@router.get("/warnings", response_model=list[AccountWarning])
def account_warnings(db: Db, identity: CurrentIdentity):
    return list(db.scalars(select(AdminUserNotice).where(
        AdminUserNotice.target_id == identity.user.id,
        AdminUserNotice.kind == "warning",
    ).order_by(AdminUserNotice.created_at.desc(), AdminUserNotice.id)))


@router.post("/logout", status_code=204, dependencies=[Depends(trusted_origin)])
def logout(request: Request, db: Db):
    response = Response(status_code=204)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        login = db.get(LoginSession, hash_token(token))
        if login:
            db.delete(login)
            db.commit()
    response.delete_cookie(COOKIE_NAME, secure=settings.session_cookie_secure, httponly=True)
    return response

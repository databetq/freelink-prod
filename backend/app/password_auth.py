from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, EmailStr, Field, SecretStr, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.auth import Db, create_session, set_session_cookie, trusted_origin
from app.errors import api_error
from app.models import Profile, User, UserCredential
from app.passwords import authenticate_credential, password_hash_slot, password_hasher

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(trusted_origin)])


class PasswordLogin(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class PasswordRegistration(PasswordLogin):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    role: Literal["client", "freelancer"]
    password: SecretStr = Field(min_length=8, max_length=128)


@router.post("/register", status_code=204)
def register_account(payload: PasswordRegistration, response: Response, db: Db):
    user = provision_password_account(db, payload)
    set_session_cookie(response, create_session(db, user.id))


def provision_password_account(db: Db, payload: PasswordRegistration) -> User:
    email = payload.email.lower()
    with password_hash_slot():
        password_hash = password_hasher.hash(payload.password.get_secret_value())
    google_user = db.scalar(select(User.id).where(
        User.google_subject.is_not(None), func.lower(User.email) == email,
    ).limit(1))
    if google_user:
        raise api_error(409, "EMAIL_UNAVAILABLE", "อีเมลนี้ใช้สมัครไม่ได้ กรุณาลองเข้าสู่ระบบด้วยวิธีเดิม")

    user = User(name=payload.name, email=email, role=payload.role)
    db.add(user)
    db.flush()
    registered = db.scalar(
        insert(UserCredential).values(user_id=user.id, email=email, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[UserCredential.email])
        .returning(UserCredential.user_id)
    )
    if registered is None:
        raise api_error(409, "EMAIL_UNAVAILABLE", "อีเมลนี้ใช้สมัครไม่ได้ กรุณาลองเข้าสู่ระบบด้วยวิธีเดิม")
    db.add(Profile(user_id=user.id))
    return user


@router.post("/login", status_code=204)
def login_with_password(payload: PasswordLogin, response: Response, db: Db):
    with password_hash_slot():
        token = authenticate_password(db, payload.email.lower(), payload.password.get_secret_value())
    set_session_cookie(response, token)


def authenticate_password(db: Db, email: str, password: str) -> str:
    credential = db.scalar(
        select(UserCredential).join(User).where(
            UserCredential.email == email,
            User.role.in_(("client", "freelancer")),
            User.status == "active",
        ).with_for_update(of=(User, UserCredential))
    )
    if not authenticate_credential(db, credential, password):
        raise api_error(401, "PASSWORD_LOGIN_FAILED", "เข้าสู่ระบบไม่ได้ ตรวจสอบอีเมลและรหัสผ่านแล้วลองอีกครั้ง")
    return create_session(db, credential.user_id)

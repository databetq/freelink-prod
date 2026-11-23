from datetime import timedelta
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from app.admin_accounts import normalize_username
from app.auth import Db, create_session, set_session_cookie, trusted_origin
from app.errors import api_error
from app.models import AdminCredential, User
from app.passwords import authenticate_credential, password_hash_slot

router = APIRouter(prefix="/auth/admin", tags=["auth"])
ADMIN_LIFETIME = timedelta(hours=8)


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64, repr=False)
    password: SecretStr = Field(min_length=1, max_length=128)


@router.post("/login", status_code=204, dependencies=[Depends(trusted_origin)])
def admin_login(payload: AdminLogin, response: Response, db: Db):
    with password_hash_slot():
        token = authenticate_admin(db, payload.username, payload.password.get_secret_value())
    set_session_cookie(response, token, ADMIN_LIFETIME)


def authenticate_admin(db: Db, username_input: str, password: str) -> str:
    try:
        username = normalize_username(username_input)
    except ValueError:
        username = ""

    credential = db.scalar(
        select(AdminCredential).join(User).where(
            AdminCredential.username == username, User.role == "admin", User.status == "active",
        ).with_for_update(of=AdminCredential)
    )
    if not authenticate_credential(db, credential, password):
        raise api_error(401, "ADMIN_LOGIN_FAILED", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง หรือบัญชีถูกล็อกชั่วคราว")

    return create_session(db, credential.user_id, ADMIN_LIFETIME)

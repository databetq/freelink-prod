from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy.orm import Session

from app.errors import api_error
from app.models import AdminCredential, UserCredential

password_hasher = PasswordHasher()
dummy_hash = password_hasher.hash(token_urlsafe(32))
hash_slots = BoundedSemaphore(4)
MAX_FAILURES = 5
LOCK_PERIOD = timedelta(minutes=10)


@contextmanager
def password_hash_slot():
    if not hash_slots.acquire(blocking=False):
        raise api_error(429, "PASSWORD_AUTH_BUSY", "มีคำขอจำนวนมาก กรุณาลองใหม่")
    try:
        yield
    finally:
        hash_slots.release()


def authenticate_credential(
    db: Session, credential: AdminCredential | UserCredential | None, password: str
) -> bool:
    now = datetime.now(timezone.utc)
    locked = bool(credential and credential.locked_until and credential.locked_until > now)
    password_hash = credential.password_hash if credential and not locked else dummy_hash
    try:
        verified = password_hasher.verify(password_hash, password)
    except VerificationError:
        verified = False
    if credential is None or locked:
        return False
    if verified:
        credential.failed_attempts = 0
        credential.locked_until = None
        if password_hasher.check_needs_rehash(credential.password_hash):
            credential.password_hash = password_hasher.hash(password)
        return True
    if credential.locked_until:
        credential.locked_until = None
        credential.failed_attempts = 0
    credential.failed_attempts += 1
    if credential.failed_attempts >= MAX_FAILURES:
        credential.locked_until = now + LOCK_PERIOD
    db.commit()
    return False

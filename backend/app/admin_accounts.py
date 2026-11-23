import argparse
import re
import sys
from getpass import GetPassWarning, getpass
from warnings import catch_warnings, simplefilter

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import AdminCredential, Profile, User
from app.passwords import password_hasher

USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")


def normalize_username(username: str) -> str:
    result = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(result):
        raise ValueError("Username must have 3-64 letters, numbers, dots, underscores or hyphens.")
    return result


def provision_admin(
    db: Session, username: str, password: str, name: str, email: str, *, add: bool | None = False
) -> None:
    username = normalize_username(username)
    if not 6 <= len(password) <= 128:
        raise ValueError("Password must have 6-128 characters.")
    if not name.strip() or len(name) > 200 or "@" not in email or len(email) > 320:
        raise ValueError("Provide a valid display name and email.")
    password_hash = password_hasher.hash(password)
    db.execute(text("SELECT pg_advisory_xact_lock(811719301)"))
    existing_admin = db.scalar(select(User.id).where(User.role == "admin").limit(1))
    if existing_admin and add is False:
        raise ValueError("An admin already exists. Use npm run add:admin to add another.")
    if not existing_admin and add is True:
        raise ValueError("Create the first admin with npm run init:admin.")
    if db.scalar(select(AdminCredential.user_id).where(AdminCredential.username == username)):
        raise ValueError("That admin username is already in use.")
    user = User(name=name.strip(), email=email.strip(), role="admin")
    db.add(user)
    db.flush()
    db.add_all([Profile(user_id=user.id), AdminCredential(
        user_id=user.id, username=username, password_hash=password_hash,
    )])
    db.commit()


def prompt_password(prompt: str) -> str:
    with catch_warnings():
        simplefilter("error", GetPassWarning)
        password = getpass(prompt)
        if password != getpass("Repeat password: "):
            raise ValueError("Passwords do not match.")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a local Freelink admin account.")
    parser.add_argument("--add", action="store_true", help="Add an admin after bootstrap.")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error("Run in an interactive terminal so the password can be entered securely.")
    try:
        username = normalize_username(input("Admin username: "))
        name = input("Display name: ")
        email = input("Contact email: ")
        password = prompt_password("Admin password (15-128 characters): ")
        with Session(get_engine()) as db:
            provision_admin(db, username, password, name, email, add=args.add)
    except (EOFError, KeyboardInterrupt):
        print("\nAdmin creation cancelled.", file=sys.stderr)
        return 1
    except GetPassWarning:
        print("The terminal cannot hide password input. Open PowerShell or a terminal and retry.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Created admin {username}. Sign in at /admin/login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import sys
from getpass import GetPassWarning

from argon2.exceptions import VerificationError
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import admin_accounts
from app.db import get_engine
from app.models import AdminCredential, User, UserCredential
from app.passwords import password_hasher

ROLES = ("client", "freelancer", "admin")
DEMO_PASSWORD = "FreelinkDemo123"
DEMO_ACCOUNTS = (
    ("client", "/login", "demo-client@example.net"),
    ("freelancer", "/login", "demo-freelancer@example.net"),
    ("admin", "/admin/login", "demo-admin"),
)


def create_demo_accounts() -> None:
    from app.password_auth import PasswordRegistration, provision_password_account

    with Session(get_engine()) as db:
        db.execute(text("SELECT pg_advisory_xact_lock(811719302)"))
        for role, _, login in DEMO_ACCOUNTS:
            credential = AdminCredential if role == "admin" else UserCredential
            login_field = AdminCredential.username if role == "admin" else UserCredential.email
            existing = db.execute(
                select(User, credential.password_hash).join(credential).where(login_field == login)
            ).one_or_none()
            if existing is not None:
                user, password_hash = existing
                try:
                    password_matches = password_hasher.verify(password_hash, DEMO_PASSWORD)
                except VerificationError:
                    password_matches = False
                if user.role != role or user.status != "active" or not password_matches:
                    raise ValueError(f"Existing account {login} does not match the demo credentials.")
                continue

            name = f"Demo {role.title()}"
            if role == "admin":
                # Admin provisioning commits all the accounts staged in this session.
                admin_accounts.provision_admin(db, login, DEMO_PASSWORD, name, f"{login}@example.net", add=None)
            else:
                registration = PasswordRegistration(name=name, email=login, role=role, password=DEMO_PASSWORD)
                provision_password_account(db, registration)
        db.commit()

    print(f"{'Role':<12} {'Login page':<14} {'Email or username':<29} Password")
    for role, path, login in DEMO_ACCOUNTS:
        print(f"{role:<12} {path:<14} {login:<29} {DEMO_PASSWORD}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Freelink account in the configured database.")
    parser.add_argument("role", nargs="?", choices=ROLES, help="Prompt for the role if omitted.")
    parser.add_argument("--add", action="store_true", help="Add an admin when one already exists.")
    parser.add_argument("--demo", action="store_true", help="Set up three demo accounts and print their credentials.")
    args = parser.parse_args()
    if args.demo and (args.role or args.add):
        parser.error("--demo creates all roles and takes no role or --add.")
    if not args.demo and not sys.stdin.isatty():
        parser.error("Run in an interactive terminal so the password can be entered securely.")

    try:
        if args.demo:
            create_demo_accounts()
            return 0

        role = args.role or input("Role [client/freelancer/admin]: ").strip().lower()
        if role not in ROLES:
            parser.error("Choose client, freelancer, or admin.")
        if role == "admin":
            return admin_accounts.main(["--add"] if args.add else [])
        if args.add:
            parser.error("--add applies to admin accounts only.")

        from app.password_auth import PasswordRegistration, provision_password_account

        name = input("Display name: ")
        email = input("Email: ").strip()
        password = admin_accounts.prompt_password("Password (8-128 characters): ")
        registration = PasswordRegistration(name=name, email=email, role=role, password=password)
        with Session(get_engine()) as db, db.begin():
            provision_password_account(db, registration)
    except (EOFError, KeyboardInterrupt):
        print("\nAccount creation cancelled.", file=sys.stderr)
        return 1
    except GetPassWarning:
        print("The terminal cannot hide password input. Open PowerShell or a terminal and retry.", file=sys.stderr)
        return 1
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            field = ".".join(map(str, error["loc"]))
            print(f"{field}: {error['msg']}", file=sys.stderr)
        return 1
    except HTTPException as exc:
        print(exc.detail["message"], file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Database operation failed. Check DATABASE_URL, PostgreSQL, and Alembic migrations.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Created {role} account {registration.email.lower()}. Sign in at /login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import asyncio
import json
from base64 import b64encode
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_abi import encode
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import auth
from app.admin_accounts import provision_admin
from app.config import get_settings
from app.db import get_db
from app.escrow_chain import FUNDED, REFUNDED, RELEASED, EscrowChain, hex_hash
from app.escrow_worker import sync_once
from app.main import app
from app.marketplace import platform_today
from app.models import (
    AdminCredential, AdminUserStatusEvent, EscrowAgreement, EscrowTransaction, Job, LoginSession, Profile, Project,
    SupportProjectAccess, User, UserCredential, WalletChallenge, WalletLink,
)


class MarketplaceTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.database = "freelink_test_" + uuid4().hex[:12]
        base = make_url(get_settings().database_url)
        self.admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        self.addCleanup(self.admin.dispose)
        with self.admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{self.database}"'))
        self.addCleanup(self.drop_database)
        self.engine = create_engine(base.set(database=self.database))
        self.addCleanup(self.engine.dispose)
        config = Config("alembic.ini")
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        app.dependency_overrides[get_db] = self.database_session
        self.addCleanup(app.dependency_overrides.clear)

    def drop_database(self):
        with self.admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{self.database}"'))

    def database_session(self):
        with Session(self.engine) as db:
            yield db

    async def test_wallet_link_requires_ownership_and_single_use_challenge(self):
        owner_wallet = Account.create()
        other_wallet = Account.create()
        with Session(self.engine) as db:
            owner_token = auth.create_login(db, "wallet-owner", "client@example.net", "Client", "client")
            other_token = auth.create_login(db, "wallet-other", "freelancer@example.net", "Freelancer", "freelancer")
            owner_id = db.scalar(select(User.id).where(User.google_subject == "wallet-owner"))
        settings = get_settings()
        origin = {"Origin": settings.frontend_origin}
        owner = {**origin, "Cookie": f"{auth.COOKIE_NAME}={owner_token}"}
        other = {**origin, "Cookie": f"{auth.COOKIE_NAME}={other_token}"}
        challenge_path = "/wallet/challenges"
        verify_path = "/wallet/verifications"

        def proof(challenge, signer):
            signature = signer.sign_message(encode_defunct(text=challenge["message"])).signature
            return {"challengeId": challenge["challengeId"], "signature": "0x" + bytes(signature).hex()}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            self.assertEqual((await http.get("/wallet/link")).status_code, 401)
            self.assertIsNone((await http.get("/wallet/link", headers=owner)).json())
            wallet = {"address": owner_wallet.address, "chainId": settings.escrow_chain_id}
            wrong_chain = await http.post(challenge_path, headers=owner,
                json={**wallet, "chainId": settings.escrow_chain_id + 1})
            self.assertEqual(wrong_chain.json()["code"], "WALLET_WRONG_CHAIN")

            async def new_challenge(headers, address=owner_wallet.address):
                response = await http.post(challenge_path, headers=headers, json={**wallet, "address": address})
                self.assertEqual(response.status_code, 201, response.text)
                self.assertIn(f"Origin: {settings.frontend_origin}", response.json()["message"])
                return response.json()

            expired = await new_challenge(owner)
            with Session(self.engine) as db:
                db.get(WalletChallenge, owner_id).expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
                db.commit()
            response = await http.post(verify_path, headers=owner, json=proof(expired, owner_wallet))
            self.assertEqual(response.json()["code"], "WALLET_CHALLENGE_INVALID")

            challenge = await new_challenge(owner)
            valid = proof(challenge, owner_wallet)
            bad_signature = await http.post(verify_path, headers=owner, json=proof(challenge, other_wallet))
            self.assertEqual(bad_signature.json()["code"], "WALLET_SIGNATURE_INVALID")
            malformed = await http.post(verify_path, headers=owner, json={**valid, "signature": "0x" + "00" * 65})
            self.assertEqual(malformed.json()["code"], "WALLET_SIGNATURE_INVALID")
            wrong_user = await http.post(verify_path, headers=other, json=valid)
            self.assertEqual(wrong_user.status_code, 409)
            verified, duplicate = sorted(await asyncio.gather(
                http.post(verify_path, headers=owner, json=valid),
                http.post(verify_path, headers=owner, json=valid),
            ), key=lambda response: response.status_code)
            self.assertEqual((verified.status_code, duplicate.status_code), (200, 409))
            self.assertEqual(verified.json()["address"], owner_wallet.address.lower())
            self.assertEqual((await http.get("/wallet/link", headers=owner)).json(), verified.json())
            self.assertIsNone((await http.get("/wallet/link", headers=other)).json())

            duplicate_link = await new_challenge(other)
            conflict = await http.post(verify_path, headers=other, json=proof(duplicate_link, owner_wallet))
            self.assertEqual(conflict.json()["code"], "WALLET_ALREADY_LINKED")
            replacement = await new_challenge(owner, other_wallet.address)
            replaced = await http.post(verify_path, headers=owner, json=proof(replacement, other_wallet))
            self.assertEqual(replaced.status_code, 200, replaced.text)
            self.assertEqual(replaced.json()["address"], other_wallet.address.lower())

    async def test_google_sign_in_uses_saved_role(self):
        with Session(self.engine) as db:
            with self.assertRaises(HTTPException) as missing:
                auth.create_login(db, "unknown-google", "unknown@example.test", "Unknown", None)
            self.assertEqual(missing.exception.detail["code"], "GOOGLE_ACCOUNT_NOT_FOUND")
            self.assertIsNone(db.scalar(select(User).where(User.google_subject == "unknown-google")))
            auth.create_login(db, "known-google", "known@example.test", "Known", "freelancer")
            auth.create_login(db, "known-google", "known@example.test", "Known", "client")
            token = auth.create_login(db, "known-google", "known@example.test", "Updated name", None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            response = await http.get("/auth/me", headers={"Cookie": f"{auth.COOKIE_NAME}={token}"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["role"], "freelancer")
            self.assertEqual(response.json()["name"], "Updated name")

    async def test_password_registration_and_sign_in(self):
        email = "Local.Account@example.net"
        password = uuid4().hex[:8]
        registration = {"name": "Local Account", "email": email, "role": "client", "password": password}
        credentials = {"email": email, "password": password}
        origin = {"Origin": get_settings().frontend_origin}
        with Session(self.engine) as db:
            auth.create_login(db, "known-google", "google@example.net", "Google", "freelancer")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            self.assertEqual((await http.post("/auth/register", json=registration)).status_code, 403)
            self.assertEqual((await http.post("/auth/register", headers=origin,
                json={**registration, "password": password[:7]})).status_code, 422)
            self.assertEqual((await http.post("/auth/register", headers=origin,
                json={**registration, "role": "admin"})).status_code, 422)
            self.assertEqual((await http.post("/auth/register", headers=origin,
                json={**registration, "email": "GOOGLE@example.net"})).status_code, 409)
            response = await http.post("/auth/register", headers=origin, json=registration)
            self.assertEqual(response.status_code, 204, response.text)
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            me = (await http.get("/auth/me")).json()
            self.assertEqual((me["role"], me["email"]), ("client", email.lower()))
            self.assertEqual((await http.post("/auth/register", headers=origin,
                json={**registration, "email": email.lower()})).status_code, 409)
            self.assertEqual((await http.post("/auth/logout", headers=origin)).status_code, 204)
            self.assertEqual((await http.get("/auth/me")).status_code, 401)
            self.assertEqual((await http.post("/auth/login", headers=origin,
                json={**credentials, "email": "google@example.net"})).status_code, 401)
            result = await http.post("/auth/login", headers=origin, json={**credentials, "role": "admin"})
            self.assertEqual(result.status_code, 204, result.text)
            self.assertEqual((await http.get("/auth/me")).json()["role"], "client")
            self.assertEqual((await http.post("/auth/logout", headers=origin)).status_code, 204)
            for _ in range(5):
                attempt = await http.post("/auth/login", headers=origin, json={**credentials, "password": "wrong"})
                self.assertEqual(attempt.status_code, 401)
            self.assertEqual((await http.post("/auth/login", headers=origin, json=credentials)).status_code, 401)
            with Session(self.engine) as db:
                stored = db.scalar(select(UserCredential).where(UserCredential.email == email.lower()))
                self.assertTrue(stored.password_hash.startswith("$argon2id$"))
                self.assertNotIn(password, stored.password_hash)
                stored.locked_until = None
                user = db.get(User, stored.user_id)
                self.assertIsNone(user.google_subject)
                user.status = "suspended"
                db.commit()
                self.assertEqual(len(db.scalars(select(User).where(User.email == email.lower())).all()), 1)
            self.assertEqual((await http.post("/auth/login", headers=origin, json=credentials)).status_code, 401)

    async def test_local_admin(self):
        password = f"test-{uuid4().hex}"
        with Session(self.engine) as db:
            auth.create_login(db, "existing-google-user", "admin@example.test", "Client", "client")
            with self.assertRaisesRegex(ValueError, "first admin"):
                provision_admin(db, "backup", password, "Backup", "backup@example.test", add=True)
            db.rollback()
            provision_admin(db, "Admin.One", password, "Administrator", "admin@example.test")
            with self.assertRaisesRegex(ValueError, "already exists"):
                provision_admin(db, "backup", password, "Backup", "backup@example.test")
            db.rollback()
            provision_admin(db, "backup", password, "Backup", "backup@example.test", add=True)
            with self.assertRaisesRegex(ValueError, "already in use"):
                provision_admin(db, "ADMIN.ONE", password, "Duplicate", "duplicate@example.test", add=True)
            db.rollback()
            credentials = db.scalar(select(AdminCredential).where(AdminCredential.username == "admin.one"))
            self.assertTrue(credentials.password_hash.startswith("$argon2id$"))
            self.assertNotIn(password, credentials.password_hash)
            google_user = db.scalar(select(User).where(User.google_subject == "existing-google-user"))
            self.assertEqual(google_user.role, "client")

        headers = {"Origin": get_settings().frontend_origin}
        admin_payload = {"username": "ADMIN.ONE", "password": password}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            endpoint = "/auth/admin/login"
            self.assertEqual((await http.post(endpoint, json=admin_payload)).status_code, 403)
            self.assertEqual((await http.get("/auth/google?role=admin")).status_code, 422)
            response = await http.post(endpoint, json=admin_payload, headers=headers)
            self.assertEqual(response.status_code, 204, response.text)
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("Max-Age=28800", response.headers["set-cookie"])
            self.assertEqual((await http.get("/auth/me")).json()["role"], "admin")
            self.assertEqual((await http.post("/auth/logout", headers=headers)).status_code, 204)
            self.assertEqual((await http.get("/auth/me")).status_code, 401)
            for _ in range(5):
                invalid = {"username": "admin.one", "password": "wrong-password"}
                self.assertEqual((await http.post(endpoint, json=invalid, headers=headers)).status_code, 401)
            self.assertEqual((await http.post(endpoint, json=admin_payload, headers=headers)).status_code, 401)

    async def test_hire_and_permissions(self):
        with Session(self.engine) as db:
            client, first, second, stranger = [
                auth.create_login(db, name, f"{name}@example.test", name, role)
                for name, role in (
                    ("client", "client"), ("first", "freelancer"),
                    ("second", "freelancer"), ("stranger", "client"),
                )
            ]
        origin = {"Origin": get_settings().frontend_origin}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            def session_headers(token):
                return {**origin, "Cookie": f"{auth.COOKIE_NAME}={token}"}

            async def request(method, path, token, expected, **kwargs):
                headers = {**session_headers(token), **kwargs.pop("headers", {})}
                response = await http.request(method, path, headers=headers, **kwargs)
                self.assertEqual(response.status_code, expected, response.text)
                self.assertTrue(response.headers.get("X-Request-ID"))
                return response.json() if response.content else None

            self.assertEqual((await http.get("/auth/me")).status_code, 401)
            me = await request("GET", "/auth/me", client, 200)
            job_data = {
                "title": "Test job", "description": "Test", "category": "Development",
                "skills": ["Python"], "budgetMin": 1000, "budgetMax": 4000,
                "budgetType": "fixed", "duration": "1 week", "experience": "intermediate",
                "status": "draft", "clientId": str(uuid4()),
                "deadline": f"{platform_today() + timedelta(days=30)}T00:00:00.000Z",
            }
            await request("POST", "/jobs", client, 403, json=job_data, headers={"Origin": "https://other.test"})
            await request("POST", "/jobs", first, 403, json=job_data)
            job = await request("POST", "/jobs", client, 201, json=job_data)
            self.assertEqual(job["clientId"], me["profileId"])
            self.assertEqual(job["deadline"], str(platform_today() + timedelta(days=30)))
            path = f"/jobs/{job['id']}"
            self.assertEqual((await http.get(path)).status_code, 404)
            await request("GET", path, client, 200)
            await request("PATCH", path, stranger, 403, json={"status": "open"})
            await request("PATCH", path, client, 422, json={"budgetMax": 100})
            await request("PATCH", path, client, 200, json={"status": "open"})
            results = await http.get("/jobs?budgetType=&minBudget=&maxBudget=&q=Python")
            self.assertEqual(results.status_code, 200, results.text)
            self.assertEqual(len(results.json()), 1)
            self.assertEqual((await http.get("/jobs?minBudget=-1")).status_code, 422)

            payload = {"bidAmount": 2000, "deliveryDays": 7, "coverLetter": "Offer", "attachments": ["sample.pdf"]}
            proposals = [
                await request("POST", path + "/proposals", token, 201, json=payload)
                for token in (first, second)
            ]
            self.assertEqual(proposals[0]["attachments"], ["sample.pdf"])
            await request("POST", path + "/proposals", first, 409, json=payload)
            await request("GET", path + "/proposals", stranger, 403)
            self.assertEqual(len(await request("GET", path + "/proposals", client, 200)), 2)
            hire_paths = [f"/proposals/{proposal['id']}/hire" for proposal in proposals]
            replies = await asyncio.gather(*(
                http.post(path, headers=session_headers(client)) for path in hire_paths
            ))
            self.assertEqual(sorted(reply.status_code for reply in replies), [200, 409])
            winner = next(index for index, reply in enumerate(replies) if reply.status_code == 200)
            project = replies[winner].json()["project"]
            retry = await request("POST", hire_paths[winner], client, 200)
            self.assertEqual(project["id"], retry["project"]["id"])
            self.assertEqual(project["escrowStatus"], "unfunded")
            self.assertTrue(project["dueDate"])
            project_path = f"/projects/{project['id']}"
            await request("GET", project_path, (first, second)[winner], 200)
            await request("GET", project_path, stranger, 403)
            await request("DELETE", path, client, 409)
            await request("POST", "/auth/logout", client, 204)
            await request("GET", "/auth/me", client, 401)

    async def test_work_delivery_review_and_project_support(self):
        with Session(self.engine) as db:
            client, freelancer, stranger, admin = [
                auth.create_login(db, name, f"{name}@example.test", name, role)
                for name, role in (("client", "client"), ("freelancer", "freelancer"), ("stranger", "client"), ("admin", "admin"))
            ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            async def call(method, path, token, expected, **kwargs):
                response = await http.request(method, path, headers={
                    "Origin": get_settings().frontend_origin, "Cookie": f"{auth.COOKIE_NAME}={token}",
                }, **kwargs)
                self.assertEqual(response.status_code, expected, response.text)
                return response

            job = (await call("POST", "/jobs", client, 201, json={
                "title": "Project delivery", "description": "Deliver a PDF", "category": "design",
                "budgetMin": 1000, "budgetMax": 4000, "budgetType": "fixed", "duration": "1 week",
                "experience": "intermediate", "status": "open",
            })).json()
            proposal = (await call("POST", f"/jobs/{job['id']}/proposals", freelancer, 201, json={
                "bidAmount": 2000, "deliveryDays": 7, "coverLetter": "Work offer",
            })).json()
            project = (await call("POST", f"/proposals/{proposal['id']}/hire", client, 200)).json()["project"]
            project_path = f"/projects/{project['id']}"
            submit_path = project_path + "/submissions"
            work = {
                "title": "First delivery", "description": "Finished the first version of the work.",
                "link": "https://example.com/work", "files": [{"name": "งาน.pdf", "content": b64encode(b"work bytes").decode()}],
            }
            response = await call("POST", submit_path, freelancer, 409, json=work)
            self.assertEqual(response.json()["code"], "ESCROW_NOT_FUNDED")
            report = {"projectId": project["id"], "topic": "report", "message": "Please review this project's issue."}
            await call("POST", "/support/reports", stranger, 403, json=report)
            receipt = (await call("POST", "/support/reports", freelancer, 201, json=report)).json()
            summary_path = f"/admin/reports/{receipt['id']}/project"
            await call("GET", summary_path, freelancer, 403)
            no_escrow = await call("GET", summary_path, admin, 200)
            self.assertEqual(no_escrow.json()["milestones"][0]["escrowStatus"], "unprepared")
            self.assertIsNone(no_escrow.json()["milestones"][0]["submissionStatus"])
            agreement_id = uuid4()
            with Session(self.engine) as db:
                db.add(EscrowAgreement(
                    id=agreement_id, project_id=UUID(project["id"]), milestone_number=1, attempt_number=1, chain_id=11155111,
                    contract_address="0x" + "12" * 20, expected_escrow_id="0x" + "34" * 32,
                    terms_json=json.dumps({"milestones": [{"title": "Final delivery", "amountThb": "2000"}],
                                           "revisionPolicy": {"maxRevisions": 2},
                                           "deadline": int(datetime.now(timezone.utc).timestamp())}),
                    terms_hash="0x" + "56" * 32, next_scan_block=1, status="prepared",
                ))
                db.flush()
                db.add(EscrowTransaction(agreement_id=agreement_id, tx_hash="0x" + "78" * 32, status="pending"))
                db.commit()
            unconfirmed = await call("GET", summary_path, admin, 200)
            self.assertEqual(unconfirmed.json()["milestones"][0]["escrowStatus"], "pending_verification")
            with Session(self.engine) as db:
                db.get(EscrowAgreement, agreement_id).status = "funded"
                db.commit()

            self.assertTrue((await call("GET", project_path, freelancer, 200)).json()["canSubmitWork"])
            await call("POST", submit_path, client, 403, json=work)
            await call("POST", submit_path, freelancer, 422, json={**work, "link": "javascript:alert(1)"})
            await call("POST", submit_path, freelancer, 422, json={**work, "files": [{"name": "work.pdf", "content": "!"}]})
            submitted = (await call("POST", submit_path, freelancer, 201, json=work)).json()
            self.assertEqual(submitted["status"], "in_review")
            first = submitted["submissions"][0]
            self.assertEqual((first["revisionsUsed"], first["revisionLimit"]), (0, 2))
            self.assertEqual(first["links"], [{"label": "", "url": work["link"]}])
            file_path = project_path + "/work-files/" + first["files"][0]["id"]
            downloaded = await call("GET", file_path, client, 200)
            self.assertEqual(downloaded.content, b"work bytes")
            self.assertTrue(downloaded.headers["content-disposition"].startswith("attachment; filename*=UTF-8''"))
            await call("GET", file_path, stranger, 403)
            await call("POST", submit_path, freelancer, 409, json=work)
            notifications = (await call("GET", "/notifications", client, 200)).json()
            notice = next(item for item in notifications if item["type"] == "submission")
            self.assertFalse(notice["read"])
            read = (await call("PATCH", f"/notifications/{notice['id']}/read", client, 200)).json()
            self.assertTrue(read["read"])

            revision = (await call("POST", project_path + "/request-revision", client, 200, json={
                "submissionId": first["id"], "feedback": "Please correct the last page.",
            })).json()
            self.assertEqual(revision["submissions"][0]["feedback"], "Please correct the last page.")
            self.assertEqual(revision["submissions"][0]["revisionsUsed"], 1)
            self.assertTrue(revision["canSubmitWork"])
            links = [{"label": "Mobile", "url": "https://example.com/mobile"},
                     {"label": "Design system", "url": "https://example.com/components"}]
            revised = {**work, "title": "Revised delivery", "link": None, "links": links}
            await call("POST", submit_path, freelancer, 422, json={**revised, "links": [{"url": "javascript:alert(1)"}]})
            second = (await call("POST", submit_path, freelancer, 201, json=revised)).json()["submissions"][0]
            reviewed = (await call("GET", project_path, client, 200)).json()["submissions"][0]
            self.assertEqual(reviewed["links"], links)
            self.assertEqual(reviewed["link"], links[0]["url"])
            await call("POST", project_path + "/approve", client, 409, json={"submissionId": first["id"]})
            revision_path = project_path + "/request-revision"
            request_revision = {"submissionId": second["id"], "feedback": "Please complete the mobile design."}
            await call("POST", revision_path, client, 200, json=request_revision)
            third = (await call("POST", submit_path, freelancer, 201, json=revised)).json()["submissions"][0]
            blocked = await call("POST", revision_path, client, 409,
                                 json={**request_revision, "submissionId": third["id"]})
            self.assertEqual(blocked.json()["code"], "WORK_REVISION_LIMIT_REACHED")
            still_pending = (await call("GET", project_path, client, 200)).json()["submissions"][0]
            self.assertEqual((still_pending["status"], still_pending["revisionsUsed"]), ("pending", 2))
            approved = (await call("POST", project_path + "/approve", client, 200, json={"submissionId": third["id"]})).json()
            self.assertEqual((approved["status"], approved["escrowStatus"], approved["submissions"][0]["status"]),
                             ("completed", "funded", "approved"))

            snapshot = await call("GET", summary_path, admin, 200)
            self.assertEqual(snapshot.headers["cache-control"], "private, no-store")
            [milestone] = snapshot.json()["milestones"]
            self.assertEqual((milestone["escrowStatus"], milestone["submissionStatus"], milestone["submittedAt"]),
                             ("funded", "approved", third["submittedAt"]))
            self.assertEqual(set(milestone), {"number", "title", "amountThb", "escrowStatus", "submissionStatus", "submittedAt"})
            await call("GET", project_path, admin, 403)
            await call("GET", file_path, admin, 403)
            [item] = (await call("GET", "/admin/overview", admin, 200)).json()["reports"]
            self.assertEqual((item["id"], item["target"], item["reason"]), (receipt["id"], project["title"], report["message"]))
            support_path = f"/support/reports/{receipt['id']}"
            replies = support_path + "/messages"
            self.assertEqual((await call("GET", "/support/reports", stranger, 200)).json(), [])
            [my_report] = (await call("GET", "/support/reports", freelancer, 200)).json()
            self.assertEqual(my_report["id"], receipt["id"])
            await call("GET", support_path, client, 404)
            await call("POST", replies, stranger, 404, json={"body": "Private ticket"})
            await call("POST", replies, freelancer, 403, json={"body": "Elevated status", "waitForReporter": True})
            waiting = (await call("POST", replies, admin, 201, json={
                "body": "Please send us the error details.", "waitForReporter": True,
            })).json()
            self.assertEqual(waiting["status"], "waiting")
            self.assertTrue(waiting["messages"][0]["fromAdmin"])
            self.assertEqual((await call("GET", support_path, freelancer, 200)).json(), waiting)
            opened = (await call("POST", replies, freelancer, 201, json={"body": "The upload failed."})).json()
            self.assertEqual(opened["status"], "open")
            self.assertEqual([msg["body"] for msg in opened["messages"]],
                             ["Please send us the error details.", "The upload failed."])
            self.assertFalse(opened["messages"][1]["fromAdmin"])
            report_path = f"/admin/reports/{receipt['id']}"
            await call("PATCH", report_path, freelancer, 403, json={"status": "resolved"})
            resolved = (await call("PATCH", report_path, admin, 200, json={"status": "resolved"})).json()
            self.assertEqual(resolved["status"], "resolved")
            self.assertEqual(resolved["messages"], opened["messages"])
            await call("PATCH", report_path, admin, 200, json={"status": "resolved"})
            await call("GET", summary_path, admin, 409)
            with Session(self.engine) as db:
                accesses = list(db.scalars(select(SupportProjectAccess)))
                admin_id = db.scalar(select(User.id).where(User.role == "admin"))
                self.assertEqual({row.request_id for row in accesses},
                                 {result.headers["x-request-id"] for result in (no_escrow, unconfirmed, snapshot)})
                self.assertTrue(all(row.report_id == UUID(receipt["id"]) and row.project_id == UUID(project["id"])
                                    and row.admin_id == admin_id for row in accesses))
            await call("POST", replies, freelancer, 409, json={"body": "Late reply"})
            await call("POST", replies, admin, 409, json={"body": "Late admin reply"})
            notices = (await call("GET", "/notifications", freelancer, 200)).json()
            support_links = [item["link"] for item in notices if item["type"] == "support"]
            self.assertEqual(support_links, [f"/support/tickets/{receipt['id']}"] * 2)

            review_path = f"/freelancers/{project['freelancerId']}/reviews"
            review_payload = {"projectId": project["id"], "rating": 5, "comment": "Delivered everything in the brief."}
            await call("POST", review_path, freelancer, 403, json=review_payload)
            waiting_review = await call("POST", review_path, client, 409, json=review_payload)
            self.assertEqual(waiting_review.json()["code"], "REVIEW_NOT_ELIGIBLE")
            with Session(self.engine) as db:
                db.get(EscrowAgreement, agreement_id).status = "released"
                db.commit()
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                created_review = await call("POST", review_path, client, 201, json=review_payload)
            request_id = created_review.headers["x-request-id"]
            self.assertTrue(any(f"event=freelancer_review_created request_id={request_id}" in line for line in logs.output))
            duplicate = await call("POST", review_path, client, 409, json=review_payload)
            self.assertEqual(duplicate.json()["code"], "REVIEW_ALREADY_EXISTS")
            self.assertTrue((await call("GET", project_path, client, 200)).json()["freelancerReviewed"])
            profile = (await call("GET", f"/freelancers/{project['freelancerId']}", freelancer, 200)).json()
            self.assertEqual((profile["rating"], profile["reviewsCount"]), (5, 1))
            self.assertEqual(profile["reviews"][0]["comment"], review_payload["comment"])

    async def test_admin_account_moderation(self):
        password = f"test-{uuid4().hex}"
        with Session(self.engine) as db:
            provision_admin(db, "admin.one", password, "Admin", "admin@example.test")
            client_session = auth.create_login(db, "client-key", "client@example.test", "Client", "client")
            subject = "freelancer-key"
            user_session = auth.create_login(db, subject, "freelancer@example.test", "Freelancer", "freelancer")
            second_session = auth.create_login(db, subject, "freelancer@example.test", "Freelancer", "freelancer")
            target_id = db.scalar(select(User.id).where(User.google_subject == subject))
        endpoint = f"/admin/users/{target_id}"
        origin = {"Origin": get_settings().frontend_origin}
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://localhost") as admin,
            AsyncClient(transport=transport, base_url="http://localhost") as guest,
        ):
            self.assertEqual((await guest.get("/admin/overview")).status_code, 401)
            client_headers = {**origin, "Cookie": f"{auth.COOKIE_NAME}={client_session}"}
            self.assertEqual((await guest.get("/admin/overview", headers=client_headers)).status_code, 403)
            job_response = await guest.post("/jobs", headers=client_headers, json={
                "title": "Admin overview job", "description": "Test", "category": "Development",
                "budgetMin": 1000, "budgetMax": 2000, "budgetType": "fixed",
                "duration": "1 week", "experience": "intermediate",
            })
            self.assertEqual(job_response.status_code, 201, job_response.text)
            patch = {"status": "suspended", "reason": "Policy violation"}
            self.assertEqual((await guest.patch(endpoint, headers=client_headers, json=patch)).status_code, 403)
            login = await admin.post("/auth/admin/login", headers=origin, json={
                "username": "admin.one", "password": password,
            })
            self.assertEqual(login.status_code, 204, login.text)
            overview = await admin.get("/admin/overview")
            self.assertEqual(overview.status_code, 200, overview.text)
            users = overview.json()["users"]
            self.assertEqual({user["role"] for user in users}, {"admin", "client", "freelancer"})
            self.assertEqual(overview.json()["jobs"][0]["id"], job_response.json()["id"])
            self.assertTrue(all(set(user) == {"id", "name", "contact", "role", "status", "joined"} for user in users))
            admin_id = next(user["id"] for user in users if user["role"] == "admin")
            history_path = endpoint + "/moderation"
            notices_path = endpoint + "/notices"
            warning = {"kind": "warning", "reason": "Please update the job details"}
            self.assertEqual((await guest.get(history_path, headers=client_headers)).status_code, 403)
            self.assertEqual((await guest.post(notices_path, headers=client_headers, json=warning)).status_code, 403)
            self.assertEqual((await admin.post(notices_path, json=warning)).status_code, 403)
            warning_post = await admin.post(notices_path, headers=origin, json=warning)
            self.assertEqual(warning_post.status_code, 201, warning_post.text)
            self.assertEqual(warning_post.json()["actorName"], "Admin")
            flag = {"kind": "flag", "reason": "Internal review"}
            flag_post = await admin.post(notices_path, headers=origin, json=flag)
            self.assertEqual(flag_post.status_code, 201, flag_post.text)
            target_headers = {"Cookie": f"{auth.COOKIE_NAME}={user_session}"}
            warnings = await guest.get("/auth/warnings", headers=target_headers)
            self.assertEqual(warnings.status_code, 200, warnings.text)
            self.assertEqual([item["reason"] for item in warnings.json()], [warning["reason"]])
            self.assertEqual(set(warnings.json()[0]), {"id", "reason", "createdAt"})
            self.assertEqual((await guest.get("/auth/warnings", headers=client_headers)).json(), [])
            self.assertEqual((await admin.patch(f"/admin/users/{admin_id}", headers=origin, json=patch)).status_code, 403)
            self.assertEqual((await admin.patch(endpoint, headers=origin, json={**patch, "reason": "   "})).status_code, 422)
            for _ in range(2):
                response = await admin.patch(endpoint, headers=origin, json=patch)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["status"], "suspended")
            for token in (user_session, second_session):
                response = await guest.get("/auth/me", headers={"Cookie": f"{auth.COOKIE_NAME}={token}"})
                self.assertEqual(response.status_code, 401)
            with Session(self.engine) as db:
                self.assertIsNone(db.scalar(select(LoginSession).where(LoginSession.user_id == target_id)))
                with self.assertRaises(HTTPException) as rejected:
                    auth.create_login(db, subject, "freelancer@example.test", "Freelancer", "freelancer")
                self.assertEqual(rejected.exception.status_code, 403)
            restored = await admin.patch(endpoint, headers=origin, json={"status": "active", "reason": "Cleared"})
            self.assertEqual(restored.status_code, 200, restored.text)
            history = await admin.get(history_path)
            self.assertEqual(history.status_code, 200, history.text)
            self.assertEqual([item["kind"] for item in history.json()], ["status", "status", "flag", "warning"])
            self.assertEqual(history.json()[0]["previousStatus"], "suspended")
        with Session(self.engine) as db:
            events = db.scalars(select(AdminUserStatusEvent).where(
                AdminUserStatusEvent.target_id == target_id,
            ).order_by(AdminUserStatusEvent.created_at)).all()
            self.assertEqual([(event.new_status, event.reason) for event in events], [
                ("suspended", "Policy violation"), ("active", "Cleared"),
            ])
            auth.create_login(db, subject, "freelancer@example.test", "Freelancer", "freelancer")

    def session_headers(self, token, **extra):
        return {"Origin": get_settings().frontend_origin, "Cookie": f"{auth.COOKIE_NAME}={token}", **extra}

    async def test_freelancer_profile_edit_and_directory(self):
        with Session(self.engine) as db:
            freelancer, other, client = [
                auth.create_login(db, name, f"{name}@example.test", name.title(), role)
                for name, role in (("freelancer", "freelancer"), ("other", "freelancer"), ("client", "client"))
            ]
        profile = {
            "name": "Mali Designer", "title": "Product Designer", "location": "เชียงใหม่",
            "hourlyRate": 1800, "bio": "ออกแบบผลิตภัณฑ์ดิจิทัลมากว่าแปดปี " * 3,
            "availability": "open", "avatarColor": "from-violet-500 to-indigo-600",
            "skills": ["Figma", "ออกแบบระบบ"], "languages": ["ไทย", "English"],
            "portfolio": [{
                "id": "w-1", "title": "Merchant dashboard", "category": "SaaS · Product Design",
                "description": "Dashboard สำหรับร้านค้าออนไลน์",
                "accent": "from-indigo-500 via-violet-500 to-fuchsia-500",
            }],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            me = (await http.get("/auth/me", headers=self.session_headers(freelancer))).json()
            path = f"/freelancers/{me['profileId']}"
            self.assertEqual((await http.get("/freelancers")).json(), [])
            self.assertEqual((await http.get(path)).status_code, 404)
            own = await http.get(path, headers=self.session_headers(freelancer))
            self.assertEqual(own.status_code, 200, own.text)
            self.assertEqual(
                (own.json()["name"], own.json()["title"], own.json()["skills"]), ("Freelancer", None, []),
            )

            async def patch(token, body, expected, headers=None):
                response = await http.patch(
                    path, json=body, headers=self.session_headers(token) if headers is None else headers,
                )
                self.assertEqual(response.status_code, expected, response.text)
                return response.json()

            await patch(None, profile, 401, headers={"Origin": get_settings().frontend_origin})
            await patch(freelancer, profile, 403, headers={"Cookie": f"{auth.COOKIE_NAME}={freelancer}"})
            await patch(client, profile, 403)
            await patch(other, profile, 403)
            for invalid in ({"name": None}, {"hourlyRate": 0}, {"availability": "away"}, {"bio": "  "}):
                await patch(freelancer, invalid, 422)
            saved = await patch(freelancer, profile, 200)
            self.assertEqual(
                (saved["name"], saved["hourlyRate"], saved["skills"]), ("Mali Designer", 1800, profile["skills"]),
            )
            self.assertEqual(saved["portfolio"], profile["portfolio"])
            self.assertEqual((saved["completedJobs"], saved["successRate"], saved["reviewsCount"]), (0, None, 0))
            partial = await patch(freelancer, {"availability": "limited"}, 200)
            self.assertEqual((partial["availability"], partial["title"]), ("limited", "Product Designer"))

            listing = (await http.get("/freelancers")).json()
            self.assertEqual([item["id"] for item in listing], [me["profileId"]])
            self.assertNotIn("email", listing[0])
            self.assertEqual((await http.get(path)).json()["bio"], profile["bio"].strip())
            for query, expected in (
                ("q=mali", 1), ("q=Designer", 1), ("q=ออกแบบ", 1), ("skill=figma", 1), ("skill=ออกแบบระบบ", 1),
                ("skill=React", 0), ("q=nobody", 0), ("availability=limited", 1), ("availability=open", 0),
                ("availability=", 1),
            ):
                found = await http.get(f"/freelancers?{query}")
                self.assertEqual((found.status_code, len(found.json())), (200, expected), query)

            # The chosen name survives the next Google sign-in and reaches /auth/me.
            with Session(self.engine) as db:
                again = auth.create_login(db, "freelancer", "freelancer@example.test", "Renamed By Google", None)
            renamed = await http.get("/auth/me", headers=self.session_headers(again))
            self.assertEqual(renamed.json()["name"], "Mali Designer")

            with Session(self.engine) as db:
                owner = db.scalar(select(Profile.user_id).where(Profile.id == me["profileId"]))
                db.get(User, owner).status = "suspended"
                db.commit()
            self.assertEqual((await http.get("/freelancers")).json(), [])
            self.assertEqual((await http.get(path)).status_code, 404)

    async def test_client_profile_and_display_name_in_jobs(self):
        with Session(self.engine) as db:
            client, freelancer = [
                auth.create_login(db, name, f"{name}@example.test", name.title(), name)
                for name in ("client", "freelancer")
            ]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            me = (await http.get("/auth/me", headers=self.session_headers(client))).json()
            freelancer_me = (await http.get("/auth/me", headers=self.session_headers(freelancer))).json()
            path = f"/clients/{me['profileId']}"
            self.assertEqual((await http.get(path)).status_code, 401)
            wrong_role = await http.get(f"/clients/{freelancer_me['profileId']}", headers=self.session_headers(client))
            self.assertEqual(wrong_role.status_code, 404)
            body = {
                "name": "Acme Studio", "contactName": "Somchai", "title": "Brand studio", "industry": "Design",
                "location": "Bangkok", "website": "https://acme.example", "bio": "We build brands.",
                "avatarColor": "from-sky-500 to-blue-600",
            }

            async def patch(token, payload, expected):
                response = await http.patch(path, json=payload, headers=self.session_headers(token))
                self.assertEqual(response.status_code, expected, response.text)
                return response.json()

            await patch(freelancer, body, 403)
            await patch(client, {**body, "website": "javascript:alert(1)"}, 422)
            await patch(client, {**body, "contactName": None}, 422)
            saved = await patch(client, body, 200)
            self.assertEqual(
                (saved["name"], saved["contactName"], saved["website"]),
                ("Acme Studio", "Somchai", "https://acme.example"),
            )
            self.assertEqual((saved["jobsPosted"], saved["hireRate"]), (0, 0))
            cleared = await patch(client, {"website": "", "industry": ""}, 200)
            self.assertEqual((cleared["website"], cleared["industry"], cleared["title"]), ("", "", "Brand studio"))
            read = await http.get(path, headers=self.session_headers(freelancer))
            self.assertEqual(read.json()["name"], "Acme Studio")

            job = await http.post("/jobs", headers=self.session_headers(client), json={
                "title": "Logo", "description": "Need a logo", "category": "Design", "budgetMin": 1000,
                "budgetMax": 2000, "budgetType": "fixed", "duration": "1 week", "experience": "entry",
            })
            self.assertEqual(job.json()["client"]["name"], "Acme Studio")
            self.assertEqual((await http.get("/jobs?q=acme")).json()[0]["id"], job.json()["id"])
            counted = await http.get(path, headers=self.session_headers(client))
            self.assertEqual(counted.json()["jobsPosted"], 1)

    async def test_notifications_and_project_messages(self):
        with Session(self.engine) as db:
            client, freelancer, stranger = [
                auth.create_login(db, name, f"{name}@example.test", name.title(), role)
                for name, role in (("client", "client"), ("freelancer", "freelancer"), ("stranger", "client"))
            ]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            async def call(method, path, token, expected, **kwargs):
                headers = {**self.session_headers(token), **kwargs.pop("headers", {})}
                response = await http.request(method, path, headers=headers, **kwargs)
                self.assertEqual(response.status_code, expected, response.text)
                return response.json() if response.content else None

            self.assertEqual((await http.get("/notifications")).status_code, 401)
            self.assertEqual((await http.get("/messages/threads")).status_code, 401)
            self.assertEqual(await call("GET", "/notifications", client, 200), [])
            self.assertEqual(await call("GET", "/messages/threads", client, 200), [])

            job = await call("POST", "/jobs", client, 201, json={
                "title": "Logo", "description": "Need a logo", "category": "Design", "budgetMin": 1000,
                "budgetMax": 2000, "budgetType": "fixed", "duration": "1 week", "experience": "entry",
            })
            proposal = await call("POST", f"/jobs/{job['id']}/proposals", freelancer, 201, json={
                "bidAmount": 1500, "deliveryDays": 5, "coverLetter": "I can do it",
            })
            [alert] = await call("GET", "/notifications?audience=client", client, 200)
            self.assertEqual(
                (alert["type"], alert["read"], alert["link"]),
                ("proposal", False, f"/client/jobs/{job['id']}/applicants"),
            )
            self.assertIn("Freelancer", alert["body"])
            self.assertEqual(await call("GET", "/notifications", freelancer, 200), [])

            decision = f"/proposals/{proposal['id']}"
            await call("PATCH", decision, client, 200, json={"status": "shortlisted"})
            await call("PATCH", decision, client, 200, json={"status": "shortlisted"})
            [shortlisted] = await call("GET", "/notifications", freelancer, 200)
            self.assertEqual((shortlisted["type"], shortlisted["link"]), ("proposal", "/freelancer/proposals"))

            await call("PATCH", f"/notifications/{alert['id']}/read", stranger, 404)
            await call("PATCH", f"/notifications/{alert['id']}/read", client, 403,
                       headers={"Origin": "https://other.test"})
            read = await call("PATCH", f"/notifications/{alert['id']}/read", client, 200)
            self.assertTrue(read["read"])

            self.assertEqual(await call("GET", "/messages/threads", freelancer, 200), [])
            hired = await call("POST", f"/proposals/{proposal['id']}/hire", client, 200)
            project = hired["project"]
            hire_alert = (await call("GET", "/notifications", freelancer, 200))[0]
            self.assertEqual(
                (hire_alert["type"], hire_alert["read"], hire_alert["link"]),
                ("job", False, f"/freelancer/projects/{project['id']}"),
            )
            await call("POST", f"/proposals/{proposal['id']}/hire", client, 200)
            self.assertEqual(len(await call("GET", "/notifications", freelancer, 200)), 2)

            [thread] = await call("GET", "/messages/threads", client, 200)
            [mirror] = await call("GET", "/messages/threads", freelancer, 200)
            self.assertEqual(thread["id"], mirror["id"])
            self.assertEqual(
                (thread["project"]["id"], thread["other"]["name"], thread["messages"], thread["unread"]),
                (project["id"], "Freelancer", [], False),
            )
            self.assertEqual(mirror["other"]["name"], "Client")
            self.assertEqual(await call("GET", "/messages/threads", stranger, 200), [])
            thread_path = f"/messages/threads/{thread['id']}"
            await call("GET", thread_path, stranger, 404)
            await call("POST", thread_path + "/messages", stranger, 404, json={"text": "hi"})
            await call("POST", thread_path + "/messages", client, 422, json={"text": "   "})
            await call("POST", thread_path + "/messages", client, 403, json={"text": "hi"},
                       headers={"Origin": "https://other.test"})

            sent = await call("POST", thread_path + "/messages", client, 201, json={"text": "  Hello there  "})
            self.assertEqual((sent["message"]["text"], sent["message"]["senderRole"]), ("Hello there", "client"))
            self.assertEqual(
                (sent["thread"]["unread"], sent["thread"]["lastMessage"]["id"]), (False, sent["message"]["id"]),
            )
            await call("POST", thread_path + "/messages", client, 201, json={"text": "Second"})
            incoming = await call("GET", thread_path, freelancer, 200)
            self.assertEqual([item["text"] for item in incoming["messages"]], ["Hello there", "Second"])
            self.assertEqual((incoming["unread"], incoming["messages"][0]["senderRole"]), (True, "client"))
            alerts = [item for item in await call("GET", "/notifications", freelancer, 200) if item["type"] == "message"]
            self.assertEqual([(item["link"], item["read"]) for item in alerts], [(f"/messages/{thread['id']}", False)])

            await call("PATCH", thread_path + "/read", stranger, 404)
            await call("PATCH", thread_path + "/read", freelancer, 204)
            self.assertFalse((await call("GET", thread_path, freelancer, 200))["unread"])
            alerts = [item for item in await call("GET", "/notifications", freelancer, 200) if item["type"] == "message"]
            self.assertTrue(alerts[0]["read"])
            reply = await call("POST", thread_path + "/messages", freelancer, 201, json={"text": "Thanks"})
            self.assertEqual(reply["message"]["senderRole"], "freelancer")
            self.assertTrue((await call("GET", "/messages/threads", client, 200))[0]["unread"])
            client_alerts = await call("GET", "/notifications", client, 200)
            self.assertEqual([item["type"] for item in client_alerts if not item["read"]], ["message"])

            await call("PATCH", "/notifications/read-all", freelancer, 204)
            self.assertTrue(all(item["read"] for item in await call("GET", "/notifications", freelancer, 200)))
            self.assertFalse(all(item["read"] for item in await call("GET", "/notifications", client, 200)))

    async def test_job_budget_and_deadline_rules(self):
        with Session(self.engine) as db:
            client = auth.create_login(db, "client", "client@example.test", "Client", "client")
        today = platform_today()
        job = {
            "title": "Logo", "description": "Need a logo", "category": "design", "budgetMin": 5000,
            "budgetMax": 30000, "budgetType": "fixed", "duration": "1-2 สัปดาห์", "experience": "entry",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            async def create(expected, **changes):
                response = await http.post("/jobs", json={**job, **changes}, headers=self.session_headers(client))
                self.assertEqual(response.status_code, expected, response.text)
                return response.json()

            # Any positive amount is allowed; 45,000 in the form is only a placeholder.
            self.assertEqual((await create(201, budgetMin=1, budgetMax=1))["budgetMin"], 1)
            await create(201, budgetMin=0.5, budgetMax=2)
            for invalid in ({"budgetMin": 0}, {"budgetMax": 0}, {"budgetMin": -1}, {"budgetMin": 9000, "budgetMax": 100}):
                await create(422, **invalid)

            self.assertEqual((await create(201, deadline=f"{today}T00:00:00.000Z"))["deadline"], str(today))
            await create(201, deadline=str(today + timedelta(days=1)))
            await create(201, deadline=None)
            for past in (today - timedelta(days=1), today - timedelta(days=400)):
                rejected = await create(422, deadline=f"{past}T00:00:00.000Z")
                self.assertEqual(rejected["code"], "INVALID_DEADLINE")
            self.assertEqual((await create(422, deadline=str(today - timedelta(days=1)), status="draft"))["code"], "INVALID_DEADLINE")

            saved = await create(201, deadline=str(today + timedelta(days=5)))
            path = f"/jobs/{saved['id']}"

            async def patch(expected, **changes):
                response = await http.patch(path, json=changes, headers=self.session_headers(client))
                self.assertEqual(response.status_code, expected, response.text)
                return response.json()

            await patch(422, budgetMin=0)
            self.assertEqual((await patch(422, deadline=str(today - timedelta(days=1))))["code"], "INVALID_DEADLINE")
            self.assertEqual((await patch(200, deadline=str(today + timedelta(days=9))))["deadline"], str(today + timedelta(days=9)))
            self.assertIsNone((await patch(200, deadline=None))["deadline"])

            # A posting that went overdue can still be edited while its date is left alone.
            overdue = today - timedelta(days=3)
            with Session(self.engine) as db:
                db.get(Job, UUID(saved["id"])).deadline = overdue
                db.commit()
            self.assertEqual((await patch(200, title="Renamed"))["title"], "Renamed")
            self.assertEqual((await patch(200, deadline=str(overdue)))["deadline"], str(overdue))
            await patch(422, deadline=str(overdue - timedelta(days=1)))

    async def test_transactions_list_is_empty_until_escrow_sync(self):
        with Session(self.engine) as db:
            token = auth.create_login(db, "freelancer", "freelancer@example.test", "Freelancer", "freelancer")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            self.assertEqual((await http.get("/transactions")).status_code, 401)
            response = await http.get("/transactions?userId=ignored", headers=self.session_headers(token))
            self.assertEqual((response.status_code, response.json()), (200, []))

    async def test_jobs_proposals_and_projects_carry_the_other_partys_card(self):
        with Session(self.engine) as db:
            client, first, second = [
                auth.create_login(db, name, f"{name}@example.test", name.title(), role)
                for name, role in (("client", "client"), ("first", "freelancer"), ("second", "freelancer"))
            ]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
            async def call(method, path, token, expected, **kwargs):
                response = await http.request(method, path, headers=self.session_headers(token), **kwargs)
                self.assertEqual(response.status_code, expected, response.text)
                return response.json() if response.content else None

            client_me = await call("GET", "/auth/me", client, 200)
            first_me = await call("GET", "/auth/me", first, 200)
            await call("PATCH", f"/clients/{client_me['profileId']}", client, 200, json={
                "name": "Acme Studio", "title": "Brand studio", "location": "Bangkok",
                "bio": "We build brands.", "avatarColor": "from-sky-500 to-blue-600",
            })
            await call("PATCH", f"/freelancers/{first_me['profileId']}", first, 200, json={
                "title": "Backend dev", "bio": "Ten years of Python.", "hourlyRate": 800,
                "skills": ["Python", "FastAPI"], "avatarColor": "from-rose-500 to-pink-500",
            })
            job = await call("POST", "/jobs", client, 201, json={
                "title": "API", "description": "Build an API", "category": "development", "skills": ["Python"],
                "budgetMin": 1000, "budgetMax": 4000, "budgetType": "fixed", "duration": "1 week",
                "experience": "intermediate", "status": "open",
            })

            # The public job page shows the client's track record, but not their company details or contact.
            public = (await http.get(f"/jobs/{job['id']}")).json()["client"]
            self.assertEqual(
                (public["name"], public["avatarColor"], public["jobsPosted"], public["hireRate"]),
                ("Acme Studio", "from-sky-500 to-blue-600", 1, 0),
            )
            for private in ("bio", "title", "location", "email", "contactName", "website"):
                self.assertNotIn(private, public)
            listed = (await http.get("/jobs")).json()
            self.assertEqual(listed[0]["client"]["jobsPosted"], 1)
            self.assertEqual((await call("GET", f"/clients/{client_me['profileId']}/jobs", client, 200))[0]["client"]["hireRate"], 0)

            offer = {"bidAmount": 2000, "deliveryDays": 7, "coverLetter": "Offer"}
            proposals = {
                name: await call("POST", f"/jobs/{job['id']}/proposals", token, 201, json=offer)
                for name, token in (("first", first), ("second", second))
            }
            self.assertEqual(proposals["first"]["job"]["client"]["name"], "Acme Studio")

            # A freelancer suspended after applying still has a name and track record on the client's list.
            with Session(self.engine) as db:
                db.execute(text("UPDATE users SET status = 'suspended' WHERE google_subject = 'second'"))
                db.commit()
            applicants = {
                item["freelancer"]["name"]: item["freelancer"]
                for item in await call("GET", f"/jobs/{job['id']}/proposals", client, 200)
            }
            card = applicants["First"]
            self.assertEqual(
                (card["title"], card["skills"], card["avatarColor"], card["completedJobs"], card["successRate"]),
                ("Backend dev", ["Python", "FastAPI"], "from-rose-500 to-pink-500", 0, None),
            )
            self.assertEqual((card["rating"], card["reviewsCount"]), (0, 0))
            self.assertEqual((applicants["Second"]["title"], applicants["Second"]["skills"]), (None, []))
            for private in ("email", "bio", "hourlyRate"):
                self.assertNotIn(private, card)

            hired = await call("POST", f"/proposals/{proposals['first']['id']}/hire", client, 200)
            project = hired["project"]
            self.assertEqual((project["client"]["name"], project["freelancer"]["name"]), ("Acme Studio", "First"))
            self.assertEqual(project["freelancer"]["title"], "Backend dev")
            self.assertEqual(project["startDate"], project["createdAt"])
            self.assertEqual(hired["job"]["client"]["hireRate"], 100)
            for token in (client, first):
                mine = (await call("GET", "/projects", token, 200))[0]
                self.assertEqual((mine["client"]["name"], mine["freelancer"]["name"]), ("Acme Studio", "First"))
                for private in ("email", "bio"):
                    self.assertNotIn(private, mine["client"])
                    self.assertNotIn(private, mine["freelancer"])

    async def test_milestone_escrow_agreement_and_finalized_receipts(self):
        client, freelancer, arbiter, contract = [f"0x{value:040x}" for value in range(1, 5)]
        settings = get_settings().model_copy(update={
            "escrow_contract_address": contract, "escrow_thb_per_eth": Decimal("1000000"),
        })
        now = int(datetime.now(timezone.utc).timestamp())
        deadline = now + 8 * 86400
        second_deadline = now + 16 * 86400
        latest_timestamp = now
        block_hash = f"0x{1:064x}"
        receipts = {}
        discovered_logs = []
        finalized = 99

        def fake_rpc(_, method, *params):
            if method == "eth_chainId":
                return hex(settings.escrow_chain_id)
            if method == "eth_getBlockByNumber":
                number = {"latest": 100, "finalized": finalized}.get(params[0])
                return {"number": hex(number if number is not None else int(params[0], 16)),
                        "hash": block_hash, "timestamp": hex(latest_timestamp if params[0] == "latest" else now)}
            if method == "eth_getTransactionReceipt":
                return receipts.get(params[0])
            if method == "eth_getLogs":
                return list(discovered_logs)
            self.fail(f"Unexpected RPC method {method}")

        def new_receipt(tx_hash, event, indexed, values, block=100, address=contract, hash_of_block=block_hash):
            log = {"topics": [event.topic] + ["0x" + encode([kind], [value]).hex()
                   for kind, value in zip(event.indexed, indexed)], "address": address,
                   "data": "0x" + encode(event.data, values).hex(), "logIndex": "0x0",
                   "transactionHash": tx_hash, "blockNumber": hex(block)}
            receipts[tx_hash] = {"logs": [log], "blockNumber": hex(block), "blockHash": hash_of_block,
                                 "status": "0x1", "transactionHash": tx_hash}
            return log

        with Session(self.engine) as db:
            metadata = [("client", "client", client), ("freelancer", "freelancer", freelancer),
                        ("stranger", "client", None)]
            sessions = {}
            for name, role, address in metadata:
                sessions[name] = self.session_headers(auth.create_login(db, name, f"{name}@example.test", name, role))
                if address:
                    user_id = db.scalar(select(User.id).where(User.google_subject == name))
                    db.add(WalletLink(user_id=user_id, address=address, chain_id=settings.escrow_chain_id,
                                      verified_at=datetime.now(timezone.utc)))
            db.commit()

        transport = ASGITransport(app=app)
        with (patch("app.escrow.get_settings", return_value=settings),
              patch.object(EscrowChain, "call", fake_rpc),
              patch.object(EscrowChain, "policy", return_value=(arbiter, 2, 365 * 86400)),
              patch.object(EscrowChain, "is_occupied", return_value=False),
              patch("app.escrow_worker.get_engine", return_value=self.engine)):
            async with AsyncClient(transport=transport, base_url="http://localhost") as http:
                async def request(method, path, role, expected, **kwargs):
                    result = await http.request(method, path, headers=sessions[role], **kwargs)
                    self.assertEqual(result.status_code, expected, result.text)
                    return result.json()

                job = await request("POST", "/jobs", "client", 201, json={
                    "title": "Escrow test", "description": "Cafe\u0301 และงานระบบ", "category": "Development",
                    "budgetMin": 1000, "budgetMax": 1000, "budgetType": "fixed",
                    "duration": "1 week", "experience": "intermediate", "status": "open",
                    "deliverables": ["เว็บไซต์ทดสอบ"],
                })
                proposal = await request("POST", f"/jobs/{job['id']}/proposals", "freelancer", 201, json={
                    "bidAmount": 1000, "deliveryDays": 8, "coverLetter": "Escrow offer",
                })
                project = (await request("POST", f"/proposals/{proposal['id']}/hire", "client", 200))["project"]
                base = f"/projects/{project['id']}"
                path = base + "/escrow"
                milestones = [{"title": "Core", "amountThb": "250.00", "checklist": ["เข้าใช้งานได้"], "deadline": deadline},
                              {"title": "Finish", "amountThb": "750.00", "checklist": ["ติดตั้งได้"], "deadline": second_deadline}]
                prepare = {"milestones": milestones}
                await request("GET", path, "stranger", 403)
                await request("POST", path + "/prepare", "freelancer", 403, json=prepare)
                missing = {key: value for key, value in milestones[1].items() if key != "deadline"}
                error = await request("POST", path + "/prepare", "client", 422,
                                      json={"milestones": [milestones[0], missing]})
                self.assertEqual(error["code"], "ESCROW_DEADLINE_REQUIRED")
                error = await request("POST", path + "/prepare", "client", 422,
                                      json={"milestones": [milestones[0], {**milestones[1], "deadline": deadline}]})
                self.assertEqual(error["code"], "ESCROW_DEADLINE_ORDER")
                past = await request("POST", path + "/prepare", "client", 422,
                                     json={"milestones": [{**milestones[0], "deadline": now - 60}, milestones[1]]})
                self.assertEqual(past["code"], "ESCROW_DEADLINE")
                invalid = [{**milestones[0], "amountThb": 400}, {**milestones[1], "amountThb": 600}]
                await request("POST", path + "/prepare", "client", 422, json={"milestones": invalid})
                one, two = await asyncio.gather(*(request("POST", path + "/prepare", "client", 200, json=prepare)
                                                   for _ in range(2)))
                self.assertEqual(one, two)
                escrow_view = await request("GET", path, "freelancer", 200)
                self.assertEqual(escrow_view["agreements"], [one])
                self.assertEqual(escrow_view["deliverables"], ["เว็บไซต์ทดสอบ"])
                self.assertEqual(escrow_view["approvedAgreementIds"], [])
                self.assertEqual((escrow_view["proposedDeliveryDays"], escrow_view["minDeadlineDays"]), (8, 7))
                terms = json.loads(one["termsJson"])
                self.assertEqual((terms["amountWei"], terms["deadline"], terms["scope"]),
                                 ("250000000000000", deadline, "Café และงานระบบ"))
                self.assertEqual(terms["milestones"], milestones)
                self.assertEqual(one["termsHash"], hex_hash(one["termsJson"].encode()))
                await request("POST", path + "/prepare", "client", 409,
                              json={"milestoneNumber": 2, "deadline": deadline})
                consent = {"agreementId": one["id"], "termsHash": one["termsHash"],
                           "tosVersion": terms["tosVersion"], "accepted": True}
                await request("POST", path + "/consent", "client", 409,
                              json={**consent, "termsHash": f"0x{0:064x}"})
                await request("POST", path + "/consent", "client", 200, json=consent)

                async def record(tx_hash, expected):
                    return await request("POST", path + "/transactions", "freelancer", expected,
                                         json={"agreementId": one["id"], "txHash": tx_hash})

                key = bytes.fromhex(one["expectedEscrowId"][2:])
                indexed = [key, bytes.fromhex(terms["projectKey"][2:]), client]
                values = [freelancer, int(terms["amountWei"]), 12500000000000, deadline,
                          bytes.fromhex(one["termsHash"][2:])]
                fund_hash, wrong_hash, release_hash = [f"0x{value:064x}" for value in range(10, 13)]
                new_receipt(fund_hash, FUNDED, indexed, values)
                pending = await record(fund_hash, 202)
                self.assertEqual(pending["status"], "pending")
                waiting = await request("GET", base, "freelancer", 200)
                self.assertEqual(waiting["escrowStatus"], "pending_verification")
                self.assertFalse(waiting["canSubmitWork"])
                finalized = 100
                new_receipt(wrong_hash, FUNDED, indexed, [*values[:1], values[1] + 1, *values[2:]])
                bad = await record(wrong_hash, 200)
                self.assertEqual(bad["error"], "ESCROW_EVENT_MISMATCH")
                self.assertEqual((await request("GET", path, "client", 200))["agreements"][0]["escrowId"], None)
                receipts[fund_hash]["blockHash"] = f"0x{2:064x}"
                await record(fund_hash, 202)
                receipts[fund_hash]["blockHash"] = block_hash
                confirmed = await record(fund_hash, 200)
                self.assertEqual(confirmed["event"], "EscrowFunded")
                self.assertEqual(confirmed, await record(fund_hash, 200))
                funded = await request("GET", base, "freelancer", 200)
                self.assertEqual((funded["escrowStatus"], funded["escrowAmount"]), ("funded", 250))
                due_date = funded["milestones"][1]["dueDate"].replace("Z", "+00:00")
                self.assertEqual(datetime.fromisoformat(due_date).timestamp(), second_deadline)
                submission = (await request("POST", base + "/submissions", "freelancer", 201, json={
                    "title": "Website draft", "description": "The website is ready to review.",
                }))["submissions"][0]
                self.assertEqual((submission["milestoneNumber"], submission["checklist"]), (1, milestones[0]["checklist"]))
                await request("POST", base + "/approve", "client", 200, json={"submissionId": submission["id"]})
                self.assertEqual((await request("GET", path, "client", 200))["approvedAgreementIds"], [one["id"]])
                await request("POST", path + "/prepare", "client", 409, json={"milestoneNumber": 2})
                history = await request("GET", "/transactions", "client", 200)
                self.assertEqual([tx["amount"] for tx in history], [262.5])
                self.assertEqual(await request("GET", "/transactions", "stranger", 200), [])
                detail = f"/transactions/{history[0]['id']}"
                self.assertEqual(await request("GET", detail, "client", 200), history[0])
                await request("GET", detail, "stranger", 404)

                discovered_logs.append(new_receipt(release_hash, RELEASED, [key, freelancer], values[1:3], block=101))
                await record(release_hash, 202)
                progress_path = path + "/release-progress"
                progress = await request("GET", progress_path, "client", 200)
                self.assertEqual((progress["status"], progress["txHash"], progress["txBlock"], progress["finalizedBlock"]),
                                 ("awaiting_finality", release_hash, 101, 100))
                await request("GET", progress_path, "stranger", 403)
                finalized = 101
                self.assertEqual((await request("GET", progress_path, "client", 200))["status"], "syncing")
                sync_once()
                released = (await request("GET", path, "client", 200))["agreements"][0]
                self.assertEqual(released["status"], "released")
                sync_once()
                self.assertEqual((await request("GET", path, "client", 200))["agreements"][0], released)
                second_payload = {"milestoneNumber": 2}
                latest_timestamp = second_deadline - 86400
                stale = await request("POST", path + "/prepare", "client", 422, json=second_payload)
                self.assertEqual(stale["code"], "ESCROW_PLANNED_DEADLINE")
                latest_timestamp = now
                next_agreement = await request("POST", path + "/prepare", "client", 200, json=second_payload)
                self.assertNotEqual(one["expectedEscrowId"], next_agreement["expectedEscrowId"])
                second_terms = json.loads(next_agreement["termsJson"])
                self.assertEqual(second_terms["deadline"], second_deadline)
                self.assertEqual(second_terms["milestones"], milestones)
                await request("POST", path + "/consent", "client", 200, json={
                    **consent, "agreementId": next_agreement["id"], "termsHash": next_agreement["termsHash"],
                })
                second_key = bytes.fromhex(next_agreement["expectedEscrowId"][2:])
                second_indexed = [second_key, bytes.fromhex(second_terms["projectKey"][2:]), client]
                fund_second_hash, refund_hash = [f"0x{value:064x}" for value in (21, 22)]
                second_amount = int(second_terms["amountWei"])
                discovered_logs[:] = [new_receipt(fund_second_hash, FUNDED, second_indexed,
                    [freelancer, second_amount, 0, second_deadline, bytes.fromhex(next_agreement["termsHash"][2:])], block=102),
                    new_receipt(refund_hash, REFUNDED, [second_key, client], [second_amount], block=103)]
                finalized = 103
                sync_once()
                retry_deadline = second_deadline + 86400
                retry = await request("POST", path + "/prepare", "client", 200,
                                      json={**second_payload, "deadline": retry_deadline})
                self.assertEqual(retry["attemptNumber"], 2)
                self.assertNotEqual(retry["expectedEscrowId"], next_agreement["expectedEscrowId"])
                retry_terms = json.loads(retry["termsJson"])
                self.assertEqual(retry_terms["deadline"], retry_deadline)
                self.assertEqual(retry_terms["milestones"], milestones)
                with Session(self.engine) as db:
                    scanned = db.get(EscrowAgreement, UUID(next_agreement["id"]))
                    self.assertEqual((scanned.status, scanned.next_scan_block), ("refunded", 104))

                single_job = await request("POST", "/jobs", "client", 201, json={
                    "title": "Single payment", "description": "One milestone", "category": "Development",
                    "budgetMin": 1000, "budgetMax": 1000, "budgetType": "fixed",
                    "duration": "1 month", "experience": "intermediate", "status": "open",
                })
                single_proposal = await request("POST", f"/jobs/{single_job['id']}/proposals", "freelancer", 201,
                                                json={"bidAmount": 1000, "deliveryDays": 9, "coverLetter": "Offer"})
                hired = await request("POST", f"/proposals/{single_proposal['id']}/hire", "client", 200)
                single_path = f"/projects/{hired['project']['id']}/escrow/prepare"
                single = await request("POST", single_path, "client", 200, json={})
                self.assertEqual(json.loads(single["termsJson"])["deadline"], now + 9 * 86400)
                single_terms = json.loads(single["termsJson"])
                single_key = bytes.fromhex(single["expectedEscrowId"][2:])
                single_amount = int(single_terms["amountWei"])
                single_id = hired["project"]["id"]
                single_escrow = f"/projects/{single_id}/escrow"
                await request("POST", single_escrow + "/consent", "client", 200, json={
                    **consent, "agreementId": single["id"], "termsHash": single["termsHash"],
                })
                with Session(self.engine) as db:
                    db.get(Project, UUID(single_id)).status = "completed"
                    db.commit()
                discovered_logs[:] = [new_receipt(f"0x{30:064x}", FUNDED,
                    [single_key, bytes.fromhex(single_terms["projectKey"][2:]), client],
                    [freelancer, single_amount, 0, single_terms["deadline"], bytes.fromhex(single["termsHash"][2:])], block=104),
                    new_receipt(f"0x{31:064x}", RELEASED, [single_key, freelancer], [single_amount, 0], block=105)]
                finalized = 104
                sync_once()
                job_path = f"/jobs/{single_job['id']}"
                self.assertEqual((await request("GET", job_path, "client", 200))["status"], "in_progress")
                finalized = 105
                sync_once()
                job = await request("GET", job_path, "client", 200)
                self.assertEqual((job["status"], job["projectCompleted"], job["projectPaid"]), ("closed", True, True))
                self.assertEqual((await request("GET", single_escrow + "/release-progress", "client", 200))["status"], "released")
                with Session(self.engine) as db:
                    self.assertEqual(db.get(Job, UUID(single_job["id"])).status, "closed")

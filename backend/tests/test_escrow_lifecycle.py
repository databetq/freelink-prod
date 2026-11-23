import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from eth_abi import encode
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.admin_accounts import provision_admin
from app.config import get_settings
from app.escrow_chain import (
    ACCEPTED, DEFERRED, DISPUTED, FUNDED, REFUNDED, RELEASED, RESOLVED, REVISION, SUBMITTED, EscrowChain,
)
from app.escrow_worker import sync_once
from app.main import app
from app.models import EscrowAgreement, Job, User, WalletLink
from tests.test_marketplace import DatabaseTest

CLIENT, FREELANCER, ARBITER, CONTRACT = [f"0x{value:040x}" for value in range(1, 5)]
BLOCK_HASH = f"0x{1:064x}"

class EscrowLifecycleTest(DatabaseTest):
    """Every way an escrow can end must leave the project somewhere the parties can continue from."""

    def setUp(self):
        super().setUp()
        self.settings = get_settings().model_copy(update={
            "escrow_contract_address": CONTRACT, "escrow_thb_per_eth": Decimal("1000000"),
            "escrow_confirmations": None, "escrow_min_deadline_minutes": 10,
        })
        self.now = int(datetime.now(timezone.utc).timestamp())
        self.receipts, self.logs, self.block = {}, [], 100
        for target in (
            patch("app.escrow.get_settings", return_value=self.settings),
            patch("app.escrow_chain.get_settings", return_value=self.settings),
            patch("app.escrow_worker.get_settings", return_value=self.settings),
            patch.object(EscrowChain, "call", self.rpc()),
            patch.object(EscrowChain, "policy", return_value=(ARBITER, 2, 365 * 86400)),
            patch.object(EscrowChain, "is_occupied", return_value=False),
            patch("app.escrow_worker.get_engine", return_value=self.engine),
        ):
            target.start()
            self.addCleanup(target.stop)
        with Session(self.engine) as db:
            self.sessions = {}
            for name, role, address in (("client", "client", CLIENT), ("freelancer", "freelancer", FREELANCER)):
                token = auth.create_login(db, name, f"{name}@example.test", name, role)
                self.sessions[name] = self.session_headers(token)
                user_id = db.scalar(select(User.id).where(User.google_subject == name))
                db.add(WalletLink(user_id=user_id, address=address, chain_id=self.settings.escrow_chain_id,
                                  verified_at=datetime.now(timezone.utc)))
            provision_admin(db, "arbiter", "arbiter-password-1", "Arbiter", "arbiter@example.test", add=None)
            admin_id = db.scalar(select(User.id).where(User.role == "admin"))
            self.sessions["admin"] = self.session_headers(auth.create_session(db, admin_id))
            db.commit()
        self.http = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")

    def rpc(self):
        def call(_, method, *params):
            if method == "eth_chainId":
                return hex(self.settings.escrow_chain_id)
            if method == "eth_getBlockByNumber":
                number = {"latest": self.block, "finalized": self.block}.get(params[0])
                return {"number": hex(number if number is not None else int(params[0], 16)),
                        "hash": BLOCK_HASH, "timestamp": hex(self.now)}
            if method == "eth_getTransactionReceipt":
                return self.receipts.get(params[0])
            if method == "eth_getLogs":
                first, last = int(params[0]["fromBlock"], 16), int(params[0]["toBlock"], 16)
                return [log for log in self.logs if first <= int(log["blockNumber"], 16) <= last
                        and log["topics"][1] == params[0]["topics"][1]]
            self.fail(f"Unexpected RPC method {method}")
        return call

    async def request(self, method, path, role, expected, **kwargs):
        result = await self.http.request(method, path, headers=self.sessions[role], **kwargs)
        self.assertEqual(result.status_code, expected, result.text)
        return result.json() if result.content else None

    def emit(self, event, indexed, values, *, data=None, extra=(), sync=True):
        """Mine one transaction with the event and let the worker find it."""
        self.block += 1
        tx_hash = f"0x{self.block:064x}"
        payload = data if data is not None else encode(event.data, values)
        topics = [event.topic] + ["0x" + encode([kind], [value]).hex() for kind, value in zip(event.indexed, indexed)]
        log = {"topics": topics, "address": CONTRACT, "data": "0x" + payload.hex(), "logIndex": "0x0",
               "transactionHash": tx_hash, "blockNumber": hex(self.block)}
        self.receipts[tx_hash] = {"logs": [log, *extra], "blockNumber": hex(self.block), "blockHash": BLOCK_HASH,
                                  "status": "0x1", "transactionHash": tx_hash}
        self.logs.append(log)
        if sync:
            sync_once()
        return tx_hash

    async def funded_project(self, title="Lifecycle", milestones=None):
        job = await self.request("POST", "/jobs", "client", 201, json={
            "title": title, "description": "Work", "category": "Development", "budgetMin": 1000, "budgetMax": 1000,
            "budgetType": "fixed", "duration": "1 week", "experience": "intermediate", "status": "open",
        })
        proposal = await self.request("POST", f"/jobs/{job['id']}/proposals", "freelancer", 201,
                                      json={"bidAmount": 1000, "deliveryDays": 8, "coverLetter": "Offer"})
        project = (await self.request("POST", f"/proposals/{proposal['id']}/hire", "client", 200))["project"]
        base = f"/projects/{project['id']}"
        await self.fund(base, {"milestones": milestones} if milestones else {"deadline": self.now + 900})
        return job, base

    async def fund(self, base, payload):
        agreement = await self.request("POST", base + "/escrow/prepare", "client", 200, json=payload)
        terms = json.loads(agreement["termsJson"])
        await self.request("POST", base + "/escrow/consent", "client", 200, json={
            "agreementId": agreement["id"], "termsHash": agreement["termsHash"], "tosVersion": terms["tosVersion"],
            "accepted": True,
        })
        self.key, self.amount = bytes.fromhex(agreement["expectedEscrowId"][2:]), int(terms["amountWei"])
        self.agreement_id = agreement["id"]
        self.emit(FUNDED, [self.key, bytes.fromhex(terms["projectKey"][2:]), CLIENT],
                  [FREELANCER, self.amount, 0, terms["deadline"], bytes.fromhex(agreement["termsHash"][2:])])
        self.emit(ACCEPTED, [self.key, FREELANCER], [])
        return agreement

    async def submit(self, base, expected=201, review_ends_at=None):
        project = await self.request("POST", base + "/submissions", "freelancer", expected, json={
            "title": "Finished website", "description": "The website is ready to review.",
        })
        if expected == 201:
            submission = project["submissions"][0]
            self.assertIsNone(submission["chainSubmittedAt"])
            waiting = await self.request("POST", base + "/approve", "client", 409, json={"submissionId": submission["id"]})
            self.assertEqual(waiting["code"], "WORK_NOT_ON_CHAIN")
            view = await self.request("GET", base + "/escrow", "freelancer", 200)
            self.assertEqual(view["latestSubmissions"][self.agreement_id]["workHash"], submission["workHash"])
            self.emit(SUBMITTED, [self.key, FREELANCER], [
                bytes.fromhex(submission["workHash"][2:]), review_ends_at or self.now + 900,
            ])
            confirmed = await self.request("GET", base, "client", 200)
            self.assertIsNotNone(confirmed["submissions"][0]["chainSubmittedAt"])
        return project

    async def state(self, job, base):
        project = await self.request("GET", base, "client", 200)
        return project["status"], project["escrowStatus"], (await self.request("GET", f"/jobs/{job['id']}", "client", 200))["status"]

    async def notices(self, role):
        return [item["title"] for item in await self.request("GET", "/notifications", role, 200) if item["type"] == "payment"]

    async def test_events_of_a_normal_run_are_recorded_and_announced(self):
        job, base = await self.funded_project()
        project = await self.submit(base)
        await self.request("POST", base + "/request-revision", "client", 200, json={
            "submissionId": project["submissions"][0]["id"], "feedback": "Please adjust the colours.",
        })
        self.emit(REVISION, [self.key], [1, "freelink:rev:v1", self.now + 900])
        project = await self.submit(base)
        self.assertEqual((await self.state(job, base))[0], "in_review")
        await self.request("POST", base + "/approve", "client", 200, json={"submissionId": project["submissions"][0]["id"]})
        self.assertEqual(await self.state(job, base), ("active", "funded", "in_progress"))
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        self.assertEqual(await self.state(job, base), ("completed", "released", "closed"))
        view = await self.request("GET", base + "/escrow", "client", 200)
        self.assertEqual([tx["event"] for tx in view["agreements"][0]["transactions"]], [
            "EscrowFunded", "EscrowAccepted", "WorkSubmitted", "RevisionRequested", "WorkSubmitted", "PaymentReleased",
        ])
        self.assertIn("ผู้จ้างฝากเงินแล้ว", await self.notices("freelancer"))
        self.assertIn("ฟรีแลนซ์รับงานแล้ว", await self.notices("client"))
        history = await self.request("GET", "/transactions", "freelancer", 200)
        self.assertEqual([tx["type"] for tx in history], ["earning"])

    async def test_claim_after_a_silent_review_completes_the_project(self):
        job, base = await self.funded_project()
        project = await self.submit(base, review_ends_at=self.now - 1)
        expired = await self.request("POST", base + "/request-revision", "client", 409, json={
            "submissionId": project["submissions"][0]["id"], "feedback": "Please adjust the colours.",
        })
        self.assertEqual(expired["code"], "WORK_REVIEW_EXPIRED")
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        self.assertEqual(await self.state(job, base), ("completed", "released", "closed"))
        project = await self.request("GET", base, "client", 200)
        self.assertEqual(project["submissions"][0]["status"], "approved")
        await self.request("POST", f"/freelancers/{project['freelancerId']}/reviews", "client", 201, json={
            "projectId": project["id"], "rating": 5, "comment": "Delivered on time.",
        })

    async def test_release_before_any_submission_completes_the_project(self):
        job, base = await self.funded_project()
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        self.assertEqual(await self.state(job, base), ("completed", "released", "closed"))

    async def test_refund_reopens_the_milestone_and_blocks_a_late_approval(self):
        job, base = await self.funded_project()
        project = await self.submit(base)
        with Session(self.engine) as db:
            # The refund is settled by the worker while the client still has the review page open.
            db.get(EscrowAgreement, UUID(self.agreement_id)).status = "refunded"
            db.commit()
        payload = {"submissionId": project["submissions"][0]["id"]}
        error = await self.request("POST", base + "/approve", "client", 409, json=payload)
        self.assertEqual(error["code"], "ESCROW_NOT_FUNDED")
        await self.request("POST", base + "/request-revision", "client", 409, json={**payload, "feedback": "Please adjust it."})
        with Session(self.engine) as db:
            db.get(EscrowAgreement, UUID(self.agreement_id)).status = "funded"
            db.commit()
        self.emit(REFUNDED, [self.key, CLIENT], [self.amount])
        self.assertEqual(await self.state(job, base), ("active", "refunded", "in_progress"))
        await self.fund(base, {"deadline": self.now + 900})
        self.assertEqual((await self.state(job, base))[1], "funded")
        await self.submit(base)
        self.assertEqual((await self.state(job, base))[0], "in_review")

    async def test_a_ruling_ends_the_project(self):
        job, base = await self.funded_project()
        await self.submit(base)
        self.emit(DISPUTED, [self.key, CLIENT], [], data=b"\xff" * 32)  # Free text is never decoded.
        self.assertEqual((await self.state(job, base))[0], "disputed")
        await self.request("POST", base + "/submissions", "freelancer", 409, json={
            "title": "Another version", "description": "Sent while the dispute is open.",
        })
        await self.request("GET", "/admin/disputes", "client", 403)
        disputes = await self.request("GET", "/admin/disputes", "admin", 200)
        self.assertEqual([(item["status"], item["escrowId"], item["clientName"], len(item["submissions"])) for item in disputes],
                         [("funded", "0x" + self.key.hex(), "client", 1)])
        self.assertIsNotNone(disputes[0]["openedAt"])
        self.emit(RESOLVED, [self.key], [6000, self.amount * 6 // 10, self.amount * 4 // 10, 0, False])
        self.assertEqual(await self.state(job, base), ("resolved", "resolved", "closed"))
        self.assertIn("ข้อพิพาทสิ้นสุดแล้ว", await self.notices("freelancer"))
        self.assertEqual((await self.request("GET", "/admin/disputes", "admin", 200))[0]["status"], "resolved")
        again = await self.request("POST", base + "/escrow/prepare", "client", 409, json={"milestoneNumber": 2})
        self.assertEqual(again["code"], "ESCROW_PROJECT_CLOSED")

    async def test_a_party_can_give_up_a_dispute(self):
        job, base = await self.funded_project()
        self.emit(DISPUTED, [self.key, FREELANCER], ["reason", ARBITER], sync=False)
        refund = self.emit(REFUNDED, [self.key, CLIENT], [self.amount], sync=False)
        await self.request("POST", base + "/escrow/transactions", "freelancer", 202, json={
            "agreementId": self.agreement_id, "txHash": refund,
        })
        sync_once()
        self.assertEqual(await self.state(job, base), ("resolved", "refunded", "closed"))
        self.assertEqual((await self.request("GET", "/admin/disputes", "admin", 200))[0]["status"], "refunded")

    async def test_claiming_one_milestone_lets_the_next_one_start(self):
        milestones = [{"title": "Core", "amountThb": "250.00", "checklist": ["Works"], "deadline": self.now + 900},
                      {"title": "Finish", "amountThb": "750.00", "checklist": ["Installed"], "deadline": self.now + 1800}]
        job, base = await self.funded_project(milestones=milestones)
        await self.submit(base)
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        self.assertEqual((await self.state(job, base))[0], "active")
        await self.fund(base, {"milestoneNumber": 2})
        await self.submit(base)
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        self.assertEqual(await self.state(job, base), ("completed", "released", "closed"))

    async def test_a_deferred_payout_tells_its_owner_to_withdraw(self):
        _, base = await self.funded_project()
        deferred = {"topics": [DEFERRED.topic, "0x" + encode(["address"], [FREELANCER]).hex()], "address": CONTRACT,
                    "data": "0x" + encode(["uint256"], [self.amount]).hex(), "logIndex": "0x1"}
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0], extra=[deferred])
        self.assertIn("มียอดให้ถอนจากสัญญา", await self.notices("freelancer"))
        self.assertNotIn("มียอดให้ถอนจากสัญญา", await self.notices("client"))

    async def test_unknown_hashes_are_limited(self):
        _, base = await self.funded_project()
        for value in range(5):
            await self.request("POST", base + "/escrow/transactions", "freelancer", 202,
                               json={"agreementId": self.agreement_id, "txHash": f"0x{900 + value:064x}"})
        payload = {"agreementId": self.agreement_id, "txHash": f"0x{999:064x}"}
        error = await self.request("POST", base + "/escrow/transactions", "freelancer", 429, json=payload)
        self.assertEqual(error["code"], "ESCROW_TOO_MANY_PENDING")
        await self.request("POST", base + "/escrow/transactions", "freelancer", 202, json={**payload, "txHash": f"0x{900:064x}"})

    async def test_a_hired_job_cannot_be_reopened_or_deleted(self):
        job, base = await self.funded_project()
        self.emit(RELEASED, [self.key, FREELANCER], [self.amount, 0])
        for method, kwargs in (("PATCH", {"json": {"status": "open"}}), ("DELETE", {})):
            error = await self.request(method, f"/jobs/{job['id']}", "client", 409, **kwargs)
            self.assertEqual(error["code"], "JOB_ALREADY_HIRED")
        with Session(self.engine) as db:
            self.assertEqual(db.get(Job, UUID(job["id"])).status, "closed")

    async def test_bids_stay_in_budget_and_suspended_accounts_are_kept_out(self):
        job = await self.request("POST", "/jobs", "client", 201, json={
            "title": "Budget", "description": "Work", "category": "Development", "budgetMin": 100, "budgetMax": 1000,
            "budgetType": "fixed", "duration": "1 week", "experience": "intermediate", "status": "open",
        })
        offer = {"bidAmount": 1001, "deliveryDays": 8, "coverLetter": "Offer"}
        error = await self.request("POST", f"/jobs/{job['id']}/proposals", "freelancer", 422, json=offer)
        self.assertEqual(error["code"], "BID_OVER_BUDGET")
        proposal = await self.request("POST", f"/jobs/{job['id']}/proposals", "freelancer", 201, json={**offer, "bidAmount": 1000})

        def suspend(subject, status):
            with Session(self.engine) as db:
                db.scalar(select(User).where(User.google_subject == subject)).status = status
                db.commit()

        suspend("freelancer", "suspended")
        error = await self.request("POST", f"/proposals/{proposal['id']}/hire", "client", 409)
        self.assertEqual(error["code"], "FREELANCER_UNAVAILABLE")
        suspend("freelancer", "active")
        suspend("client", "suspended")
        self.assertEqual(await self.request("GET", "/jobs", "freelancer", 200), [])

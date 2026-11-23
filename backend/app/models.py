from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('client', 'freelancer', 'admin')", name="ck_users_role"),
        CheckConstraint("status IN ('active', 'suspended')", name="ck_users_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("availability IN ('open', 'limited', 'unavailable')", name="ck_profiles_availability"),
        CheckConstraint("hourly_rate IS NULL OR hourly_rate >= 0", name="ck_profiles_hourly_rate"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    # users.name is overwritten from Google on every sign-in, so the name the person
    # chose to show lives here and wins when it is set.
    display_name: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_color: Mapped[str | None] = mapped_column(String(100))
    availability: Mapped[str] = mapped_column(String(16), server_default="open")
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    languages: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    portfolio: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]")
    contact_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(300))


class WalletLink(Base):
    __tablename__ = "wallet_links"
    __table_args__ = (UniqueConstraint("address", name="uq_wallet_links_address"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    address: Mapped[str] = mapped_column(String(42))
    chain_id: Mapped[int] = mapped_column(BigInteger)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WalletChallenge(Base):
    __tablename__ = "wallet_challenges"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    nonce: Mapped[UUID]
    address: Mapped[str] = mapped_column(String(42))
    chain_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AdminCredential(Base):
    __tablename__ = "admin_credentials"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    failed_attempts: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    failed_attempts: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminUserStatusEvent(Base):
    __tablename__ = "admin_user_status_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    target_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    previous_status: Mapped[str] = mapped_column(String(16))
    new_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminUserNotice(Base):
    __tablename__ = "admin_user_notices"
    __table_args__ = (
        CheckConstraint("kind IN ('warning', 'flag')", name="ck_admin_user_notices_kind"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    target_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("budget_min >= 0 AND budget_max >= budget_min", name="ck_jobs_budget"),
        CheckConstraint("budget_type IN ('fixed', 'hourly')", name="ck_jobs_budget_type"),
        CheckConstraint(
            "status IN ('open', 'draft', 'in_progress', 'closed')", name="ck_jobs_status"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    deliverables: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget_min: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    budget_type: Mapped[str] = mapped_column(String(16))
    duration: Mapped[str] = mapped_column(String(100))
    experience: Mapped[str] = mapped_column(String(100))
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("job_id", "freelancer_id", name="uq_proposals_job_freelancer"),
        CheckConstraint("bid_amount > 0 AND delivery_days > 0", name="ck_proposals_offer"),
        CheckConstraint(
            "status IN ('pending', 'shortlisted', 'hired', 'rejected', 'withdrawn')",
            name="ck_proposals_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    freelancer_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    bid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    delivery_days: Mapped[int]
    cover_letter: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("client_id <> freelancer_id", name="ck_projects_distinct_parties"),
        CheckConstraint("budget > 0", name="ck_projects_budget"),
        CheckConstraint(
            "status IN ('active', 'in_review', 'revision', 'completed', 'disputed', 'cancelled', 'resolved')",
            name="ck_projects_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("proposals.id"), unique=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    freelancer_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EscrowAgreement(Base):
    __tablename__ = "escrow_agreements"
    __table_args__ = (
        UniqueConstraint("project_id", "milestone_number", "attempt_number", name="uq_escrow_attempt"),
        UniqueConstraint("chain_id", "contract_address", "expected_escrow_id", name="uq_escrow_on_chain"),
        CheckConstraint("milestone_number > 0 AND attempt_number > 0", name="ck_escrow_numbers"),
        CheckConstraint(
            "status IN ('prepared', 'funded', 'released', 'refunded', 'resolved', 'expired')",
            name="ck_escrow_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    milestone_number: Mapped[int]
    attempt_number: Mapped[int]
    chain_id: Mapped[int] = mapped_column(BigInteger)
    contract_address: Mapped[str] = mapped_column(String(42))
    expected_escrow_id: Mapped[str] = mapped_column(String(66))
    terms_json: Mapped[str] = mapped_column(Text)
    terms_hash: Mapped[str] = mapped_column(String(66))
    status: Mapped[str] = mapped_column(String(16), server_default="prepared")
    client_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_scan_block: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EscrowTransaction(Base):
    __tablename__ = "escrow_transactions"
    __table_args__ = (
        UniqueConstraint("agreement_id", "tx_hash", name="uq_escrow_tx"),
        CheckConstraint("status IN ('pending', 'confirmed', 'rejected')", name="ck_escrow_tx_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("escrow_agreements.id"))
    tx_hash: Mapped[str] = mapped_column(String(66))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    event: Mapped[str | None] = mapped_column(String(32))
    log_index: Mapped[int | None]
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    block_hash: Mapped[str | None] = mapped_column(String(66))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount_wei: Mapped[str | None] = mapped_column(String(78))
    fee_wei: Mapped[str | None] = mapped_column(String(78))
    error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FreelancerReview(Base):
    __tablename__ = "freelancer_reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_freelancer_reviews_rating"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    rating: Mapped[int]
    comment: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkSubmission(Base):
    __tablename__ = "work_submissions"
    __table_args__ = (CheckConstraint("status IN ('pending', 'revision', 'approved')", name="ck_work_submissions_status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    agreement_id: Mapped[UUID] = mapped_column(ForeignKey("escrow_agreements.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(2048))
    links: Mapped[list[dict[str, str]]] = mapped_column(JSON, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    feedback: Mapped[str | None] = mapped_column(Text)
    work_hash: Mapped[str | None] = mapped_column(String(66))
    chain_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chain_review_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkAttachment(Base):
    __tablename__ = "work_attachments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(ForeignKey("work_submissions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class SupportReport(Base):
    __tablename__ = "support_reports"
    __table_args__ = (
        CheckConstraint("topic IN ('general', 'payment', 'account', 'report')", name="ck_support_reports_topic"),
        CheckConstraint("status IN ('open', 'waiting', 'resolved')", name="ck_support_reports_status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"))
    topic: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupportReportMessage(Base):
    __tablename__ = "support_report_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("support_reports.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    from_admin: Mapped[bool]
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportProjectAccess(Base):
    __tablename__ = "support_project_accesses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("support_reports.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    admin_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('proposal', 'submission', 'message', 'payment', 'job', 'support')", name="ck_notifications_type"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageThread(Base):
    __tablename__ = "message_threads"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    freelancer_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"), index=True)
    client_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    freelancer_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("message_threads.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

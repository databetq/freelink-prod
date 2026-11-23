from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_serializer, model_validator
from pydantic.alias_generators import to_camel

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
# What a client may newly enter for a job budget. Responses keep using Money so a job saved
# before this rule (budget 0) can still be read back.
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Label = Annotated[str, Field(min_length=1, max_length=100)]
BudgetType = Literal["fixed", "hourly"]


def job_date(value):
    if isinstance(value, str) and "T" in value:
        iso_timestamp = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(iso_timestamp).date()
    return value


JobDate = Annotated[date, BeforeValidator(job_date)]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class PublicProfile(ApiModel):
    id: UUID
    name: str


class ClientCard(PublicProfile):
    """A client as other people see them on a job or project: track record only, no contact details.

    `bio`, `title` and `location` stay behind `GET /clients/{id}` (login required), so a public
    job page does not expose them. The track record is null until the endpoint fills it in.
    """

    avatar_color: str | None = None
    jobs_posted: int | None = None
    hire_rate: int | None = None
    # Reviews do not exist yet (see ClientResponse), so these stay 0 until that flow is built.
    rating: float = 0
    reviews: int = 0


class FreelancerCard(PublicProfile):
    """A freelancer as the hiring client or the project counterpart sees them."""

    title: str | None = None
    avatar_color: str | None = None
    skills: list[str] = Field(default_factory=list)
    rating: float = 0
    reviews_count: int = 0
    completed_jobs: int | None = None
    success_rate: int | None = None


class FreelancerReviewCreate(ApiModel):
    project_id: UUID
    rating: Annotated[int, Field(strict=True, ge=1, le=5)]
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]


class FreelancerReviewView(ApiModel):
    id: UUID
    rating: int
    comment: str
    created_at: datetime
    client: ClientCard | None = None


class JobWrite(ApiModel):
    title: Title
    description: Annotated[str, Field(min_length=1, max_length=20000)]
    category: Label
    skills: list[Label] = Field(default_factory=list, max_length=100)
    deliverables: list[Title] = Field(default_factory=list, max_length=100)
    budget_min: Money
    budget_max: Money
    budget_type: BudgetType
    duration: Label
    experience: Label
    deadline: JobDate | None = None

    @model_validator(mode="after")
    def validate_budget(self):
        if self.budget_max < self.budget_min:
            raise ValueError("budgetMax must be greater than or equal to budgetMin")
        return self


class JobCreate(JobWrite):
    budget_min: PositiveMoney
    budget_max: PositiveMoney
    status: Literal["open", "draft"] = "open"


class JobPatch(ApiModel):
    title: Title | None = None
    description: Annotated[str, Field(min_length=1, max_length=20000)] | None = None
    category: Label | None = None
    skills: list[Label] | None = Field(default=None, max_length=100)
    deliverables: list[Title] | None = Field(default=None, max_length=100)
    budget_min: PositiveMoney | None = None
    budget_max: PositiveMoney | None = None
    budget_type: BudgetType | None = None
    duration: Label | None = None
    experience: Label | None = None
    deadline: JobDate | None = None
    status: Literal["open", "draft", "closed"] | None = None

    @model_validator(mode="after")
    def reject_null_fields(self):
        for key in self.model_fields_set - {"deadline"}:
            if getattr(self, key) is None:
                raise ValueError(f"{to_camel(key)} cannot be null")
        return self


class JobResponse(JobWrite):
    project_completed: bool = False
    project_paid: bool = False
    id: UUID
    client_id: UUID
    client: ClientCard
    status: str
    created_at: datetime
    proposals_count: int

    @field_serializer("budget_min", "budget_max")
    def serialize_budget(self, value: Decimal) -> float:
        return float(value)


class ProposalWrite(ApiModel):
    bid_amount: Annotated[Money, Field(gt=0)]
    delivery_days: Annotated[int, Field(ge=1, le=365)]
    cover_letter: Annotated[str, Field(min_length=1, max_length=20000)]
    attachments: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=20
    )


class ProposalPatch(ApiModel):
    status: Literal["pending", "shortlisted", "rejected"]


class ProposalResponse(ProposalWrite):
    id: UUID
    job_id: UUID
    freelancer_id: UUID
    freelancer: FreelancerCard
    job: JobResponse
    status: str
    created_at: datetime

    @field_serializer("bid_amount")
    def serialize_bid(self, value: Decimal) -> float:
        return float(value)


WORK_ATTACHMENT_LIMIT = 5 * 1024 * 1024
WORK_LINK_LIMIT = 10


class WorkAttachmentInput(ApiModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content: Annotated[str, Field(max_length=4 * ((WORK_ATTACHMENT_LIMIT + 2) // 3))]


class WorkLinkInput(ApiModel):
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    url: Annotated[AnyHttpUrl, Field(max_length=2048)]


class WorkSubmissionCreate(ApiModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=20000)]
    link: AnyHttpUrl | None = None
    links: list[WorkLinkInput] = Field(default_factory=list, max_length=WORK_LINK_LIMIT)
    files: list[WorkAttachmentInput] = Field(default_factory=list, max_length=3)


class WorkReviewRequest(ApiModel):
    submission_id: UUID


class WorkRevisionRequest(WorkReviewRequest):
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]


class WorkFileResponse(ApiModel):
    id: UUID
    name: str


class WorkSubmissionResponse(ApiModel):
    work_hash: str | None = None
    chain_submitted_at: datetime | None = None
    chain_review_ends_at: datetime | None = None
    id: UUID
    agreement_id: UUID
    milestone_number: int = 1
    checklist: list[str] = Field(default_factory=list)
    title: str
    description: str
    link: str | None
    links: list[WorkLinkInput] = Field(default_factory=list)
    files: list[WorkFileResponse] = Field(default_factory=list)
    status: Literal["pending", "revision", "approved"]
    revision_limit: int = 0
    revisions_used: int = 0
    feedback: str | None
    submitted_at: datetime


class ProjectResponse(ApiModel):
    id: UUID
    max_work_links: int = WORK_LINK_LIMIT
    job_id: UUID
    client_id: UUID
    freelancer_id: UUID
    title: str
    status: str
    budget: Decimal
    due_date: datetime = Field(validation_alias="due_at")
    created_at: datetime
    # A project starts the moment the client hires, so the start date is its creation time.
    start_date: datetime = Field(validation_alias="created_at")
    # Both parties of the project, so neither page has to look the other side up by id.
    client: ClientCard | None = None
    freelancer: FreelancerCard | None = None
    escrow_status: Literal["unfunded", "pending_verification", "funded", "released", "refunded", "resolved"] = "unfunded"
    escrow_amount: float = 0
    released_amount: float = 0
    milestones: list = Field(default_factory=list)
    submissions: list[WorkSubmissionResponse] = Field(default_factory=list)
    can_submit_work: bool = False
    freelancer_reviewed: bool = False

    @field_serializer("budget")
    def serialize_budget(self, value: Decimal) -> float:
        return float(value)


class HireResponse(ApiModel):
    project: ProjectResponse
    job: JobResponse

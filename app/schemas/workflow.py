from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.roles import validate_role


class AssignReviewerRequest(BaseModel):
    reviewer_id: int = Field(gt=0)


class AcceptReviewRequest(BaseModel):
    confidentiality_accepted: bool


class ReviewRequest(BaseModel):
    recommendation: Literal["approve", "revision", "reject", "practice"]
    comments: str = Field(min_length=2, max_length=12000)
    rubric: dict = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "revision", "reject", "practice"]
    note: str = Field(default="", max_length=12000)


class UserAccessUpdate(BaseModel):
    role: str
    is_active: bool | None = None
    governorate_id: str | None = Field(default=None, max_length=20)
    directorate_id: str | None = Field(default=None, max_length=80)
    school_id: str | None = Field(default=None, max_length=80)
    specialization: str | None = Field(default=None, max_length=150)
    research_field: str | None = Field(default=None, max_length=150)

    @field_validator("role")
    @classmethod
    def role_is_supported(cls, value: str) -> str:
        return validate_role(value)


class AffiliationRequest(BaseModel):
    governorate_id: str | None = Field(default=None, max_length=20)
    directorate_id: str | None = Field(default=None, max_length=80)
    school_id: str | None = Field(default=None, max_length=80)
    specialization: str | None = Field(default=None, max_length=150)
    research_field: str | None = Field(default=None, max_length=150)


class RecommendationStatusRequest(BaseModel):
    status: Literal["new", "under_review", "adopted", "closed"]

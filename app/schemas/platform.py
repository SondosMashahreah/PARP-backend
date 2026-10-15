from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, EmailStr, model_validator
from app.schemas.auth import PASSWORD_RE
from app.domain.roles import validate_role


class PaymentUpdate(BaseModel):
    required_agorot: int = Field(ge=0, le=100000000)
    paid_agorot: int = Field(ge=0, le=100000000)
    confirmed: bool = False
    receipt: str = Field(default="", max_length=250)

    @model_validator(mode="after")
    def complete(self):
        if self.confirmed and self.paid_agorot < self.required_agorot:
            raise ValueError("Full payment is required before confirmation")
        return self


class ConferenceCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    category: str = Field(min_length=2, max_length=150)
    venue: str = Field(min_length=2, max_length=500)
    starts_at: datetime
    ends_at: datetime
    deadline: datetime

    @model_validator(mode="after")
    def dates(self):
        if any(d.tzinfo is None for d in (self.starts_at, self.ends_at, self.deadline)):
            raise ValueError("Include timezone in dates")
        if self.ends_at <= self.starts_at or self.deadline > self.starts_at:
            raise ValueError("Invalid conference dates")
        return self


class ParticipationDecision(BaseModel):
    status: Literal["approved", "revision_requested", "rejected"]
    notes: str = Field(min_length=2, max_length=12000)


class NoticeCreate(BaseModel):
    text: str = Field(min_length=2, max_length=4000)


class AdminUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    role: str
    password: str = Field(min_length=10, max_length=72)

    @model_validator(mode="after")
    def valid(self):
        self.role = validate_role(self.role)
        if self.role == "organizing_committee":
            raise ValueError("Create organizing committee accounts separately")
        if not PASSWORD_RE.fullmatch(self.password):
            raise ValueError("Use uppercase, lowercase, number and symbol")
        return self


class CommitteeLogin(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=72)


class PasswordChange(BaseModel):
    password: str = Field(min_length=10, max_length=72)

    @model_validator(mode="after")
    def strong(self):
        if not PASSWORD_RE.fullmatch(self.password):
            raise ValueError("Use uppercase, lowercase, number and symbol")
        return self


class CommitteeAccountCreate(PasswordChange):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    conference_id: int = Field(gt=0)

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings


PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{10,72}$")


def normalize_allowed_email(value: str) -> str:
    email = value.strip().lower()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if domain != settings.ALLOWED_EMAIL_DOMAIN.lower():
        raise ValueError(f"Email must end with @{settings.ALLOWED_EMAIL_DOMAIN}")
    return email


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("email")
    @classmethod
    def allowed_domain(cls, value: EmailStr) -> str:
        return normalize_allowed_email(str(value))

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not PASSWORD_RE.fullmatch(value):
            raise ValueError(
                "Password must contain uppercase, lowercase, number, symbol, and be at least 10 characters"
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def allowed_domain(cls, value: EmailStr) -> str:
        return normalize_allowed_email(str(value))


class OtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def allowed_domain(cls, value: EmailStr) -> str:
        return normalize_allowed_email(str(value))


class ResendOtpRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def allowed_domain(cls, value: EmailStr) -> str:
        return normalize_allowed_email(str(value))


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_verified: bool
    avatar_url: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse | None = None

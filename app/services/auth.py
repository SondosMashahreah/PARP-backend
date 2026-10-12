from datetime import datetime, timezone

from app.domain.errors import ApplicationError
from app.domain.roles import RESEARCHER, normalize_role
from app.repositories import users
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.infrastructure.email import send_otp_email
from app.services.otp import generate_otp, hash_otp, otp_expiry, verify_otp
from app.infrastructure.minio_storage import presigned_avatar_url


def user_response(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": normalize_role(user.role),
        "is_verified": user.is_verified or not settings.AUTH_REQUIRE_EMAIL_VERIFICATION,
        "avatar_url": presigned_avatar_url(user.avatar_object_name),
    }


def token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": user_response(user),
    }


def issue_otp(db: Session, user: User) -> None:
    otp = generate_otp()
    user.otp_hash = hash_otp(otp)
    user.otp_expires_at = otp_expiry()
    user.otp_attempts = 0
    users.commit(db)
    try:
        send_otp_email(user.email, otp)
    except Exception:
        users.rollback(db)
        raise ApplicationError(status_code=503, detail="Could not send verification email")


def register_user(db: Session, full_name: str, email: str, password: str) -> User:
    user = users.by_email(db, email)
    if user and (user.is_verified or not settings.AUTH_REQUIRE_EMAIL_VERIFICATION):
        raise ApplicationError(status_code=409, detail="Email already registered")

    if user:
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.is_active = True
        if normalize_role(user.role) == RESEARCHER:
            user.role = RESEARCHER
    else:
        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=RESEARCHER,
        )
        users.add(db, user)

    if settings.AUTH_REQUIRE_EMAIL_VERIFICATION:
        issue_otp(db, user)
    else:
        user.is_verified = True
        user.otp_hash = None
        user.otp_expires_at = None
        user.otp_attempts = 0
        users.commit(db)

    users.refresh(db, user)
    return user


def verify_user_email(db: Session, email: str, otp: str) -> User:
    user = users.by_email(db, email)
    now = datetime.now(timezone.utc)

    if not user or user.is_verified or not user.otp_hash or not user.otp_expires_at:
        raise ApplicationError(status_code=400, detail="Invalid or expired verification code")

    expires_at = user.otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now or user.otp_attempts >= 5:
        raise ApplicationError(status_code=400, detail="Invalid or expired verification code")

    if not verify_otp(otp, user.otp_hash):
        user.otp_attempts += 1
        users.commit(db)
        raise ApplicationError(status_code=400, detail="Invalid or expired verification code")

    user.is_verified = True
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    users.commit(db)
    users.refresh(db, user)
    return user


def authenticate(db: Session, email: str, password: str, requested_role: str = RESEARCHER) -> User:
    user = users.by_email(db, email)
    if not user or not user.is_active:
        raise ApplicationError(status_code=401, detail="Invalid email or password")
    if settings.AUTH_REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
        raise ApplicationError(status_code=401, detail="Invalid email or password")
    if not verify_password(password, user.password_hash):
        raise ApplicationError(status_code=401, detail="Invalid email or password")

    if normalize_role(user.role) == "organizing_committee":
        raise ApplicationError(403, "Use committee username login")
    actual_role = normalize_role(user.role)
    if actual_role != requested_role:
        raise ApplicationError(status_code=403, detail="The selected role does not match this account")
    if user.role != actual_role:
        user.role = actual_role
        users.commit(db)
        users.refresh(db, user)
    return user


def resend_verification(db, email):
    if not settings.AUTH_REQUIRE_EMAIL_VERIFICATION:
        return {"message": "Email verification is disabled"}
    user = users.by_email(db, email)
    if user and not user.is_verified:
        issue_otp(db, user)
    return {"message": "If the account is pending, a new code was sent"}


def refresh_tokens(db, refresh_token):
    from app.core.security import decode_token
    payload = decode_token(refresh_token, "refresh")
    if not payload or not str(payload.get("sub", "")).isdigit():
        raise ApplicationError(401, "Invalid or expired refresh token")
    user = users.by_id(db, int(payload["sub"]))
    if not user or not user.is_active or (settings.AUTH_REQUIRE_EMAIL_VERIFICATION and not user.is_verified):
        raise ApplicationError(401, "Invalid account")
    return {"access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id), "token_type": "bearer"}

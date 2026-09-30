from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.services.email import send_otp_email
from app.services.otp import generate_otp, hash_otp, otp_expiry, verify_otp
from app.services.minio_storage import presigned_avatar_url


def user_response(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_verified": user.is_verified,
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
    db.commit()
    try:
        send_otp_email(user.email, otp)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="Could not send verification email")


def register_user(db: Session, full_name: str, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user and user.is_verified:
        raise HTTPException(status_code=409, detail="Email already registered")

    if user:
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.is_active = True
    else:
        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()

    issue_otp(db, user)
    db.refresh(user)
    return user


def verify_user_email(db: Session, email: str, otp: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    now = datetime.now(timezone.utc)

    if not user or user.is_verified or not user.otp_hash or not user.otp_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    expires_at = user.otp_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now or user.otp_attempts >= 5:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    if not verify_otp(otp, user.otp_hash):
        user.otp_attempts += 1
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    user.is_verified = True
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user

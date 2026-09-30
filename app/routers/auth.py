from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.auth import (
    LoginRequest,
    OtpRequest,
    RefreshRequest,
    RegisterRequest,
    ResendOtpRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    authenticate,
    issue_otp,
    register_user,
    token_response,
    user_response,
    verify_user_email,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=202)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    register_user(db, data.full_name, str(data.email), data.password)
    return {"message": "Verification code sent"}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_email(data: OtpRequest, db: Session = Depends(get_db)):
    user = verify_user_email(db, str(data.email), data.otp)
    return token_response(user)


@router.post("/resend-otp", status_code=202)
def resend_otp(data: ResendOtpRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(data.email)).first()
    if not user or user.is_verified:
        # Avoid leaking account state.
        return {"message": "If the account is pending, a new code was sent"}
    issue_otp(db, user)
    return {"message": "If the account is pending, a new code was sent"}


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return token_response(authenticate(db, str(data.email), data.password))


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")
    if not payload or not str(payload.get("sub", "")).isdigit():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active or not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid account")
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return user_response(current_user)

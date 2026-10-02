from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
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
    resend_verification,
    refresh_tokens,
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
    return resend_verification(db, str(data.email))


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return token_response(authenticate(db, str(data.email), data.password))


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_tokens(db, data.refresh_token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return user_response(current_user)

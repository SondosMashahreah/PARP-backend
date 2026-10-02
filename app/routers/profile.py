from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.profile import ProfileUpdateRequest
from app.services import profile

router = APIRouter(prefix="/profile", tags=["Profile"])

@router.patch("/me", response_model=UserResponse)
def update_profile(data: ProfileUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile.update_profile(db, current_user, data.full_name)

@router.post("/avatar", response_model=UserResponse)
async def update_avatar(file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Preserve content-type validation before reading the request body.
    if (file.content_type or "") not in profile.ALLOWED_TYPES:
        from app.domain.errors import ApplicationError
        raise ApplicationError(400, "Only JPG, PNG and WEBP images are allowed")
    data = await file.read(profile.MAX_AVATAR_BYTES + 1)
    return profile.update_avatar(db, current_user, data, file.content_type)

@router.delete("/avatar", response_model=UserResponse)
def remove_avatar(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile.remove_avatar(db, current_user)

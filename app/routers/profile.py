from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.profile import ProfileUpdateRequest
from app.services.auth import user_response
from app.services.minio_storage import delete_object, upload_avatar


router = APIRouter(prefix="/profile", tags=["Profile"])
MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@router.patch("/me", response_model=UserResponse)
def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.full_name = " ".join(data.full_name.split())
    db.commit()
    db.refresh(current_user)
    return user_response(current_user)


@router.post("/avatar", response_model=UserResponse)
async def update_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    extension = ALLOWED_TYPES.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="Only JPG, PNG and WEBP images are allowed")

    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Profile image must be 5 MB or smaller")

    old_object = current_user.avatar_object_name
    current_user.avatar_object_name = upload_avatar(
        current_user.id,
        data,
        file.content_type or "application/octet-stream",
        extension,
    )
    db.commit()
    db.refresh(current_user)
    delete_object(old_object)
    return user_response(current_user)


@router.delete("/avatar", response_model=UserResponse)
def remove_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    old_object = current_user.avatar_object_name
    current_user.avatar_object_name = None
    db.commit()
    db.refresh(current_user)
    delete_object(old_object)
    return user_response(current_user)

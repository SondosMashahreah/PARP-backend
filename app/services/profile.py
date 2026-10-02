from app.domain.errors import ApplicationError
from app.repositories import users
from app.services.auth import user_response
from app.infrastructure.minio_storage import delete_object, upload_avatar

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}



def update_profile(db, current_user, full_name):
    current_user.full_name = " ".join(full_name.split())
    users.commit(db)
    users.refresh(db, current_user)
    return user_response(current_user)


def update_avatar(db, current_user, data, content_type):
    extension = ALLOWED_TYPES.get(content_type or "")
    if not extension:
        raise ApplicationError(status_code=400, detail="Only JPG, PNG and WEBP images are allowed")

    if len(data) > MAX_AVATAR_BYTES:
        raise ApplicationError(status_code=413, detail="Profile image must be 5 MB or smaller")

    old_object = current_user.avatar_object_name
    current_user.avatar_object_name = upload_avatar(
        current_user.id,
        data,
        content_type or "application/octet-stream",
        extension,
    )
    users.commit(db)
    users.refresh(db, current_user)
    delete_object(old_object)
    return user_response(current_user)


def remove_avatar(db, current_user):
    old_object = current_user.avatar_object_name
    current_user.avatar_object_name = None
    users.commit(db)
    users.refresh(db, current_user)
    delete_object(old_object)
    return user_response(current_user)

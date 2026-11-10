from app.domain.errors import ApplicationError
from app.domain.image_processing import sanitize_image, MAX_IMAGE_BYTES
from app.repositories import users
from app.services.auth import user_response
from app.services.identity import set_english_name
from app.infrastructure.minio_storage import delete_object, upload_avatar

MAX_AVATAR_BYTES = MAX_IMAGE_BYTES
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "webp", "image/heif": "webp",
    "image/heic-sequence": "webp", "image/heif-sequence": "webp",
    "image/avif": "webp", "image/gif": "webp",
    "image/bmp": "webp", "image/x-ms-bmp": "webp",
    "image/tiff": "webp", "application/octet-stream": "webp",
}



def update_profile(db, current_user, full_name, full_name_en=None):
    current_user.full_name = " ".join(full_name.split())
    set_english_name(current_user, full_name_en)
    users.commit(db)
    users.refresh(db, current_user)
    return user_response(current_user)


def update_avatar(db, current_user, data, content_type):
    extension = ALLOWED_TYPES.get(content_type or "")
    if not extension:
        raise ApplicationError(status_code=400, detail="Unsupported image type")

    if len(data) > MAX_AVATAR_BYTES:
        raise ApplicationError(status_code=413, detail="Profile image must be 15 MB or smaller")

    # Existing JPG/PNG/WebP behavior is retained for old clients.
    # Other types must decode successfully, then are saved as static WebP.
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        data = sanitize_image(data)
        content_type, extension = "image/webp", "webp"
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

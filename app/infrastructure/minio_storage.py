from datetime import timedelta
from io import BytesIO
from uuid import uuid4

from minio import Minio

from app.core.config import settings


_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


def ensure_bucket() -> None:
    if not _client.bucket_exists(settings.MINIO_BUCKET):
        _client.make_bucket(settings.MINIO_BUCKET)


def upload_avatar(user_id: int, data: bytes, content_type: str, extension: str) -> str:
    ensure_bucket()
    object_name = f"users/{user_id}/avatar-{uuid4().hex}.{extension}"
    _client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def delete_object(object_name: str | None) -> None:
    if not object_name:
        return
    try:
        _client.remove_object(settings.MINIO_BUCKET, object_name)
    except Exception:
        # Replacing a profile photo should not fail only because the previous object is gone.
        pass


def presigned_avatar_url(object_name: str | None) -> str | None:
    if not object_name:
        return None
    return _client.presigned_get_object(
        settings.MINIO_BUCKET,
        object_name,
        expires=timedelta(hours=1),
    )

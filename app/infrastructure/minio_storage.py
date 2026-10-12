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


def _upload(object_name: str, data: bytes, content_type: str) -> str:
    ensure_bucket()
    _client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def upload_avatar(user_id: int, data: bytes, content_type: str, extension: str) -> str:
    object_name = f"users/{user_id}/avatar-{uuid4().hex}.{extension}"
    return _upload(object_name, data, content_type)


def upload_research_file(
    user_id: int,
    submission_id: int,
    version: int,
    data: bytes,
    content_type: str,
    extension: str,
) -> str:
    object_name = (
        f"research/{user_id}/{submission_id}/v{version}-{uuid4().hex}.{extension}"
    )
    return _upload(object_name, data, content_type)


def delete_object(object_name: str | None) -> None:
    if not object_name:
        return
    try:
        _client.remove_object(settings.MINIO_BUCKET, object_name)
    except Exception:
        # Replacing a profile photo should not fail only because the previous object is gone.
        pass


def _presigned_url(object_name: str | None) -> str | None:
    if not object_name:
        return None
    return _client.presigned_get_object(
        settings.MINIO_BUCKET,
        object_name,
        expires=timedelta(hours=1),
    )


def presigned_avatar_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)


def presigned_file_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)



def upload_certificate(user_id: int, data: bytes) -> str:
    return _upload(f"certificates/{user_id}/{uuid4().hex}.pdf", data, "application/pdf")

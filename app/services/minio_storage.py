"""Compatibility imports; implementation lives in app.infrastructure."""
from app.infrastructure.minio_storage import ensure_bucket, upload_avatar, delete_object, presigned_avatar_url  # noqa: F401

"""PARP storage adapter: MinIO locally, Supabase Storage on Render.

Select using STORAGE_BACKEND=minio|supabase.
Supabase newer sb_secret_ keys are sent ONLY as apikey, never a Bearer JWT.
This module preserves the public function names of the original minio_storage.py.
"""
from datetime import timedelta
from functools import lru_cache
from io import BytesIO
from urllib.parse import quote
from uuid import uuid4

import httpx
from minio import Minio

from app.core.config import settings

_BACKEND = settings.STORAGE_BACKEND.strip().lower()
if _BACKEND not in {"minio", "supabase"}:
    raise ValueError("STORAGE_BACKEND must be 'minio' or 'supabase'")


@lru_cache(maxsize=1)
def _minio():
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


@lru_cache(maxsize=1)
def _supabase_http():
    key = settings.SUPABASE_SECRET_KEY.strip()
    url = settings.SUPABASE_URL.rstrip("/")
    if not url.startswith("https://") or not url.endswith(".supabase.co"):
        raise RuntimeError("SUPABASE_URL must be https://PROJECT_REF.supabase.co")
    if not key.startswith("sb_secret_"):
        raise RuntimeError("Set SUPABASE_SECRET_KEY to a valid sb_secret_ key in Render")
    # Non-JWT secret key: do not add an Authorization: Bearer header.
    return httpx.Client(headers={"apikey": key}, timeout=60.0)


def _storage_url(*parts):
    bucket = settings.SUPABASE_STORAGE_BUCKET
    if not bucket:
        raise RuntimeError("SUPABASE_STORAGE_BUCKET must be set")
    return (
        settings.SUPABASE_URL.rstrip("/")
        + "/storage/v1/"
        + "/".join(quote(part, safe="/" if i == len(parts) - 1 else "")
                   for i, part in enumerate(parts))
    )


def _check(response, operation):
    if not response.is_success:
        # Never include credentials or request headers in exception messages.
        raise RuntimeError(f"Supabase Storage {operation} failed: HTTP {response.status_code}; {response.text[:250]}")


def ensure_bucket() -> None:
    if _BACKEND == "minio":
        client = _minio()
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
    # In Supabase create a PRIVATE bucket in its dashboard, once.


def _upload(object_name: str, data: bytes, content_type: str) -> str:
    if _BACKEND == "minio":
        ensure_bucket()
        _minio().put_object(
            settings.MINIO_BUCKET, object_name, BytesIO(data),
            length=len(data), content_type=content_type,
        )
    else:
        response = _supabase_http().post(
            _storage_url("object", settings.SUPABASE_STORAGE_BUCKET, object_name),
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )
        _check(response, "upload")
    return object_name


def upload_avatar(user_id: int, data: bytes, content_type: str, extension: str) -> str:
    return _upload(f"users/{user_id}/avatar-{uuid4().hex}.{extension}", data, content_type)


def upload_research_file(
    user_id: int, submission_id: int, version: int,
    data: bytes, content_type: str, extension: str,
) -> str:
    return _upload(
        f"research/{user_id}/{submission_id}/v{version}-{uuid4().hex}.{extension}",
        data, content_type,
    )


def upload_certificate(user_id: int, data: bytes) -> str:
    return _upload(f"certificates/{user_id}/{uuid4().hex}.pdf", data, "application/pdf")


def delete_object(object_name: str | None) -> None:
    if not object_name:
        return
    try:
        if _BACKEND == "minio":
            _minio().remove_object(settings.MINIO_BUCKET, object_name)
        else:
            response = _supabase_http().request(
                "DELETE", _storage_url("object", settings.SUPABASE_STORAGE_BUCKET),
                json={"prefixes": [object_name]},
            )
            _check(response, "delete")
    except Exception:
        # Match original behavior: a failed cleanup must not fail successful DB changes.
        pass


def _presigned_url(object_name: str | None) -> str | None:
    if not object_name:
        return None
    if _BACKEND == "minio":
        return _minio().presigned_get_object(
            settings.MINIO_BUCKET, object_name,
            expires=timedelta(hours=1),
        )
    response = _supabase_http().post(
        _storage_url("object", "sign", settings.SUPABASE_STORAGE_BUCKET, object_name),
        json={"expiresIn": 3600},
    )
    _check(response, "sign URL")
    data = response.json()
    signed = data.get("signedURL") or data.get("signedUrl")
    if not signed:
        raise RuntimeError("Supabase Storage did not return signedURL")
    if signed.startswith(("https://", "http://")):
        return signed
    if signed.startswith("/storage/v1/"):
        return settings.SUPABASE_URL.rstrip("/") + signed
    if signed.startswith("/object/"):
        return settings.SUPABASE_URL.rstrip("/") + "/storage/v1" + signed
    return settings.SUPABASE_URL.rstrip("/") + "/storage/v1/" + signed.lstrip("/")


def presigned_avatar_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)


def presigned_file_url(object_name: str | None) -> str | None:
    return _presigned_url(object_name)

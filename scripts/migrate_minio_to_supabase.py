"""Copy PARP objects from local MinIO to Supabase Storage (no deletion/overwriting).

Usage from PARP-backend directory:
  python scripts/migrate_minio_to_supabase.py                # preview only
  python scripts/migrate_minio_to_supabase.py --migrate --limit 1
  python scripts/migrate_minio_to_supabase.py --migrate      # full migration

Credentials: local .env for MinIO; SUPABASE_URL and SUPABASE_SECRET_KEY
(or SUPABASE_SERVICE_ROLE_KEY) in environment. Never commit credentials.
"""
import argparse
import hashlib
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from supabase import create_client


def env(name, default=None):
    return os.environ.get(name) or default


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--migrate', action='store_true', help='Copy and verify files; without this, preview only')
    parser.add_argument('--limit', type=int, default=None, help='Process only the first N files for testing')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')

    load_dotenv(Path.cwd() / '.env', override=False)

    endpoint = env('SOURCE_MINIO_ENDPOINT', env('MINIO_ENDPOINT', 'localhost:9000'))
    access = env('SOURCE_MINIO_ACCESS_KEY', env('MINIO_ACCESS_KEY'))
    secret = env('SOURCE_MINIO_SECRET_KEY', env('MINIO_SECRET_KEY'))
    source_bucket = env('SOURCE_MINIO_BUCKET', env('MINIO_BUCKET', 'parp-profile-images'))
    secure = env('SOURCE_MINIO_SECURE', env('MINIO_SECURE', 'false')).lower() == 'true'
    target_bucket = env('TARGET_SUPABASE_BUCKET', env('SUPABASE_STORAGE_BUCKET', 'parp-profile-images'))
    url = env('SUPABASE_URL')
    key = env('SUPABASE_SECRET_KEY', env('SUPABASE_SERVICE_ROLE_KEY'))

    if not access or not secret:
        sys.exit('Missing MinIO credentials. Check local .env or SOURCE_MINIO_ACCESS_KEY / SOURCE_MINIO_SECRET_KEY.')
    if args.migrate and (not url or not key):
        sys.exit('Missing SUPABASE_URL or SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY.')

    source = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
    if not source.bucket_exists(source_bucket):
        sys.exit(f'Local MinIO bucket does not exist: {source_bucket}')

    objects = [o for o in source.list_objects(source_bucket, recursive=True) if not o.is_dir]
    objects.sort(key=lambda o: o.object_name)
    total = len(objects)
    total_bytes = sum(o.size or 0 for o in objects)
    print(f'MinIO source: {endpoint}/{source_bucket}')
    print(f'Supabase target bucket: {target_bucket}')
    print(f'Objects found: {total}; total bytes: {total_bytes:,}')
    if not total:
        print('No objects to copy. Verify you are looking at the intended MinIO bucket.')
        return 1

    selected = objects[:args.limit] if args.limit else objects
    if not args.migrate:
        print('PREVIEW ONLY: Nothing is uploaded, changed or deleted.')
        for item in selected:
            print(f'  {item.object_name} ({item.size or 0:,} bytes)')
        print('Run with --migrate to copy. Use --migrate --limit 1 for a safe first test.')
        return 0

    client = create_client(url, key)
    target = client.storage.from_(target_bucket)
    uploaded = 0
    identical = 0
    failed = 0

    for i, obj in enumerate(selected, 1):
        name = obj.object_name
        response = None
        try:
            response = source.get_object(source_bucket, name)
            data = response.read()
        except Exception as e:
            failed += 1
            print(f'[{i}/{len(selected)}] FAILED read: {name}: {e}')
            continue
        finally:
            if response is not None:
                response.close()
                response.release_conn()

        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        try:
            target.upload(
                path=name,
                file=data,
                file_options={'content-type': content_type, 'upsert': 'false'},
            )
            was_uploaded = True
        except Exception as upload_error:
            # Do NOT overwrite. If file already exists, confirm identical bytes.
            was_uploaded = False
            try:
                actual = target.download(name)
            except Exception:
                failed += 1
                print(f'[{i}/{len(selected)}] FAILED upload: {name}: {upload_error}')
                continue
            if sha256(actual) != sha256(data):
                failed += 1
                print(f'[{i}/{len(selected)}] CONFLICT: {name} exists in Supabase with different content; left unchanged')
                continue

        if was_uploaded:
            try:
                actual = target.download(name)
                if sha256(actual) != sha256(data):
                    raise RuntimeError('SHA-256 mismatch')
                uploaded += 1
                print(f'[{i}/{len(selected)}] COPIED + VERIFIED: {name}')
            except Exception as e:
                failed += 1
                print(f'[{i}/{len(selected)}] FAILED verification: {name}: {e}')
        else:
            identical += 1
            print(f'[{i}/{len(selected)}] ALREADY IDENTICAL: {name}')

    print(f'Finished: {uploaded} copied + verified, {identical} already identical, {failed} failed; of {len(selected)} examined.')
    print('Original MinIO files were not modified or deleted.')
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'Migration stopped: {exc}', file=sys.stderr)
        sys.exit(1)

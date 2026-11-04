"""Safe, copy-only MinIO -> Supabase Storage migration for PARP.

Supabase's new sb_secret_ API key is sent only as `apikey` (never as a
Bearer JWT). Run from PARP-backend:

  python scripts/migrate_minio_to_supabase.py
  python scripts/migrate_minio_to_supabase.py --migrate --limit 1
  python scripts/migrate_minio_to_supabase.py --migrate

Requires: pip install minio python-dotenv httpx
Environment: .env for local MinIO; SUPABASE_URL and SUPABASE_SECRET_KEY
(or SUPABASE_SERVICE_ROLE_KEY) for the Supabase project. Never commit keys.
"""
import argparse
import hashlib
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from minio import Minio


def env(name, default=None):
    return os.environ.get(name) or default


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def urljoin_path(base, *segments):
    # Keep folder separators in object names but URL-encode special characters.
    parts = [quote(segment, safe='/' if i == len(segments) - 1 else '') for i, segment in enumerate(segments)]
    return base.rstrip('/') + '/storage/v1/' + '/'.join(parts)


def check_response(response, label):
    if not response.is_success:
        # Never output headers: they contain the secret key.
        raise RuntimeError(f'{label}: HTTP {response.status_code}; {response.text[:450]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--migrate', action='store_true', help='Copy and verify; defaults to preview')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of items processed')
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
        sys.exit('Missing local MinIO credentials; check your .env')
    if args.migrate and (not url or not key):
        sys.exit('Missing SUPABASE_URL or SUPABASE_SECRET_KEY')
    if args.migrate and not key.strip().startswith('sb_secret_'):
        sys.exit('Expected a current sb_secret_ key in SUPABASE_SECRET_KEY. Copy from Supabase > Settings > API Keys > Secret Keys. Do NOT paste it into chat.')
    if args.migrate and ('/rest/v1' in url or '/storage/v1' in url):
        sys.exit('SUPABASE_URL must be just https://PROJECT_REF.supabase.co (no API path).')

    source = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
    if not source.bucket_exists(source_bucket):
        sys.exit(f'MinIO bucket not found: {source_bucket}')
    objects = sorted(
        [o for o in source.list_objects(source_bucket, recursive=True) if not o.is_dir],
        key=lambda item: item.object_name,
    )
    total_size = sum(o.size or 0 for o in objects)
    print(f'MinIO source: {endpoint}/{source_bucket}')
    print(f'Supabase target bucket: {target_bucket}')
    print(f'Objects found: {len(objects)}; total bytes: {total_size:,}')
    if not objects:
        print('No objects found. Check the source bucket.')
        return 1
    selected = objects[:args.limit] if args.limit else objects
    if not args.migrate:
        print('PREVIEW ONLY: Nothing is uploaded, changed or deleted.')
        for obj in selected:
            print(f'  {obj.object_name} ({obj.size or 0:,} bytes)')
        return 0

    print('Authentication: Supabase sb_secret_ via apikey header only (no Bearer JWT).')
    copied = identical = failed = 0
    with httpx.Client(headers={'apikey': key.strip()}, timeout=90, follow_redirects=False) as http:
        for i, obj in enumerate(selected, 1):
            name = obj.object_name
            response = None
            try:
                response = source.get_object(source_bucket, name)
                data = response.read()
            except Exception as exc:
                failed += 1
                print(f'[{i}/{len(selected)}] FAILED read: {name}: {exc}')
                continue
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

            mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            upload_url = urljoin_path(url, 'object', target_bucket, name)
            download_url = urljoin_path(url, 'object', 'authenticated', target_bucket, name)
            try:
                upload = http.post(
                    upload_url, content=data,
                    headers={'Content-Type': mime, 'x-upsert': 'false'},
                )
                if upload.is_success:
                    download = http.get(download_url)
                    check_response(download, 'Verify download')
                    if sha256(download.content) != sha256(data):
                        raise RuntimeError('SHA-256 mismatch after upload')
                    copied += 1
                    print(f'[{i}/{len(selected)}] COPIED + VERIFIED: {name}')
                    continue

                # No overwrite: if the upload failed because file already exists,
                # only accept it when the existing content is byte-for-byte identical.
                download = http.get(download_url)
                if download.is_success:
                    if sha256(download.content) == sha256(data):
                        identical += 1
                        print(f'[{i}/{len(selected)}] ALREADY IDENTICAL: {name}')
                    else:
                        failed += 1
                        print(f'[{i}/{len(selected)}] CONFLICT: {name} differs on Supabase; skipped')
                else:
                    failed += 1
                    print(f'[{i}/{len(selected)}] FAILED upload: {name}: HTTP {upload.status_code}; {upload.text[:400]}')
            except Exception as exc:
                failed += 1
                print(f'[{i}/{len(selected)}] FAILED transfer: {name}: {exc}')

    print(f'Finished: {copied} copied + verified, {identical} already identical, {failed} failed; of {len(selected)} examined.')
    print('Original MinIO files were not modified or deleted.')
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'Migration stopped: {exc}', file=sys.stderr)
        sys.exit(1)

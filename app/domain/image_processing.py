"""Validate real image bytes and normalize user uploads to safe static WebP.

Pillow validates the decoded data, not a spoofable filename or Content-Type.
Pillow-HEIF registers HEIC/HEIF (and AVIF where supported) decoders.
"""
import warnings
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from app.domain.errors import ApplicationError

register_heif_opener()
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
SUPPORTED = {'PNG', 'JPEG', 'WEBP', 'GIF', 'BMP', 'TIFF', 'HEIF', 'AVIF'}


def sanitize_image(data: bytes) -> bytes:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ApplicationError(422, 'Image must be at most 15 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in SUPPORTED or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Unsupported image format or dimensions')
                image.seek(0)  # Animated GIF/WebP uploads become a static first frame.
                image.load()
                image = ImageOps.exif_transpose(image)
                image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                out = BytesIO()
                image.save(out, 'WEBP', quality=86, method=5)
                return out.getvalue()
    except (UnidentifiedImageError, ValueError, OSError, EOFError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ApplicationError(422, 'Invalid or unsupported image. Use JPEG, PNG, WebP, HEIC/HEIF, GIF, BMP, TIFF or supported AVIF.') from exc

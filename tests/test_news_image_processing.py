"""Image sanitizer tests run without storage, API or production database."""
import unittest
from io import BytesIO
from PIL import Image
from app.domain.errors import ApplicationError
from app.domain.image_processing import sanitize_image, MAX_IMAGE_BYTES

class NewsImageProcessingTests(unittest.TestCase):
    def sample(self, fmt):
        b = BytesIO()
        Image.new('RGB', (32,24), (18,66,124)).save(b,format=fmt)
        return b.getvalue()

    def test_common_formats_are_normalized_to_webp(self):
        for fmt in ('PNG','JPEG','GIF','BMP','TIFF','WEBP'):
            with self.subTest(format=fmt):
                encoded = sanitize_image(self.sample(fmt))
                with Image.open(BytesIO(encoded)) as img:
                    self.assertEqual(img.format,'WEBP')
                    self.assertEqual(img.size,(32,24))

    def test_invalid_or_too_large_images_cannot_be_stored(self):
        for payload in (b'',b'<svg><script/></svg>',b'not an image',b'\0' * (MAX_IMAGE_BYTES+1)):
            with self.subTest(size=len(payload)):
                with self.assertRaises(ApplicationError) as context:
                    sanitize_image(payload)
                self.assertEqual(context.exception.status_code,422)

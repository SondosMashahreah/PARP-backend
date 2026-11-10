import unittest
from app.schemas.auth import RegisterRequest
from app.schemas.platform import AdminUserCreate
from app.models.user import User, UserNameTranslation
from app.services.identity import set_english_name

class InstitutionalNamesTests(unittest.TestCase):
    def test_bilingual_names_are_distinct_and_legacy_name_is_preserved(self):
        user = User(full_name='سندس', email='s@example.com', password_hash='x', role='researcher')
        self.assertIsNone(user.name_translation)
        set_english_name(user, 'Sondos Mashahreah')
        self.assertIsInstance(user.name_translation, UserNameTranslation)
        self.assertEqual(user.name_translation.full_name_en, 'Sondos Mashahreah')
        self.assertEqual(user.full_name, 'سندس')

    def test_registration_and_admin_payload_accept_canonical_ids(self):
        data = RegisterRequest(full_name='سندس', full_name_en='Sondos', email='s@meo.edu.ps',
                               password='StrongPass1!', directorate_id='d1', school_id='s1')
        self.assertEqual(data.school_id, 's1')
        admin = AdminUserCreate(full_name='سندس', full_name_en='Sondos', email='s@meo.edu.ps',
                                password='StrongPass1!', role='researcher', directorate_id='d1', school_id='s1')
        self.assertEqual(admin.directorate_id, 'd1')

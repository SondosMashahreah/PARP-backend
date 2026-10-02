"""Regression checks using an isolated database and mocked external adapters."""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only-unused-secret')
os.environ.setdefault('DEBUG', 'false')
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import create_refresh_token
from app.domain.errors import ApplicationError
from app.services import auth, profile, education
from scripts.import_education import TABLES, import_data

class LayerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        User.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.user = User(full_name='Test User', email='test@example.test', password_hash='unused', is_active=True, is_verified=True)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_profile_and_avatar_workflow(self):
        with patch('app.services.auth.presigned_avatar_url', return_value='test-avatar'), patch('app.services.profile.upload_avatar', return_value='new-object') as upload, patch('app.services.profile.delete_object') as delete:
            result = profile.update_profile(self.db, self.user, '  Updated   Name ')
            self.assertEqual(result['full_name'], 'Updated Name')
            self.user.avatar_object_name = 'old-object'
            profile.update_avatar(self.db, self.user, b'example', 'image/png')
            upload.assert_called_once_with(self.user.id, b'example', 'image/png', 'png')
            delete.assert_called_once_with('old-object')
            self.assertEqual(self.user.avatar_object_name, 'new-object')
            profile.remove_avatar(self.db, self.user)
            self.assertIsNone(self.user.avatar_object_name)
            delete.assert_called_with('new-object')

    def test_avatar_limits_and_refresh_errors(self):
        for data, mime, code in [(b'x', 'text/plain', 400), (b'x' * (profile.MAX_AVATAR_BYTES + 1), 'image/png', 413)]:
            with self.assertRaises(ApplicationError) as error:
                profile.update_avatar(self.db, self.user, data, mime)
            self.assertEqual(error.exception.status_code, code)
        token = create_refresh_token(self.user.id)
        self.assertEqual(auth.refresh_tokens(self.db, token)['token_type'], 'bearer')
        self.user.is_active = False
        self.db.commit()
        with self.assertRaises(ApplicationError) as error:
            auth.refresh_tokens(self.db, token)
        self.assertEqual(error.exception.status_code, 401)
        with self.assertRaises(ApplicationError):
            auth.refresh_tokens(self.db, 'invalid')

    def test_resend_does_not_leak_account_state(self):
        with patch('app.services.auth.issue_otp') as issue:
            missing = auth.resend_verification(self.db, 'missing@example.test')
            verified = auth.resend_verification(self.db, self.user.email)
            issue.assert_not_called()
            self.user.is_verified = False
            self.db.commit()
            pending = auth.resend_verification(self.db, self.user.email)
            issue.assert_called_once_with(self.db, self.user)
            self.assertEqual(missing, verified)
            self.assertEqual(verified, pending)

    def test_directory_and_bbox(self):
        for table in TABLES:
            table.create(self.engine)
        import_data(self.db)
        self.db.commit()
        catalog = education.catalog(self.db)
        first = education.schools({}, 0, 10, self.db)
        self.assertEqual(catalog['total_schools'], first['total'])
        self.assertEqual(len(first['items']), 10)
        row = first['items'][0]
        self.assertEqual(education.school_detail(row['id'], self.db), row)
        self.assertEqual(education.school_points('34,29,37,34', {}, 100, self.db)['type'], 'FeatureCollection')
        for bbox in ['bad', 'nan,29,37,34', '37,29,34,34']:
            with self.assertRaises(ApplicationError) as error:
                education.parse_bbox(bbox)
            self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(ApplicationError) as error:
            education.school_detail('missing', self.db)
        self.assertEqual(error.exception.status_code, 404)

if __name__ == '__main__':
    unittest.main()

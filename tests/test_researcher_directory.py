"""New ARDS-linked authors resolve only through approved platform affiliation."""
import os
import unittest

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only')
os.environ.setdefault('DEBUG', 'false')

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app  # noqa: F401 - register ORM models
from app.core.database import Base
from app.domain.errors import ApplicationError
from app.models.education import Directorate, School
from app.models.user import User
from app.models.workflow import UserAffiliation
from app.services.researcher_directory import own_profile, search_profiles, canonicalize_linked_researchers


class ResearcherDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Directorate(id='d1', name_ar='مديرية نابلس', name_en='Nablus Directorate', search_text='', category='public', source_url='', source_date='2026'))
        self.db.add(School(id='s1', national_code='123', name_ar='مدرسة مثال', name_en='Example School', search_text='', school_type='public', directorate_id='d1', region='PS01', source_row=1, source_values={}))
        self.db.add_all([
            User(full_name='Researcher One', email='one@example.test', password_hash='unused', role='researcher', is_active=True, is_verified=True),
            User(full_name='Researcher Two', email='two@example.test', password_hash='unused', role='researcher', is_active=True, is_verified=True),
            User(full_name='Inactive', email='inactive@example.test', password_hash='unused', role='researcher', is_active=False, is_verified=True),
        ])
        self.db.commit()
        self.owner = self.db.query(User).filter_by(email='one@example.test').one()
        self.coauthor = self.db.query(User).filter_by(email='two@example.test').one()
        self.db.add_all([
            UserAffiliation(user_id=self.owner.id, school_id='s1', directorate_id='d1', approval_status='approved'),
            UserAffiliation(user_id=self.coauthor.id, school_id='s1', directorate_id='d1', approval_status='requested'),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_search_returns_only_approved_linked_accounts(self):
        self.assertEqual(own_profile(self.db, self.owner)['researcher']['school_id'], 's1')
        self.assertEqual(len(search_profiles(self.db, self.owner, 'Researcher')['items']), 1)
        self.assertEqual(search_profiles(self.db, self.owner, 'Researcher')['items'][0]['user_id'], self.owner.id)
        self.assertNotIn('email', search_profiles(self.db, self.owner, 'Researcher')['items'][0])

    def test_submitted_data_uses_server_affiliations_not_client_text(self):
        content = {'kind': 'research', 'researchers_mode': 'linked', 'researchers': [
            {'user_id': self.owner.id, 'full_name': 'Fake name', 'school': 'Fake School', 'directorate': 'Fake Directorate'}]}
        data = canonicalize_linked_researchers(self.db, self.owner, content)
        self.assertEqual(data['researchers'][0]['school'], 'مدرسة مثال')
        self.assertEqual(data['researchers'][0]['directorate'], 'مديرية نابلس')
        self.assertEqual(data['researchers'][0]['full_name'], 'Researcher One')
        self.assertEqual(content['researchers'][0]['school'], 'Fake School')
        with self.assertRaises(ApplicationError):
            canonicalize_linked_researchers(self.db, self.owner, {**content, 'researchers': [{'user_id': self.coauthor.id}]})
        with self.assertRaises(ApplicationError):
            canonicalize_linked_researchers(self.db, self.owner, {**content, 'researchers': [{'user_id': self.owner.id}, {'user_id': self.owner.id}]})

    def test_unlinked_legacy_authors_still_load(self):
        old = {'standard_version': 'ARDS-1.0', 'researchers': [{'full_name':'Historical author', 'school':'Historical school','directorate':'Historical directorate'}]}
        self.assertIs(canonicalize_linked_researchers(self.db, self.owner, old), old)


if __name__ == '__main__':
    unittest.main()

"""A public reader can download published research, never drafts or unpublished files."""
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.main import app  # noqa: F401 - load all SQLAlchemy models
from app.core.database import Base
from app.domain.errors import ApplicationError
from app.models.user import User
from app.models.workflow import ResearchSubmission, ResearchVersion
from app.services.workflow import published_research_file_url


class PublicResearchFileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        author = User(full_name='Author', email='v13@example.test', password_hash='unused', role='researcher')
        self.db.add(author)
        self.db.flush()
        self.author_id = author.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def record(self, kind='research', status='published', version=True):
        row = ResearchSubmission(researcher_id=self.author_id, title='Sample study', research_field='Math', problem='Issue', status=status, publication_type=kind)
        self.db.add(row)
        self.db.flush()
        if version:
            self.db.add(ResearchVersion(submission_id=row.id, version_number=1, file_object_name='research/test/sample.pdf', original_file_name='sample.pdf', content_type='application/pdf', form_data={}))
            self.db.flush()
        return row

    def test_published_research_gets_a_fresh_signed_url(self):
        row = self.record()
        with patch('app.services.workflow.presigned_file_url', return_value='https://example.test/signed') as signed:
            self.assertEqual(published_research_file_url(self.db, row.id), 'https://example.test/signed')
            signed.assert_called_once_with('research/test/sample.pdf')

    def test_unpublished_and_practices_do_not_expose_files(self):
        ids = [self.record(status='approved').id, self.record(status='under_review').id, self.record(kind='practice').id, self.record(version=False).id]
        with patch('app.services.workflow.presigned_file_url') as signed:
            for identifier in ids + [999999]:
                with self.assertRaises(ApplicationError) as error:
                    published_research_file_url(self.db, identifier)
                self.assertEqual(error.exception.status_code, 404)
            signed.assert_not_called()


if __name__ == '__main__':
    unittest.main()

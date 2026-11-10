"""ARDS integration smoke test: drafts, publication privacy, and revised version metadata."""
import json
import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'testing-only-key'
os.environ['DEBUG'] = 'false'

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from app.main import app  # noqa: F401,E402 - import registers all models
from app.core.database import Base  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workflow import UserAffiliation, ResearchSubmission, ResearchVersion  # noqa: E402
from app.schemas.researcher import DraftContent  # noqa: E402
from app.services import researcher, workflow  # noqa: E402


class ActionResearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.author = User(full_name='Lead teacher', email='lead@example.test', password_hash='unused', role='researcher', is_active=True, is_verified=True)
        self.db.add(self.author)
        self.db.commit()
        self.db.add(UserAffiliation(user_id=self.author.id, school_id='example-school', directorate_id='example-directorate', approval_status='approved'))
        self.db.commit()
        self.patches = [patch('app.services.workflow.upload_research_file', return_value='mocked-object'),
                        patch('app.services.workflow.presigned_file_url', return_value='https://example.test/file')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.db.close()
        self.engine.dispose()

    def example(self):
        return DraftContent(
            kind='research', standard_version='ARDS-1.0', title='Action research',
            research_field='Mathematics', problem='Problem statement', abstract='Public summary',
            keywords='education, drama', research_question='What was the effect?',
            researchers=[{'full_name': 'Lead teacher', 'school': 'School One', 'directorate': 'Dir One'},
                         {'full_name': 'Partner teacher', 'school': 'School Two', 'directorate': 'Dir Two'}],
            research_objectives=['Improve learning'], sample_size=33,
            intervention='Use drama', action_plan_steps=[{'activity': 'Run group activities'}],
            research_instruments=[{'name': 'Observation checklist'}],
            key_findings='Students improved', researcher_reflection='Better class engagement',
            conclusions='Drama supported learning', recommendations='Continue to adapt lessons',
        )

    def test_versions_keep_coauthor_affiliations_and_public_access_is_safe(self):
        draft = researcher.create_draft(self.db, self.author, self.example())
        submitted = researcher.submit_draft(self.db, self.author, draft['id'], 1,
                                            'paper.pdf', 'application/pdf', b'%PDF-test')
        self.assertEqual(submitted['standard_version'], 'ARDS-1.0')
        self.assertEqual(len(submitted['researchers']), 2)
        self.assertEqual(submitted['standard_data']['researchers'][1]['directorate'], 'Dir Two')
        self.assertEqual(submitted['keywords'], ['education', 'drama'])

        row = self.db.get(ResearchSubmission, submitted['id'])
        row.status = 'rejected'
        self.db.commit()
        revised = workflow.resubmit(self.db, self.author, row.id,
                                     form_json=json.dumps({'title': 'Revised research'}),
                                     file_name='revised.pdf', content_type='application/pdf',
                                     file_bytes=b'%PDF-new')
        self.assertEqual(revised['current_version'], 2)
        self.assertEqual(revised['standard_data']['researchers'][0]['school'], 'School One')
        self.assertEqual(self.db.query(ResearchVersion).filter_by(submission_id=row.id).count(), 2)

        row.status = 'published'
        self.db.commit()
        public = workflow.public_repository(self.db, 'research')[0]
        self.assertEqual(public['researchers'][1]['directorate'], 'Dir Two')
        self.assertIsNone(public['standard_data'])
        self.assertIsNone(public['file'])
        self.assertIsNone(public['problem'])


if __name__ == '__main__':
    unittest.main()

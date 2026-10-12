import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'test-secret-not-used-in-production'
os.environ['DEBUG'] = 'false'
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.models.workflow import UserAffiliation, ResearchSubmission, ResearchVersion
from app.models.researcher import ResearchDraft
from app.schemas.researcher import DraftContent, DraftSave, ProgressSave
from app.services import researcher, workflow
from app.domain.errors import ApplicationError
from app.routers.dependencies import get_current_user

class ResearcherWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(full_name='Owner', email='owner@example.test', password_hash='unused', role='researcher', is_active=True, is_verified=True)
        self.other = User(full_name='Other', email='other@example.test', password_hash='unused', role='researcher', is_active=True, is_verified=True)
        self.staff = User(full_name='Staff', email='staff@example.test', password_hash='unused', role='organizing_committee', is_active=True, is_verified=True)
        self.db.add_all([self.owner,self.other,self.staff]);self.db.commit()
        self.db.add(UserAffiliation(user_id=self.owner.id, school_id='synthetic-school', directorate_id='synthetic-directorate', approval_status='approved'));self.db.commit()
        self.content = DraftContent(title='Research title',research_field='Education',problem='Classroom problem',abstract='Research abstract')
        self.patches = [patch('app.services.workflow.upload_research_file', return_value='test-object'), patch('app.services.workflow.presigned_file_url', return_value='https://example.test/file')]
        for p in self.patches:p.start()
    def tearDown(self):
        app.dependency_overrides.clear()
        for p in self.patches:p.stop()
        self.db.close();self.engine.dispose()
    def test_draft_ownership_revision_and_permissions(self):
        draft=researcher.create_draft(self.db,self.owner,self.content)
        with self.assertRaises(ApplicationError) as e:researcher.save_draft(self.db,self.other,draft['id'],DraftSave(content=self.content,revision=1))
        self.assertEqual(e.exception.status_code,404)
        saved=researcher.save_draft(self.db,self.owner,draft['id'],DraftSave(content=self.content,revision=1))
        self.assertEqual(saved['revision'],2)
        with self.assertRaises(ApplicationError) as e:researcher.save_draft(self.db,self.owner,draft['id'],DraftSave(content=self.content,revision=1))
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(ApplicationError) as e:researcher.overview(self.db,self.staff)
        self.assertEqual(e.exception.status_code,403)
    def test_submit_is_idempotent_and_rejection_can_be_revised(self):
        draft=researcher.create_draft(self.db,self.owner,self.content)
        first=researcher.submit_draft(self.db,self.owner,draft['id'],1,'paper.pdf','application/pdf',b'%PDF-1.7 test')
        again=researcher.submit_draft(self.db,self.owner,draft['id'],1,'paper.pdf','application/pdf',b'%PDF-1.7 test')
        self.assertEqual(first['id'],again['id']);self.assertTrue(again['already_submitted'])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ResearchSubmission)),1)
        self.assertEqual(researcher.overview(self.db,self.owner)['drafts'],[])
        row=self.db.get(ResearchSubmission,first['id']);row.status='rejected';self.db.commit()
        revised=workflow.resubmit(self.db,self.owner,row.id,form_json='{"title":"Revised title","problem":"Revised problem"}',file_name='revised.pdf',content_type='application/pdf',file_bytes=b'%PDF-test')
        self.assertEqual(revised['status'],'submitted');self.assertEqual(revised['title'],'Revised title');self.assertEqual(revised['current_version'],2)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ResearchVersion)),2)
        with self.assertRaises(ApplicationError):workflow.resubmit(self.db,self.other,row.id,form_json='{}',file_name='x.pdf',content_type='application/pdf',file_bytes=b'%PDF-test')
    def test_training_and_certificates_are_private_and_staff_managed(self):
        progress=ProgressSave(course_key='course-1',title='Research methods',completed=2,total=5)
        with self.assertRaises(ApplicationError):researcher.record_progress(self.db,self.owner,self.owner.id,progress)
        researcher.record_progress(self.db,self.staff,self.owner.id,progress)
        self.assertEqual(researcher.overview(self.db,self.owner)['training'][0]['completed'],2)
        self.assertEqual(researcher.overview(self.db,self.other)['training'],[])
        with patch('app.services.researcher.upload_certificate',return_value='certificate.pdf'),patch('app.services.researcher.presigned_file_url',return_value='https://example.test/certificate'):
            researcher.issue_certificate(self.db,self.staff,self.owner.id,'Completion','PARP',b'%PDF-test')
            self.assertEqual(len(researcher.overview(self.db,self.owner)['certificates']),1)
            self.assertEqual(researcher.overview(self.db,self.other)['certificates'],[])
        with self.assertRaises(ValueError):ProgressSave(course_key='c',title='test',completed=6,total=5)
    def test_http_auth_validation_and_owner_scope(self):
        def db_override():yield self.db
        app.dependency_overrides[get_db]=db_override
        client=TestClient(app)
        self.assertEqual(client.get('/api/researcher/me').status_code,401)
        app.dependency_overrides[get_current_user]=lambda:self.owner
        created=client.post('/api/researcher/drafts',json=self.content.model_dump())
        self.assertEqual(created.status_code,201)
        self.assertEqual(client.post('/api/researcher/drafts',json={'title':'x'*501}).status_code,422)
        app.dependency_overrides[get_current_user]=lambda:self.other
        self.assertEqual(client.put('/api/researcher/drafts/'+str(created.json()['id']),json={'revision':1,'content':self.content.model_dump()}).status_code,404)
        app.dependency_overrides[get_current_user]=lambda:self.staff
        self.assertEqual(client.get('/api/researcher/me').status_code,403)
        client.close()

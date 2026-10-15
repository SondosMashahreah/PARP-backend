import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'excellence-test-only'
os.environ['DEBUG'] = 'false'
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.database import Base, get_db
from app.routers.dependencies import get_current_user
from app.models.user import User
from app.models.platform import Conference
from app.models.workflow import ResearchSubmission
from app.models.excellence import ExcellenceEntry
from app.services.excellence import sanitize_image
from app.domain.errors import ApplicationError

class ExcellenceTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.admin=User(full_name='Admin',email='admin@test.ps',password_hash='test',role='system_admin',is_active=True)
        self.teacher=User(full_name='Researcher',email='teacher@test.ps',password_hash='test',role='researcher',is_active=True)
        self.db.add_all([self.admin,self.teacher]);self.db.flush()
        at=datetime(2026,10,15,tzinfo=timezone.utc)
        self.conference=Conference(title='مؤتمر التعليم',category='Education',venue='School',starts_at=at,ends_at=at,deadline=at,created_by=self.admin.id)
        self.research=ResearchSubmission(researcher_id=self.teacher.id,title='التعلم التعاوني',title_en='Cooperative learning',abstract='This is the public abstract.',problem='PRIVATE TEXT',research_field='Education',status='published',publication_type='research')
        self.db.add_all([self.conference,self.research]);self.db.commit()
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_current_user]=lambda:self.admin
        self.storage=patch('app.services.excellence._upload',return_value='object');self.storage.start()
        self.cleanup=patch('app.services.excellence.delete_object');self.cleanup.start()
        self.url=patch('app.services.excellence.presigned_avatar_url',side_effect=lambda name:'https://storage.test/photo.webp' if name else None);self.url.start()
        self.client=TestClient(app)
    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.storage.stop();self.cleanup.stop();self.url.stop();self.db.close();self.engine.dispose()
    def payload(self,**changes):
        return dict(name_ar='سندس',name_en='Sondos',conference_id=self.conference.id,submission_id=self.research.id,conference_title_en='Education Conference',visible=False,sort_order=0,**changes)
    def create(self):
        response=self.client.post('/api/excellence/admin',json=self.payload());self.assertEqual(response.status_code,201,response.text);return response.json()['id']
    def png(self):
        output=BytesIO();Image.new('RGBA',(32,32),(100,50,150,120)).save(output,format='PNG');return output.getvalue()
    def publish(self,id):
        self.assertEqual(self.client.post(f'/api/excellence/admin/{id}/image',files={'file':('photo.png',self.png(),'image/png')}).status_code,200)
        payload=self.payload();payload['visible']=True
        self.assertEqual(self.client.put(f'/api/excellence/admin/{id}',json=payload).status_code,200)
    def test_full_lifecycle_filters_abstract_and_delete_preserve_research(self):
        id=self.create();self.assertEqual(self.client.get('/api/excellence').json()['total'],0)
        self.publish(id)
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/api/excellence?q=Sondos&year=2026').json()['total'],1)
        self.assertEqual(self.client.get('/api/excellence?q=سندس').json()['total'],1)
        self.assertEqual(self.client.get('/api/excellence?q=learning').json()['total'],1)
        self.assertEqual(self.client.get('/api/excellence?year=2025').json()['total'],0)
        self.assertEqual(self.client.get('/api/excellence?q=%25').json()['total'],0)
        data=self.client.get(f'/api/excellence/{id}/abstract').json()
        self.assertEqual(data['abstract'],self.research.abstract)
        self.assertNotIn('problem',data);self.assertNotIn('file',data)
        self.assertEqual(self.client.get('/api/excellence/filters').json()['years'],[2026])
        app.dependency_overrides[get_current_user]=lambda:self.admin
        self.assertEqual(self.client.delete(f'/api/excellence/admin/{id}').status_code,200)
        self.assertIsNotNone(self.db.get(ResearchSubmission,self.research.id))
        self.assertEqual(self.client.get(f'/api/excellence/{id}/abstract').status_code,404)
    def test_only_admin_can_write_or_list_private_entries(self):
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/api/excellence/admin').status_code,401)
        app.dependency_overrides[get_current_user]=lambda:self.teacher
        self.assertEqual(self.client.post('/api/excellence/admin',json=self.payload()).status_code,403)
        self.assertEqual(self.client.get('/api/excellence/admin/research').status_code,403)
        self.assertEqual(self.client.post('/api/excellence/admin/1/image',files={'file':('p.png',self.png(),'image/png')}).status_code,403)
    def test_visibility_requires_portrait_and_published_abstract_and_unique_entry(self):
        payload=self.payload();payload['visible']=True
        self.assertEqual(self.client.post('/api/excellence/admin',json=payload).status_code,422)
        id=self.create()
        self.assertEqual(self.client.post('/api/excellence/admin',json=self.payload()).status_code,409)
        self.publish(id)
        self.research.status='under_review';self.db.commit()
        self.assertEqual(self.client.get('/api/excellence').json()['total'],0)
        self.assertEqual(self.client.get(f'/api/excellence/{id}/abstract').status_code,404)
        self.assertEqual(self.client.get('/api/excellence/filters').json()['years'],[])
        self.assertEqual(self.client.put(f'/api/excellence/admin/{id}',json=payload).status_code,422)
    def test_invalid_images_and_missing_references_rejected(self):
        id=self.create()
        self.assertEqual(self.client.post(f'/api/excellence/admin/{id}/image',files={'file':('p.png',b'<svg onload="bad"/>','image/png')}).status_code,422)
        clean=sanitize_image(self.png())
        with Image.open(BytesIO(clean)) as image:self.assertEqual(image.format,'WEBP');self.assertEqual(image.mode,'RGBA')
        with self.assertRaises(ApplicationError):sanitize_image(b'x'*(5*1024*1024+1))
        payload=self.payload();payload['conference_id']=999
        self.assertEqual(self.client.put(f'/api/excellence/admin/{id}',json=payload).status_code,422)
    def test_public_researcher_profile_excludes_private_and_other_authors(self):
        id=self.create()
        self.assertEqual(self.client.get(f'/api/excellence/{id}/researcher').status_code,404)
        self.publish(id)
        for owner,status,title in [(self.teacher.id,'under_review','SECRET'),(self.admin.id,'published','OTHER'),(self.teacher.id,'published','SECOND')]:
            self.db.add(ResearchSubmission(researcher_id=owner,title=title,abstract='Abstract',problem='PRIVATE',research_field='Education',status=status))
        self.db.commit()
        app.dependency_overrides.pop(get_current_user)
        response=self.client.get(f'/api/excellence/{id}/researcher')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual({p['title'] for p in data['publications']},{self.research.title,'SECOND'})
        self.assertIsNone(data['school'])
        self.assertIsNone(data['directorate'])
        for secret in ['email','password_hash','problem','file_object_name','SECRET','OTHER']:
            self.assertNotIn(secret,response.text)
        self.research.status='under_review';self.db.commit()
        self.assertEqual(self.client.get(f'/api/excellence/{id}/researcher').status_code,404)

    def test_image_storage_failure_keeps_existing_entry(self):
        id=self.create();self.publish(id)
        old=self.db.get(ExcellenceEntry,id).image_object
        with patch('app.services.excellence._upload',side_effect=RuntimeError('offline')):
            self.assertEqual(self.client.post(f'/api/excellence/admin/{id}/image',files={'file':('photo.png',self.png(),'image/png')}).status_code,503)
        self.assertEqual(self.db.get(ExcellenceEntry,id).image_object,old)

if __name__=='__main__':unittest.main()

"""Integration checks for notification ownership, transactional triggers, and role isolation."""
import os
import unittest

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'notifications-test-secret')
os.environ.setdefault('DEBUG', 'false')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.notification import Notification
from app.models.news import NewsArticle
from app.models.platform import CommitteeAccount, Conference, PlatformNotice
from app.models.user import User
from app.models.workflow import ResearchSubmission, UserAffiliation, WorkflowEvent
from app.routers.dependencies import get_current_user


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(full_name='Researcher', email='owner@exam.test', password_hash='x', role='researcher', is_active=True, is_verified=True)
        self.other = User(full_name='Other', email='other@exam.test', password_hash='x', role='researcher', is_active=True, is_verified=True)
        self.admin = User(full_name='Admin', email='admin@exam.test', password_hash='x', role='system_admin', is_active=True, is_verified=True)
        self.db.add_all([self.owner, self.other, self.admin])
        self.db.commit()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.owner
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_inbox_owner_only_and_read_all(self):
        row = Notification(recipient_key=f'user:{self.owner.id}', kind='test', title_ar='خاصة', title_en='Private', href='/workspace')
        self.db.add(row)
        self.db.commit()
        owner = self.client.get('/api/notifications').json()
        self.assertEqual(owner['unread_count'], 1)
        self.assertEqual(len(owner['items']), 1)
        app.dependency_overrides[get_current_user] = lambda: self.other
        self.assertEqual(self.client.get('/api/notifications').json()['items'], [])
        self.assertEqual(self.client.post(f'/api/notifications/{row.id}/read').status_code, 404)
        app.dependency_overrides[get_current_user] = lambda: self.owner
        self.assertEqual(self.client.post('/api/notifications/read-all').json()['updated'], 1)
        self.assertEqual(self.client.get('/api/notifications').json()['unread_count'], 0)

    def test_submission_event_and_rollback(self):
        submission = ResearchSubmission(researcher_id=self.owner.id, title='Classroom research', research_field='Math', problem='Problem', status='submitted')
        self.db.add(submission)
        self.db.flush()
        self.db.add(WorkflowEvent(submission_id=submission.id, actor_id=self.owner.id, event_type='submitted', from_status=None, to_status='submitted'))
        self.db.commit()
        rows = self.db.scalars(select(Notification)).all()
        self.assertEqual({row.recipient_key for row in rows}, {f'user:{self.owner.id}', f'user:{self.admin.id}'})
        self.db.add(WorkflowEvent(submission_id=submission.id, actor_id=self.owner.id, event_type='scientific_decision', from_status='submitted', to_status='revision_requested'))
        self.db.flush()
        self.db.rollback()
        self.assertEqual(len(self.db.scalars(select(Notification)).all()), 2)

    def test_published_news_broadcast_only_when_newly_published(self):
        news = NewsArticle(created_by=self.admin.id, title='News', title_en='News EN', body='Body', published=False)
        self.db.add(news)
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(Notification)).all()), 0)
        news.published = True
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(Notification)).all()), 3)
        news.title = 'Updated headline'
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(Notification)).all()), 3)

    def test_affiliation_notice_and_committee_recipient_isolation(self):
        self.db.add(UserAffiliation(user_id=self.owner.id, approval_status='requested'))
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(Notification).where(Notification.recipient_key == f'user:{self.admin.id}')).all()), 1)
        row = self.db.get(UserAffiliation, self.owner.id)
        row.approval_status = 'approved'
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(Notification).where(Notification.recipient_key == f'user:{self.owner.id}')).all()), 1)
        conference = Conference(title='Research day', category='Research', venue='Campus', starts_at=__import__('datetime').datetime.now(), ends_at=__import__('datetime').datetime.now(), deadline=__import__('datetime').datetime.now(), created_by=self.admin.id)
        self.db.add(conference)
        self.db.commit()
        committee = CommitteeAccount(username='committee', password_hash='x', conference_id=conference.id, is_active=True)
        self.db.add(committee)
        self.db.commit()
        app.dependency_overrides[get_current_user] = lambda: committee
        self.assertEqual(self.client.get('/api/notifications').status_code, 200)
        self.assertEqual(self.client.get('/api/notifications').json()['items'], [])


if __name__ == '__main__':
    unittest.main()

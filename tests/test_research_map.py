"""Research choropleth counts use real submissions, verified geography, and role scopes."""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app  # noqa: F401: register ORM metadata
from app.core.database import Base
from app.domain.errors import ApplicationError
from app.models.education import Directorate, Governorate, School
from app.models.user import User
from app.models.workflow import ResearchSubmission, UserAffiliation
from app.services.research_map import research_governorates


class ResearchMapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.national = User(full_name='National', email='national@edu.test', password_hash='x', role='decision_maker')
        self.director = User(full_name='Director', email='director@edu.test', password_hash='x', role='directorate_manager')
        self.researcher = User(full_name='Researcher', email='research@edu.test', password_hash='x', role='researcher')
        self.db.add_all([self.national, self.director, self.researcher])
        self.db.flush()
        for id_ in ('g1', 'g2', 'g3'):
            self.db.add(Governorate(id=id_, name_ar=id_, name_en=id_, search_text='', region='PS01', latitude=31, longitude=35, geometry={}, boundary_date='2023', source='test'))
        for id_, gov in (('d1', 'g1'), ('d2', 'g2')):
            self.db.add(Directorate(id=id_, name_ar=id_, name_en=id_, search_text='', governorate_id=gov, region='PS01', category='public', source_url='', source_date='test'))
        self.db.add(School(id='s1', name_ar='School', name_en='School', national_code='1', search_text='', school_type='public', region='PS01', governorate_id='g1', directorate_id='d1', source_row=1, source_values={}))
        self.db.add(UserAffiliation(user_id=self.director.id, directorate_id='d1', approval_status='approved'))
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_research(self, *, gov=None, school=None, directorate=None, kind='research', status='submitted'):
        row = ResearchSubmission(researcher_id=self.researcher.id, title='Research', research_field='Education', problem='Problem', publication_type=kind, status=status, governorate_id=gov, directorate_id=directorate, school_id=school)
        self.db.add(row)
        self.db.flush()
        return row

    def test_national_totals_fallback_zero_and_unassigned(self):
        self.add_research(gov='g1', directorate='d1', status='published')
        self.add_research(school='s1', directorate='d1')  # school governorate fallback
        self.add_research(directorate='d2')  # directorate governorate fallback
        self.add_research()  # unknown is never guessed
        self.add_research(gov='old-removed', school='s1', directorate='d1')  # invalid saved ID falls back to school
        self.add_research(gov='g3', kind='practice')  # practices excluded
        self.db.commit()
        result = research_governorates(self.db, self.national)
        counts = {row['id']: row['research_count'] for row in result['governorates']}
        self.assertEqual(counts, {'g1': 3, 'g2': 1, 'g3': 0})
        self.assertEqual(result['total_research'], 5)
        self.assertEqual(result['published_research'], 1)
        self.assertEqual(result['unassigned_research'], 1)
        self.assertEqual(result['active_governorates'], 2)
        self.assertEqual(result['max_research_count'], 3)

    def test_directorate_scope_and_permissions(self):
        self.add_research(gov='g1', directorate='d1')
        self.add_research(gov='g2', directorate='d2')
        self.db.commit()
        restricted = research_governorates(self.db, self.director)
        self.assertEqual(restricted['scope'], 'directorate')
        self.assertEqual(restricted['total_research'], 1)
        self.assertEqual({r['id']: r['research_count'] for r in restricted['governorates']}, {'g1': 1, 'g2': 0, 'g3': 0})
        self.db.get(UserAffiliation, self.director.id).approval_status = 'requested'
        self.db.commit()
        self.assertEqual(research_governorates(self.db, self.director)['total_research'], 0)
        with self.assertRaises(ApplicationError) as error:
            research_governorates(self.db, self.researcher)
        self.assertEqual(error.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()

"""Isolated API/import tests. Synthetic coordinates below exist only in the test DB."""
import os
import unittest
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-only-unused-secret')
os.environ.setdefault('DEBUG', 'false')
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.database import get_db
from app.models.education import School, Directorate
from app.models.user import User
from app.core.security import create_access_token
from app.services.education import normalize_query
from scripts.import_education import TABLES, import_data
from scripts.enrich_education import enrich


class EducationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        User.__table__.create(cls.engine)
        for table in TABLES:
            table.create(cls.engine)
        with Session(cls.engine) as db, db.begin():
            cls.initial_stats = import_data(db)
            user = User(id=1, full_name='Test Account', email='map-test@example.test', password_hash='unused', is_active=True, is_verified=True)
            db.add(user)
        def test_db():
            with Session(cls.engine) as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        cls.client = TestClient(app)
        cls.client.headers['Authorization'] = f'Bearer {create_access_token(1)}'

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_authentication_is_enforced_and_existing_routes_remain(self):
        anonymous = TestClient(app)
        try:
            for endpoint in ('catalog', 'boundaries', 'schools', 'schools/points?bbox=34,29,37,34'):
                self.assertEqual(anonymous.get('/api/education/' + endpoint).status_code, 401)
            self.assertEqual(anonymous.get('/api/education/catalog', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        finally:
            anonymous.close()
        paths = {route.path for route in app.routes}
        self.assertTrue({'/auth/login', '/auth/register', '/auth/refresh'}.issubset(paths))

    def test_catalog_and_real_boundaries(self):
        data = self.client.get('/api/education/catalog').json()
        self.assertEqual(data['total_schools'], 3094)
        self.assertEqual(len(data['governorates']), 16)
        self.assertEqual(len(data['directorates']), 22)
        self.assertEqual(data['located_schools'], 0)
        self.assertEqual(data['unassigned_directorate_schools'], 3094)
        self.assertEqual(data['unassigned_governorate_schools'], 2)
        boundaries = self.client.get('/api/education/boundaries').json()
        self.assertEqual(len(boundaries['features']), 16)
        self.assertTrue(all(f['geometry']['type'] in ('Polygon', 'MultiPolygon') for f in boundaries['features']))
        self.assertFalse(any('research' in f['properties'] for f in boundaries['features']))
        self.assertEqual(self.client.get('/api/education/directorates/boundaries').json()['features'], [])

    def test_search_and_pagination(self):
        data = self.client.get('/api/education/schools', params={'limit': 10}).json()
        self.assertEqual(len(data['items']), 10)
        next_page = self.client.get('/api/education/schools', params={'offset': 10, 'limit': 10}).json()
        self.assertFalse({s['id'] for s in data['items']} & {s['id'] for s in next_page['items']})
        school = data['items'][0]
        for query in (school['name_ar'], school['name_en'], school['national_code']):
            if not query:
                continue
            found = self.client.get('/api/education/schools', params={'q': query, 'limit': 100}).json()
            self.assertIn(school['id'], [s['id'] for s in found['items']])
        for city in ('نابلس', 'Nablus'):
            found = self.client.get('/api/education/schools', params={'q': city}).json()
            all_city = self.client.get('/api/education/schools', params={'governorate_id': 'PS0115'}).json()
            self.assertGreaterEqual(found['total'], all_city['total'])
        self.assertEqual(normalize_query('إِبْرَاهِيم ١٢٣'), normalize_query('ابراهيم 123'))
        injection_result = self.client.get('/api/education/schools', params={'q': "' OR 1=1 --"}).json()
        self.assertLess(injection_result['total'], 3094)
        self.assertEqual(injection_result, self.client.get('/api/education/schools', params={'q': 'or 1 1'}).json())
        self.assertEqual(self.client.get('/api/education/schools', params={'limit': 101}).status_code, 422)

    def test_filters_and_missing_data(self):
        data = self.client.get('/api/education/schools', params={'governorate_id': 'PS0101', 'school_type': 'government', 'region': 'PS01'}).json()
        self.assertGreater(data['total'], 0)
        self.assertTrue(all(s['governorate_id'] == 'PS0101' and s['school_type'] == 'government' for s in data['items']))
        self.assertEqual(self.client.get('/api/education/schools', params={'location': 'located'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/education/schools', params={'directorate_id': 'unassigned'}).json()['total'], 3094)
        self.assertEqual(self.client.get('/api/education/schools/missing').status_code, 404)
        points = self.client.get('/api/education/schools/points', params={'bbox': '34,29,37,34'}).json()
        self.assertEqual(points['features'], [])
        for bbox in ('nan,0,1,1', '1,1,0,0', '1,2,3', '-181,0,2,3'):
            self.assertEqual(self.client.get('/api/education/schools/points', params={'bbox': bbox}).status_code, 422)

    def test_insert_only_and_ambiguous_codes(self):
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(School).where(School.national_code == '38331760')), 2)
            school = db.scalars(select(School)).first()
            school.latitude, school.longitude, school.coordinate_source = 31.8, 35.2, 'TEST ONLY'
            school.directorate_id = db.scalars(select(Directorate.id)).first()
            stats = import_data(db)
            self.assertEqual(stats['inserted'], 0)
            self.assertEqual(stats['existing'], 3132)
            self.assertEqual(school.latitude, 31.8)
            self.assertIsNotNone(school.directorate_id)
            db.rollback()

    def test_verified_enrichment_points_and_rollback(self):
        with Session(self.engine) as db:
            school = db.scalars(select(School)).first()
            uid = school.id
            with self.assertRaises(ValueError):
                enrich(db, [{'id': uid, 'latitude': 31.8, 'longitude': 35.2}])
            db.rollback()
            enrich(db, [{'id': uid, 'latitude': 31.8, 'longitude': 35.2, 'coordinate_source': 'TEST ONLY'}])
            db.commit()
        try:
            points = self.client.get('/api/education/schools/points', params={'bbox': '35,31,36,32'}).json()
            self.assertEqual(points['features'][0]['geometry']['coordinates'], [35.2, 31.8])
            self.assertEqual(points['total'], 1)
            self.assertEqual(self.client.get('/api/education/schools/points', params={'bbox': '34,29,34.5,30'}).json()['total'], 0)
            with Session(self.engine) as db:
                with self.assertRaises(ValueError):
                    with db.begin():
                        enrich(db, [{'id': uid, 'latitude': 32, 'longitude': 35, 'coordinate_source': 'TEST CHANGE'}, {'id': 'unknown'}])
                self.assertEqual(db.get(School, uid).latitude, 31.8)
        finally:
            with Session(self.engine) as db, db.begin():
                school = db.get(School, uid)
                school.latitude = school.longitude = school.coordinate_source = None


if __name__ == '__main__':
    unittest.main()

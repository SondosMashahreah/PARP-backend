"""Regression tests for real location imports, preserving user edits and API points."""
import copy
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-only-unused-secret")
os.environ.setdefault("DEBUG", "false")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.education import Directorate, EducationSource, School
from app.models.user import User
from scripts.import_education import TABLES, import_data
from scripts.import_school_locations import import_locations, load_bundle, validate_bundle


class SchoolLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle()
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        for table in TABLES + [User.__table__]:
            table.create(cls.engine)
        with Session(cls.engine) as db, db.begin():
            import_data(db)
            db.add(User(id=1, full_name="Location test", email="locations@example.test", password_hash="unused", is_active=True, is_verified=True))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_real_bundle_is_consistent_and_preview_writes_nothing(self):
        records = validate_bundle(self.bundle)
        self.assertEqual(len(records), 2381)
        self.assertEqual(sum(r["region"] == "PS02" for r in records), 22)
        self.assertEqual(sum(r["governorate_id"] is None for r in records), 2)
        with Session(self.engine) as db:
            report = import_locations(db, self.bundle)
            self.assertEqual(report["eligible"], 2381)
            self.assertEqual(report["added"], 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(School).where(School.latitude.is_not(None))), 0)
            self.assertIsNone(db.get(EducationSource, "school-locations-v1"))

    def test_apply_repeat_and_seed_preserve_existing_edits(self):
        first, second = self.bundle["records"][:2]
        with Session(self.engine) as db:
            school = db.get(School, first["id"])
            school.latitude, school.longitude, school.coordinate_source = 31.75, 35.2, "Manually verified by platform editor"
            chosen_directorate = db.scalars(select(Directorate.id)).first()
            school.directorate_id = chosen_directorate
            report = import_locations(db, self.bundle, apply=True)
            self.assertEqual(report["added"], 2380)
            self.assertEqual(report["preserved_existing"], 1)
            self.assertEqual(db.get(School, first["id"]).coordinate_source, "Manually verified by platform editor")
            self.assertEqual(db.get(School, first["id"]).directorate_id, chosen_directorate)
            self.assertEqual(db.get(School, second["id"]).longitude, second["longitude"])
            repeat = import_locations(db, self.bundle, apply=True)
            self.assertEqual(repeat["added"], 0)
            self.assertEqual(repeat["already_present"], 2380)
            import_data(db)
            self.assertEqual(db.get(School, first["id"]).latitude, 31.75)
            self.assertEqual(db.get(School, second["id"]).latitude, second["latitude"])
            db.rollback()

    def test_edited_school_identity_is_not_overwritten(self):
        row = self.bundle["records"][0]
        with Session(self.engine) as db:
            school = db.get(School, row["id"])
            school.name_ar = "Updated by user"
            report = import_locations(db, self.bundle, apply=True)
            self.assertEqual(report["identity_changed"], 1)
            self.assertIsNone(db.get(School, row["id"]).latitude)
            self.assertEqual(db.get(School, row["id"]).name_ar, "Updated by user")
            db.rollback()

    def test_invalid_or_unknown_rows_never_partially_write(self):
        for mutation in ("nan", "swapped", "missing_source", "duplicate", "unknown"):
            bundle = copy.deepcopy(self.bundle)
            row = bundle["records"][-1]
            if mutation == "nan":
                row["latitude"] = float("nan")
            elif mutation == "swapped":
                row["latitude"], row["longitude"] = row["longitude"], row["latitude"]
            elif mutation == "missing_source":
                row["coordinate_source"] = ""
            elif mutation == "duplicate":
                row["id"] = bundle["records"][0]["id"]
            else:
                row["id"] = "school-unknown"
            with Session(self.engine) as db:
                with self.assertRaises(ValueError):
                    import_locations(db, bundle, apply=True)
                self.assertEqual(db.scalar(select(func.count()).select_from(School).where(School.latitude.is_not(None))), 0)

    def test_transaction_rollback_after_apply(self):
        with Session(self.engine) as db:
            with self.assertRaises(RuntimeError):
                with db.begin():
                    import_locations(db, self.bundle, apply=True)
                    raise RuntimeError("Simulated failure before commit")
            self.assertEqual(db.scalar(select(func.count()).select_from(School).where(School.latitude.is_not(None))), 0)

    def test_imported_locations_in_authenticated_api_and_bbox(self):
        with Session(self.engine) as db, db.begin():
            import_locations(db, self.bundle, apply=True)
        def test_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        try:
            with TestClient(app) as client:
                client.headers["Authorization"] = f"Bearer {create_access_token(1)}"
                catalog = client.get("/api/education/catalog").json()
                self.assertEqual(catalog["located_schools"], 2381)
                self.assertEqual(catalog["total_schools"], 3094)
                self.assertEqual(catalog["unassigned_governorate_schools"], 2)
                self.assertEqual(catalog["unassigned_directorate_schools"], 3094)
                missing = client.get("/api/education/schools", params={"location": "missing"}).json()
                self.assertEqual(missing["total"], 713)
                points = client.get("/api/education/schools/points", params={"bbox": "34,31,36,33", "limit": 5000}).json()
                self.assertEqual(points["total"], 2381)
                self.assertEqual(len(points["features"]), 2381)
                source = {r["id"]: r for r in self.bundle["records"]}
                for point in points["features"]:
                    row = source[point["id"]]
                    self.assertEqual(point["geometry"]["coordinates"], [row["longitude"], row["latitude"]])
                gaza = client.get("/api/education/schools/points", params={"bbox": "34,31,35,31.65", "region": "PS02"}).json()
                self.assertEqual(gaza["total"], 22)
                self.assertEqual(client.get("/api/education/schools/points", params={"bbox": "34,29,34.5,30"}).json()["total"], 0)
                row = self.bundle["records"][0]
                for query in [row["name_ar"], row["name_en"], row["national_code"]]:
                    result = client.get("/api/education/schools", params={"q": query, "location": "located"}).json()
                    self.assertIn(row["id"], [r["id"] for r in result["items"]])
                detail = client.get("/api/education/schools/" + row["id"]).json()
                self.assertEqual(detail["coordinate_source"], row["coordinate_source"])
        finally:
            app.dependency_overrides.clear()
            with Session(self.engine) as db, db.begin():
                for school in db.scalars(select(School)):
                    school.latitude = school.longitude = school.coordinate_source = None
                source = db.get(EducationSource, "school-locations-v1")
                if source:
                    db.delete(source)


if __name__ == "__main__":
    unittest.main()

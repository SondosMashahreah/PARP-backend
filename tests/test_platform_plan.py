import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "testing-only-key"
os.environ["DEBUG"] = "false"
import unittest
from datetime import datetime, timezone, timedelta
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import Base, get_db
from app.routers.dependencies import get_current_user
from app.models.user import User
from app.models.workflow import (
    ResearchSubmission,
    ResearchVersion,
    UserAffiliation,
    ReviewAssignment,
)
from app.models.platform import (
    PublicationPayment,
    Conference,
    ConferenceParticipation,
    CommitteeCredential,
)
from app.models.education import School, Directorate
from app.services import platform, workflow, researcher
from app.schemas.platform import (
    PaymentUpdate,
    ConferenceCreate,
    AdminUserCreate,
    CommitteeLogin,
    PasswordChange,
    ParticipationDecision,
)
from app.schemas.researcher import DraftContent
from app.schemas.workflow import DecisionRequest
from app.domain.errors import ApplicationError
from app.domain.roles import validate_role


class PlatformPlanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.users = {}
        for role in (
            "researcher",
            "school_manager",
            "directorate_manager",
            "decision_maker",
            "reviewer",
            "scientific_committee",
            "organizing_committee",
            "system_admin",
        ):
            u = User(
                full_name=role,
                email=role + "@example.org",
                password_hash="unused",
                role=role,
                is_active=True,
                is_verified=True,
            )
            self.db.add(u)
            self.db.flush()
            self.users[role] = u
        self.owner = self.users["researcher"]
        self.admin = self.users["system_admin"]
        for i in ("1", "2"):
            self.db.add(
                Directorate(
                    id="d" + i,
                    name_ar="مديرية " + i,
                    name_en="Directorate " + i,
                    search_text="",
                    category="public",
                    source_url="",
                    source_date="2026",
                    latitude=31.9,
                    longitude=35.2,
                )
            )
            self.db.add(
                School(
                    id="s" + i,
                    national_code=i,
                    name_ar="مدرسة " + i,
                    name_en="School " + i,
                    search_text="",
                    school_type="public",
                    directorate_id="d" + i,
                    region="PS01",
                    source_row=int(i),
                    source_values={},
                )
            )
        self.db.flush()
        for role in ("researcher", "school_manager", "directorate_manager"):
            self.db.add(
                UserAffiliation(
                    user_id=self.users[role].id,
                    school_id="s1",
                    directorate_id="d1",
                    approval_status="approved",
                )
            )
        self.db.commit()
        self.patches = [
            patch(
                "app.services.workflow.presigned_file_url", return_value="private-url"
            ),
            patch(
                "app.services.workflow.upload_research_file",
                return_value="research-file",
            ),
            patch(
                "app.services.platform.presigned_file_url",
                return_value="presentation-url",
            ),
            patch("app.services.platform._upload", return_value="presentation-file"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        app.dependency_overrides.clear()
        for p in self.patches:
            p.stop()
        self.db.close()
        self.engine.dispose()

    def record(self, kind="research", status="approved", school="s1"):
        row = ResearchSubmission(
            researcher_id=self.owner.id,
            title="Action research",
            abstract="Public abstract",
            research_field="Education",
            problem="Private detail",
            school_id=school,
            directorate_id="d1" if school == "s1" else "d2",
            publication_type=kind,
            status=status,
            publication_allowed=True,
        )
        self.db.add(row)
        self.db.flush()
        self.db.add(
            ResearchVersion(
                submission_id=row.id,
                version_number=1,
                file_object_name="file",
                original_file_name="paper.pdf",
                content_type="application/pdf",
                form_data={},
            )
        )
        self.db.commit()
        return row

    def test_zero_requires_explicit_admin_confirmation_and_full_payment(self):
        row = self.record()
        with self.assertRaises(ApplicationError):
            workflow.publish_research(self.db, self.owner, row.id)
        payment = platform.request_payment(self.db, self.owner, row.id)
        self.assertFalse(payment["confirmed"])
        with self.assertRaises(ApplicationError):
            workflow.publish_research(self.db, self.owner, row.id)
        with self.assertRaises(ApplicationError):
            platform.update_payment(
                self.db,
                self.users["scientific_committee"],
                row.id,
                PaymentUpdate(required_agorot=0, paid_agorot=0, confirmed=True),
            )
        with self.assertRaises(ValueError):
            PaymentUpdate(required_agorot=100, paid_agorot=0, confirmed=True)
        result = platform.update_payment(
            self.db,
            self.admin,
            row.id,
            PaymentUpdate(required_agorot=0, paid_agorot=0, confirmed=True),
        )
        self.assertEqual(result["history"][0]["actor_id"], self.admin.id)
        self.assertEqual(
            workflow.publish_research(self.db, self.owner, row.id)["status"],
            "published",
        )
        with self.assertRaises(ApplicationError):
            platform.update_payment(
                self.db,
                self.admin,
                row.id,
                PaymentUpdate(required_agorot=0, paid_agorot=0, confirmed=False),
            )

    def test_practice_requires_evaluation_but_never_payment(self):
        row = self.record("practice", "submitted")
        with self.assertRaises(ApplicationError):
            workflow.publish_as_practice(self.db, self.owner, row.id)
        row.status = "approved"
        self.db.commit()
        with self.assertRaises(ApplicationError):
            platform.request_payment(self.db, self.owner, row.id)
        result = workflow.publish_as_practice(self.db, self.owner, row.id)
        self.assertEqual(result["status"], "published")
        self.assertIsNone(self.db.get(PublicationPayment, row.id))
        self.assertEqual(
            workflow.public_repository(self.db, "practice")[0]["file"]["url"],
            "private-url",
        )

    def test_public_research_hides_file_and_private_fields(self):
        row = self.record(status="published")
        public = workflow.public_repository(self.db, "research")[0]
        self.assertEqual(public["abstract"], "Public abstract")
        self.assertIsNone(public["file"])
        self.assertIsNone(public["problem"])
        self.assertEqual(public["events"], [])
        self.assertIsNotNone(
            workflow.serialize_submission(self.db, row, self.owner)["file"]
        )

    def test_required_abstract_and_practice_draft(self):
        draft = researcher.create_draft(
            self.db,
            self.owner,
            DraftContent(
                kind="practice",
                title="Practice",
                research_field="Teaching",
                problem="Problem",
            ),
        )
        with self.assertRaises(ApplicationError):
            researcher.submit_draft(
                self.db,
                self.owner,
                draft["id"],
                1,
                "x.pdf",
                "application/pdf",
                b"%PDF-test",
            )
        good = researcher.create_draft(
            self.db,
            self.owner,
            DraftContent(
                kind="practice",
                title="Practice",
                research_field="Teaching",
                problem="Problem",
                abstract="Practice abstract",
            ),
        )
        result = researcher.submit_draft(
            self.db, self.owner, good["id"], 1, "x.pdf", "application/pdf", b"%PDF-test"
        )
        self.assertEqual(result["publication_type"], "practice")

    def test_school_directorate_and_national_scopes(self):
        self.record(school="s1")
        self.record(school="s2")
        school = platform.statistics(self.db, self.users["school_manager"])
        self.assertEqual(len(school["research"]), 1)
        self.assertEqual([s["id"] for s in school["schools"]], ["s1"])
        directorate = platform.statistics(self.db, self.users["directorate_manager"])
        self.assertEqual(len(directorate["research"]), 1)
        self.assertEqual(
            len(platform.statistics(self.db, self.users["decision_maker"])["research"]),
            2,
        )
        aff = self.db.get(UserAffiliation, self.users["school_manager"].id)
        aff.approval_status = "requested"
        self.db.commit()
        self.assertEqual(
            platform.statistics(self.db, self.users["school_manager"])["schools"], []
        )
        with self.assertRaises(ApplicationError):
            workflow.approve_affiliation(
                self.db, self.users["school_manager"], self.users["school_manager"].id
            )

    def test_only_assigned_evaluator_decides(self):
        row = self.record(status="under_review")
        reviewer = self.users["reviewer"]
        with self.assertRaises(ApplicationError):
            workflow.scientific_decision(
                self.db,
                self.users["scientific_committee"],
                row.id,
                DecisionRequest(decision="approve"),
            )
        with self.assertRaises(ApplicationError):
            workflow.scientific_decision(
                self.db, reviewer, row.id, DecisionRequest(decision="approve")
            )
        self.db.add(
            ReviewAssignment(
                submission_id=row.id,
                reviewer_id=reviewer.id,
                assigned_by_id=self.admin.id,
                status="completed",
                confidentiality_accepted=True,
            )
        )
        self.db.commit()
        self.assertEqual(
            workflow.scientific_decision(
                self.db, reviewer, row.id, DecisionRequest(decision="approve")
            )["status"],
            "approved",
        )

    def conference(self):
        now = datetime.now(timezone.utc)
        return platform.create_conference(
            self.db,
            self.users["scientific_committee"],
            ConferenceCreate(
                title="Research conference",
                category="Education",
                venue="Jerusalem",
                starts_at=now + timedelta(days=10),
                ends_at=now + timedelta(days=11),
                deadline=now + timedelta(days=5),
            ),
        )

    def test_conference_upload_decision_and_scoped_notices(self):
        conf = self.conference()
        data = BytesIO()
        with ZipFile(data, "w") as z:
            z.writestr("ppt/presentation.xml", "<presentation/>")
        with self.assertRaises(ApplicationError):
            platform.participate(
                self.db, self.owner, conf["id"], "Title", "Abstract", "bad.pptx", b"bad"
            )
        item = platform.participate(
            self.db,
            self.owner,
            conf["id"],
            "Title",
            "Abstract",
            "talk.pptx",
            data.getvalue(),
        )
        with self.assertRaises(ApplicationError):
            platform.participate(
                self.db,
                self.owner,
                conf["id"],
                "Title",
                "Abstract",
                "talk.pptx",
                data.getvalue(),
            )
        with self.assertRaises(ApplicationError):
            platform.decide_participation(
                self.db,
                self.users["organizing_committee"],
                item["id"],
                ParticipationDecision(status="approved", notes="Approved"),
            )
        platform.decide_participation(
            self.db,
            self.users["scientific_committee"],
            item["id"],
            ParticipationDecision(status="revision_requested", notes="Revise slides"),
        )
        self.assertEqual(len(platform.notices(self.db, self.owner)), 1)
        self.assertEqual(platform.notices(self.db, self.admin), [])
        self.assertEqual(
            platform.participate(
                self.db,
                self.owner,
                conf["id"],
                "Revised",
                "Abstract",
                "talk.pptx",
                data.getvalue(),
            )["status"],
            "submitted",
        )
        self.assertEqual(
            len(platform.participations(self.db, self.users["school_manager"])), 1
        )

    def test_committee_credentials_and_retired_role(self):
        conf = self.conference()
        with self.assertRaises(ValueError):
            validate_role("supervisor")
        data = AdminUserCreate(
            full_name="Committee user",
            email="committee@other.org",
            password="Temporary1!",
            role="organizing_committee",
            username="committee.member",
            conference_id=conf["id"],
        )
        with self.assertRaises(ApplicationError):
            platform.create_user(self.db, self.owner, data)
        result = platform.create_user(self.db, self.admin, data)
        logged = platform.committee_login(
            self.db, CommitteeLogin(username="committee.member", password="Temporary1!")
        )
        self.assertTrue(logged["must_change_password"])
        platform.change_password(
            self.db,
            self.db.get(User, result["id"]),
            PasswordChange(password="UpdatedPass2!"),
        )
        self.assertFalse(
            self.db.get(CommitteeCredential, result["id"]).must_change_password
        )

    def test_http_map_access(self):
        def session():
            yield self.db

        app.dependency_overrides[get_db] = session
        client = TestClient(app)
        self.assertEqual(client.get("/api/platform/map").status_code, 401)
        for role, u in self.users.items():

            def actor():
                return u

            app.dependency_overrides[get_current_user] = actor
            self.assertEqual(
                client.get("/api/platform/map").status_code,
                200 if role in ("decision_maker", "directorate_manager") else 403,
            )
        client.close()


if __name__ == "__main__":
    unittest.main()

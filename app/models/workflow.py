from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class UserAffiliation(Base):
    __tablename__ = "user_affiliations"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    governorate_id: Mapped[str | None] = mapped_column(
        ForeignKey("education_governorates.id"), nullable=True, index=True
    )
    directorate_id: Mapped[str | None] = mapped_column(
        ForeignKey("education_directorates.id"), nullable=True, index=True
    )
    school_id: Mapped[str | None] = mapped_column(
        ForeignKey("education_schools.id"), nullable=True, index=True
    )
    specialization: Mapped[str | None] = mapped_column(String(150), nullable=True)
    research_field: Mapped[str | None] = mapped_column(String(150), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(30), default="requested", nullable=False, index=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchSubmission(Base):
    __tablename__ = "research_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    governorate_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    directorate_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    school_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_field: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    research_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    intervention: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(40), default="submitted", nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    publication_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    publication_type: Mapped[str] = mapped_column(String(20), default="research", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ResearchVersion(Base):
    __tablename__ = "research_versions"
    __table_args__ = (
        UniqueConstraint("submission_id", "version_number", name="uq_research_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("research_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_object_name: Mapped[str] = mapped_column(String(600), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    form_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"
    __table_args__ = (
        UniqueConstraint("submission_id", "reviewer_id", name="uq_submission_reviewer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("research_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidentiality_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="invited", nullable=False, index=True)


class ResearchReview(Base):
    __tablename__ = "research_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("review_assignments.id"), nullable=False, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("research_submissions.id"), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    comments: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorkflowEvent(Base):
    __tablename__ = "research_workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("research_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RecommendationRecord(Base):
    __tablename__ = "observatory_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("research_submissions.id"), unique=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    research_field: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    directorate_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProblemRecord(Base):
    __tablename__ = "problem_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("research_submissions.id"), unique=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    research_field: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    school_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    directorate_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def now():
    return datetime.now(timezone.utc)


class ResearchDraft(Base):
    __tablename__ = 'research_drafts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey('research_submissions.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class TrainingProgress(Base):
    __tablename__ = 'researcher_training_progress'
    __table_args__ = (UniqueConstraint('user_id', 'course_key', name='uq_researcher_course'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    course_key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(250))
    completed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ResearcherCertificate(Base):
    __tablename__ = 'researcher_certificates'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(250))
    issuer: Mapped[str] = mapped_column(String(250))
    file_object_name: Mapped[str] = mapped_column(String(600))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

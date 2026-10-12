from datetime import datetime, timezone
from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def now():
    return datetime.now(timezone.utc)


class PublicationPayment(Base):
    __tablename__ = "publication_payments"
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("research_submissions.id"), primary_key=True
    )
    required_agorot: Mapped[int] = mapped_column(Integer, default=0)
    paid_agorot: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    receipt: Mapped[str] = mapped_column(String(250), default="")
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Conference(Base):
    __tablename__ = "conferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(150))
    venue: Mapped[str] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ConferenceParticipation(Base):
    __tablename__ = "conference_participations"
    __table_args__ = (
        UniqueConstraint(
            "conference_id", "researcher_id", name="uq_conference_researcher"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey("conferences.id"))
    researcher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    school_id: Mapped[str] = mapped_column(String(80), index=True)
    directorate_id: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500))
    abstract: Mapped[str] = mapped_column(Text)
    object_name: Mapped[str] = mapped_column(String(600))
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlatformNotice(Base):
    __tablename__ = "platform_notices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey("conferences.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CommitteeCredential(Base):
    __tablename__ = "committee_credentials"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey("conferences.id"))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)

"""Additive hall-of-excellence records; existing research stays authoritative."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class ExcellenceEntry(Base):
    __tablename__ = 'excellence_entries'
    __table_args__ = (UniqueConstraint('conference_id', 'submission_id', name='uq_excellence_conference_research'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey('conferences.id'), index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('research_submissions.id'), index=True)
    name_ar: Mapped[str] = mapped_column(String(150))
    name_en: Mapped[str] = mapped_column(String(150))
    conference_title_en: Mapped[str] = mapped_column(String(300), default='')
    image_object: Mapped[str | None] = mapped_column(String(600), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

"""Private, persistent inbox. Prefix keys keep committee IDs separate from user IDs."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    __tablename__ = 'notifications'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    title_en: Mapped[str] = mapped_column(String(300), nullable=False)
    body_ar: Mapped[str] = mapped_column(Text, nullable=False, default='')
    body_en: Mapped[str] = mapped_column(Text, nullable=False, default='')
    href: Mapped[str] = mapped_column(String(500), nullable=False, default='/workspace')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

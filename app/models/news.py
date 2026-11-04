from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class NewsArticle(Base):
    __tablename__ = 'news_articles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    title_en: Mapped[str] = mapped_column(String(300), default='')
    excerpt: Mapped[str] = mapped_column(String(1000), default='')
    excerpt_en: Mapped[str] = mapped_column(String(1000), default='')
    body: Mapped[str] = mapped_column(Text)
    body_en: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(100), default='أخبار المنصة')
    category_en: Mapped[str] = mapped_column(String(100), default='')
    image_alt: Mapped[str] = mapped_column(String(300), default='')
    image_object: Mapped[str | None] = mapped_column(String(600), nullable=True)
    gallery_images: Mapped[list['NewsImage']] = relationship(
        back_populates='article', cascade='all, delete-orphan', order_by='NewsImage.id', lazy='select'
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class NewsImage(Base):
    """Additional images: ordered by insertion ID; the cover stays on news_articles.image_object."""
    __tablename__ = 'news_article_images'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey('news_articles.id', ondelete='CASCADE'), nullable=False, index=True
    )
    object_name: Mapped[str] = mapped_column(String(600), nullable=False)
    article: Mapped[NewsArticle] = relationship(back_populates='gallery_images')

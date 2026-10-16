"""Idempotent additive migration: python -m scripts.create_news_table."""
from app.core.database import engine
from app.models.user import User  # noqa: F401, resolves the foreign key
from app.models.news import NewsArticle

if __name__ == '__main__':
    NewsArticle.__table__.create(engine, checkfirst=True)
    print('news_articles is ready')

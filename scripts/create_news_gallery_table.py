"""Add the news gallery table safely without modifying existing articles.

Run once AFTER deploying the new backend code and BEFORE serving gallery requests:
    python -m scripts.create_news_gallery_table

The operation is idempotent. It retains all news_articles.image_object covers.
"""
from app.core.database import engine
from app.models.user import User  # noqa: F401 - resolve foreign keys
from app.models.news import NewsArticle, NewsImage  # noqa: F401

if __name__ == '__main__':
    NewsImage.__table__.create(engine, checkfirst=True)
    print('news_article_images is ready')

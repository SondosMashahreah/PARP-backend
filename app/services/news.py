from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, func, or_
from app.models.news import NewsArticle
from app.domain.errors import ApplicationError
from app.services.workflow import ensure_role
from app.services.excellence import sanitize_image, MAX_IMAGE_BYTES
from app.infrastructure.minio_storage import _upload, delete_object, presigned_avatar_url


def admin(user):
    ensure_role(user, 'system_admin')


def get_article(db, article_id, public=True):
    row = db.get(NewsArticle, article_id)
    if not row or (public and not row.published):
        raise ApplicationError(404, 'News article not found')
    return row


def serialize(row, full=False, private=False):
    fields = ['id', 'title', 'title_en', 'excerpt', 'excerpt_en', 'category', 'category_en', 'image_alt']
    if full:
        fields += ['body', 'body_en']
    if private:
        fields += ['published']
    data = {k: getattr(row, k) for k in fields}
    for k in ['published_at', 'updated_at']:
        value = getattr(row, k)
        data[k] = value.replace(tzinfo=timezone.utc).isoformat() if value else None
    data['image_url'] = presigned_avatar_url(row.image_object)
    return data


def list_articles(db, *, public=True, q='', offset=0, limit=24):
    stmt = select(NewsArticle)
    if public:
        stmt = stmt.where(NewsArticle.published.is_(True))
    if q.strip():
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        stmt = stmt.where(or_(*[c.ilike(pattern, escape='\\') for c in [NewsArticle.title, NewsArticle.title_en, NewsArticle.excerpt, NewsArticle.body]]))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc()).offset(offset).limit(limit))
    return {'items': [serialize(r, private=not public) for r in rows], 'total': total, 'offset': offset, 'limit': limit}


def write(db, user, data, article_id=None):
    admin(user)
    row = get_article(db, article_id, False) if article_id else NewsArticle(created_by=user.id)
    if data.published and not row.image_object:
        raise ApplicationError(422, 'Save a draft and upload its image before publishing')
    if data.published and not row.published_at:
        row.published_at = datetime.now(timezone.utc)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize(row, full=True, private=True)


def set_image(db, user, article_id, data):
    admin(user)
    row = get_article(db, article_id, False)
    clean = sanitize_image(data)
    old = row.image_object
    name = f'news/{article_id}/{uuid4().hex}.webp'
    try:
        _upload(name, clean, 'image/webp')
    except Exception:
        raise ApplicationError(503, 'Image storage is unavailable; please retry')
    try:
        row.image_object = name
        db.commit()
    except Exception:
        db.rollback()
        delete_object(name)
        raise
    delete_object(old)
    return serialize(row, full=True, private=True)


def delete(db, user, article_id):
    admin(user)
    row = get_article(db, article_id, False)
    image = row.image_object
    db.delete(row)
    db.commit()
    delete_object(image)
    return {'deleted': True}

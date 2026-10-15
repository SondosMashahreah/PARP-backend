from io import BytesIO
import warnings
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, or_, func, extract
from sqlalchemy.exc import IntegrityError
from app.domain.errors import ApplicationError
from app.models.excellence import ExcellenceEntry
from app.models.platform import Conference
from app.models.workflow import ResearchSubmission, UserAffiliation
from app.models.education import School, Directorate
from app.infrastructure.minio_storage import _upload, delete_object, presigned_avatar_url
from app.services.workflow import ensure_role

MAX_IMAGE_BYTES = 5 * 1024 * 1024

def admin(user):
    ensure_role(user, 'system_admin')

def get_entry(db, entry_id):
    row = db.get(ExcellenceEntry, entry_id)
    if not row:
        raise ApplicationError(404, 'Excellence entry not found')
    return row

def serialize(entry, research, conference):
    return dict(id=entry.id, submission_id=research.id, conference_id=conference.id,
        name_ar=entry.name_ar, name_en=entry.name_en, title=research.title,
        title_en=research.title_en or research.title, conference_title=conference.title,
        conference_title_en=entry.conference_title_en or conference.title,
        conference_title_en_override=entry.conference_title_en,
        year=conference.starts_at.year, image_url=presigned_avatar_url(entry.image_object),
        visible=entry.visible, sort_order=entry.sort_order, research_status=research.status,
        has_abstract=bool(research.abstract and research.abstract.strip()))

def query_base():
    return select(ExcellenceEntry, ResearchSubmission, Conference).join(ResearchSubmission, ExcellenceEntry.submission_id == ResearchSubmission.id).join(Conference, ExcellenceEntry.conference_id == Conference.id)

def public_conditions():
    return (ExcellenceEntry.visible.is_(True), ExcellenceEntry.image_object.is_not(None), ResearchSubmission.status == 'published', func.length(func.trim(ResearchSubmission.abstract)) > 0)

def list_entries(db, *, public=True, q='', year=None, conference_id=None, offset=0, limit=24):
    stmt = query_base()
    if public:
        stmt = stmt.where(*public_conditions())
    if q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = f'%{escaped}%'
        stmt = stmt.where(or_(*[c.ilike(pattern, escape='\\') for c in (ExcellenceEntry.name_ar, ExcellenceEntry.name_en, ResearchSubmission.title, ResearchSubmission.title_en)]))
    if year:
        stmt = stmt.where(extract('year', Conference.starts_at) == year)
    if conference_id:
        stmt = stmt.where(Conference.id == conference_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Conference.starts_at.desc(), ExcellenceEntry.sort_order, ExcellenceEntry.id).offset(offset).limit(limit)).all()
    return {'items': [serialize(*row) for row in rows], 'total': total, 'offset': offset, 'limit': limit}

def filters(db):
    rows = db.execute(query_base().where(*public_conditions()).order_by(Conference.starts_at.desc(), ExcellenceEntry.id)).all()
    conferences = {}
    for entry, _, conference in rows:
        conferences.setdefault(conference.id, {'id': conference.id, 'title': conference.title, 'title_en': entry.conference_title_en or conference.title, 'year': conference.starts_at.year})
    return {'conferences': list(conferences.values()), 'years': sorted({r['year'] for r in conferences.values()}, reverse=True)}

def abstract(db, entry_id):
    row = db.execute(query_base().where(ExcellenceEntry.id == entry_id, *public_conditions())).first()
    if not row:
        raise ApplicationError(404, 'Published excellence entry not found')
    entry, research, conference = row
    return {**serialize(*row), 'abstract': research.abstract, 'researcher_name': entry.name_ar, 'research_field': research.research_field}

def write(db, user, data, entry_id=None):
    admin(user)
    research, conference = db.get(ResearchSubmission, data.submission_id), db.get(Conference, data.conference_id)
    if not research or not conference:
        raise ApplicationError(422, 'Select an existing research submission and conference')
    if research.status != 'published' or not (research.abstract or '').strip():
        raise ApplicationError(422, 'Select published research with an abstract')
    row = get_entry(db, entry_id) if entry_id else ExcellenceEntry(created_by=user.id)
    if data.visible and not row.image_object:
        raise ApplicationError(422, 'Save the entry, upload a portrait, then enable visibility')
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApplicationError(409, 'This research already has an entry in this conference')
    db.refresh(row)
    return serialize(row, research, conference)

def sanitize_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ApplicationError(422, 'Use a PNG, JPEG or WebP image up to 5 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > 16000000:
                    raise ValueError('Invalid image')
                image.load()
                image = ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((1200, 1200))
                output = BytesIO()
                image.save(output, 'WEBP', quality=90)
                return output.getvalue()
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApplicationError(422, 'Image is invalid or too large to decode')

def set_image(db, user, entry_id, data):
    admin(user)
    row = get_entry(db, entry_id)
    clean = sanitize_image(data)
    previous = row.image_object
    name = f'excellence/{entry_id}/{uuid4().hex}.webp'
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
    delete_object(previous)
    return {'image_url': presigned_avatar_url(name)}

def delete(db, user, entry_id):
    admin(user)
    row = get_entry(db, entry_id)
    image = row.image_object
    db.delete(row)
    db.commit()
    delete_object(image)
    return {'deleted': True}

def research_options(db, q='', limit=50):
    stmt = select(ResearchSubmission).where(ResearchSubmission.status == 'published', func.length(func.trim(ResearchSubmission.abstract)) > 0)
    if q.strip():
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        stmt = stmt.where(or_(ResearchSubmission.title.ilike(pattern, escape='\\'), ResearchSubmission.title_en.ilike(pattern, escape='\\')))
    rows = db.scalars(stmt.order_by(ResearchSubmission.id.desc()).limit(limit)).all()
    return [{'id': r.id, 'title': r.title, 'title_en': r.title_en or r.title, 'researcher_id': r.researcher_id} for r in rows]


def researcher_profile(db, entry_id):
    row = db.execute(query_base().where(ExcellenceEntry.id == entry_id, *public_conditions())).first()
    if not row:
        raise ApplicationError(404, 'Published excellence entry not found')
    entry, research, conference = row
    affiliation = db.get(UserAffiliation, research.researcher_id)
    approved = affiliation if affiliation and affiliation.approval_status == 'approved' else None
    school = db.get(School, approved.school_id) if approved and approved.school_id else None
    directorate = db.get(Directorate, approved.directorate_id) if approved and approved.directorate_id else None
    def place(value):
        return {'name_ar': value.name_ar, 'name_en': value.name_en or value.name_ar} if value else None
    publications = db.scalars(select(ResearchSubmission).where(
        ResearchSubmission.researcher_id == research.researcher_id,
        ResearchSubmission.status == 'published'
    ).order_by(ResearchSubmission.published_at.desc(), ResearchSubmission.id.desc())).all()
    return {
        'id': entry.id, 'name_ar': entry.name_ar, 'name_en': entry.name_en,
        'image_url': presigned_avatar_url(entry.image_object),
        'school': place(school), 'directorate': place(directorate),
        'specialization': approved.specialization if approved else None,
        'research_field': approved.research_field if approved else None,
        'publications': [{'id': r.id, 'title': r.title, 'title_en': r.title_en or r.title,
            'abstract': r.abstract, 'research_field': r.research_field,
            'publication_type': r.publication_type,
            'published_at': r.published_at.isoformat() if r.published_at else None} for r in publications]
    }

from sqlalchemy import select, or_, func
from app.models.education import School, Governorate, Directorate, EducationSource
from app.domain.education import normalize_query
from app.domain.education import school_payload


def school_query(filters):
    statement = select(School).outerjoin(Governorate, School.governorate_id == Governorate.id).outerjoin(Directorate, School.directorate_id == Directorate.id)
    for field in ("region", "governorate_id", "directorate_id", "school_type"):
        value = filters.get(field)
        if value == "unassigned" and field in ("governorate_id", "directorate_id"):
            statement = statement.where(getattr(School, field).is_(None))
        elif value:
            statement = statement.where(getattr(School, field) == value)
    for token in normalize_query(filters.get("q", "")).split():
        # SQLAlchemy binds parameters and escapes LIKE wildcard characters.
        statement = statement.where(or_(School.search_text.contains(token, autoescape=True),
            Governorate.search_text.contains(token, autoescape=True), Directorate.search_text.contains(token, autoescape=True)))
    if filters.get("location") == "located":
        statement = statement.where(School.latitude.is_not(None), School.longitude.is_not(None))
    elif filters.get("location") == "missing":
        statement = statement.where(School.latitude.is_(None))
    return statement


def school_detail(school_id, db):
    school = db.get(School, school_id)
    if school is None:
        return None
    return school_payload(school)

def school_points(bbox, f, limit, db):
    west, south, east, north = bbox
    statement = school_query(f).where(School.latitude.is_not(None), School.longitude.is_not(None),
        School.longitude.between(west, east), School.latitude.between(south, north))
    total = count(db, statement)
    return {"type": "FeatureCollection", "total": total, "truncated": total > limit, "features": [
        {"type": "Feature", "id": s.id, "geometry": {"type": "Point", "coordinates": [s.longitude, s.latitude]},
         "properties": {"id": s.id, "name_ar": s.name_ar, "name_en": s.name_en}}
        for s in db.scalars(statement.order_by(School.id).limit(limit))]}

def schools(f, offset, limit, db):
    statement = school_query(f)
    return {"total": count(db, statement), "offset": offset, "limit": limit,
            "items": [school_payload(s) for s in db.scalars(statement.order_by(School.name_ar, School.id).offset(offset).limit(limit))]}

def directorate_boundaries(db):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": d.id, "geometry": d.geometry, "properties": {"id": d.id, "name_ar": d.name_ar, "name_en": d.name_en}}
        for d in db.scalars(select(Directorate)) if d.geometry]}

def boundaries(db):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": g.id, "geometry": g.geometry,
         "properties": {"id": g.id, "name_ar": g.name_ar, "name_en": g.name_en, "region": g.region, "boundary_date": g.boundary_date}}
        for g in db.scalars(select(Governorate).order_by(Governorate.id))]}

def catalog(db):
    govs = db.scalars(select(Governorate).order_by(Governorate.id)).all()
    counts = dict(db.execute(select(School.governorate_id, func.count()).group_by(School.governorate_id)).all())
    linked = dict(db.execute(select(School.directorate_id, func.count()).group_by(School.directorate_id)).all())
    dirs = db.scalars(select(Directorate).order_by(Directorate.name_ar)).all()
    source = db.get(EducationSource, "schools-upload")
    safe_source = {k: v for k, v in (source.report if source else {}).items() if k not in ("duplicates", "notes")}
    return {
        "governorates": [{k: getattr(g, k) for k in ("id", "name_ar", "name_en", "region", "latitude", "longitude", "boundary_date")} | {"school_count": counts.get(g.id, 0)} for g in govs],
        "directorates": [{k: getattr(d, k) for k in ("id", "name_ar", "name_en", "governorate_id", "region", "category", "source_url", "source_date")} | {"linked_school_count": linked.get(d.id, 0), "has_boundary": bool(d.geometry)} for d in dirs],
        "school_types": list(db.scalars(select(School.school_type).distinct().order_by(School.school_type))),
        "total_schools": sum(counts.values()),
        "located_schools": count(db, select(School).where(School.latitude.is_not(None))),
        "unassigned_directorate_schools": linked.get(None, 0),
        "unassigned_governorate_schools": counts.get(None, 0),
        "source": safe_source,
        "ministry": {"name_ar": "وزارة التربية والتعليم العالي", "name_en": "Ministry of Education and Higher Education", "url": "https://www.moe.edu.ps/"},
    }

def count(db, statement):
    return db.scalar(select(func.count()).select_from(statement.subquery())) or 0

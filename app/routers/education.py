import math
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import get_current_user
from app.models.education import Directorate, EducationSource, Governorate, School
from app.services.education import normalize_query, school_payload, school_query

router = APIRouter(prefix="/api/education", tags=["Education directory"], dependencies=[Depends(get_current_user)])


def education_db(db: Session = Depends(get_db)):
    try:
        yield db
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Education data is unavailable. Check the database and run the education import.") from exc


def filters(q: str = Query("", max_length=160), region: Literal["PS01", "PS02"] | None = None,
            governorate_id: str | None = Query(None, max_length=80),
            directorate_id: str | None = Query(None, max_length=80),
            school_type: str | None = Query(None, max_length=60),
            location: Literal["all", "located", "missing"] = "all"):
    return dict(q=q, region=region, governorate_id=governorate_id,
                directorate_id=directorate_id, school_type=school_type, location=location)


def count(db, statement):
    return db.scalar(select(func.count()).select_from(statement.subquery())) or 0


@router.get("/catalog")
def catalog(db: Session = Depends(education_db)):
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


@router.get("/boundaries")
def boundaries(db: Session = Depends(education_db)):
    # Actual governorate geometry, never substitute it for directorate boundaries.
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": g.id, "geometry": g.geometry,
         "properties": {"id": g.id, "name_ar": g.name_ar, "name_en": g.name_en, "region": g.region, "boundary_date": g.boundary_date}}
        for g in db.scalars(select(Governorate).order_by(Governorate.id))]}


@router.get("/directorates/boundaries")
def directorate_boundaries(db: Session = Depends(education_db)):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": d.id, "geometry": d.geometry, "properties": {"id": d.id, "name_ar": d.name_ar, "name_en": d.name_en}}
        for d in db.scalars(select(Directorate)) if d.geometry]}


@router.get("/schools")
def schools(f: dict = Depends(filters), offset: int = Query(0, ge=0),
            limit: int = Query(25, ge=1, le=100), db: Session = Depends(education_db)):
    statement = school_query(f)
    return {"total": count(db, statement), "offset": offset, "limit": limit,
            "items": [school_payload(s) for s in db.scalars(statement.order_by(School.name_ar, School.id).offset(offset).limit(limit))]}


def parse_bbox(value):
    try:
        west, south, east, north = [float(v) for v in value.split(",")]
        if not all(math.isfinite(v) for v in (west, south, east, north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError()
        return west, south, east, north
    except (ValueError, TypeError):
        raise HTTPException(422, "bbox must be west,south,east,north in WGS84 degrees")


@router.get("/schools/points")
def school_points(bbox: str = Query(..., max_length=120), f: dict = Depends(filters),
                  limit: int = Query(2000, ge=1, le=5000), db: Session = Depends(education_db)):
    west, south, east, north = parse_bbox(bbox)
    statement = school_query(f).where(School.latitude.is_not(None), School.longitude.is_not(None),
        School.longitude.between(west, east), School.latitude.between(south, north))
    total = count(db, statement)
    return {"type": "FeatureCollection", "total": total, "truncated": total > limit, "features": [
        {"type": "Feature", "id": s.id, "geometry": {"type": "Point", "coordinates": [s.longitude, s.latitude]},
         "properties": {"id": s.id, "name_ar": s.name_ar, "name_en": s.name_en}}
        for s in db.scalars(statement.order_by(School.id).limit(limit))]}


@router.get("/schools/{school_id}")
def school_detail(school_id: str, db: Session = Depends(education_db)):
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(404, "School not found")
    return school_payload(school)

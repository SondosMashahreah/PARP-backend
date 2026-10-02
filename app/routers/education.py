from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import get_current_user
from app.services import education as education_service

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


@router.get("/catalog")
def catalog(db: Session = Depends(education_db)):
    return education_service.catalog(db)


@router.get("/boundaries")
def boundaries(db: Session = Depends(education_db)):
    # Actual governorate geometry, never substitute it for directorate boundaries.
    return education_service.boundaries(db)


@router.get("/directorates/boundaries")
def directorate_boundaries(db: Session = Depends(education_db)):
    return education_service.directorate_boundaries(db)


@router.get("/schools")
def schools(f: dict = Depends(filters), offset: int = Query(0, ge=0),
            limit: int = Query(25, ge=1, le=100), db: Session = Depends(education_db)):
    return education_service.schools(f, offset, limit, db)

@router.get("/schools/points")
def school_points(bbox: str = Query(..., max_length=120), f: dict = Depends(filters),
                  limit: int = Query(2000, ge=1, le=5000), db: Session = Depends(education_db)):
    return education_service.school_points(bbox, f, limit, db)


@router.get("/schools/{school_id}")
def school_detail(school_id: str, db: Session = Depends(education_db)):
    return education_service.school_detail(school_id, db)

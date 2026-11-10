"""Public, minimal institution names and IDs for self-registration.

Existing authenticated education/map routes remain protected. No coordinates,
search source text, or personal data are returned by these endpoints.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.education import normalize_query
from app.models.education import Directorate, Governorate, School

router = APIRouter(prefix='/api/education/public', tags=['Public institution choices'])


def _label(row):
    return {'id': row.id, 'name_ar': row.name_ar, 'name_en': row.name_en or row.name_ar,
            'governorate_id': row.governorate_id}


@router.get('/institutions')
def institutions(db: Session = Depends(get_db)):
    govs = db.scalars(select(Governorate).order_by(Governorate.name_ar)).all()
    dirs = db.scalars(select(Directorate).order_by(Directorate.name_ar)).all()
    return {
        'governorates': [{'id': g.id, 'name_ar': g.name_ar, 'name_en': g.name_en or g.name_ar} for g in govs],
        'directorates': [_label(d) for d in dirs],
    }


@router.get('/schools')
def schools(q: str = Query('', max_length=120), directorate_id: str | None = Query(None, max_length=80),
            selected_id: str | None = Query(None, max_length=80), limit: int = Query(30, ge=1, le=50),
            db: Session = Depends(get_db)):
    stmt = select(School)
    if directorate_id:
        # Unlinked schools can be nominated; server approval validates the affiliation.
        stmt = stmt.where(or_(School.directorate_id == directorate_id, School.directorate_id.is_(None)))
    if q.strip():
        normalized = normalize_query(q)
        stmt = stmt.where(or_(School.name_ar.ilike('%' + q.strip() + '%'),
                              School.name_en.ilike('%' + q.strip() + '%'),
                              School.national_code.ilike('%' + q.strip() + '%'),
                              School.search_text.ilike('%' + normalized + '%')))
    elif not directorate_id:
        stmt = stmt.where(False)
    rows = db.scalars(stmt.order_by(School.name_ar, School.id).limit(limit)).all()
    if selected_id and not any(s.id == selected_id for s in rows):
        selected = db.get(School, selected_id)
        if selected:
            rows.append(selected)
    return {'items': [_label(s) | {'directorate_id': s.directorate_id} for s in rows]}

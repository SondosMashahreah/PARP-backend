from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import get_current_user
from app.schemas.excellence import ExcellenceWrite
from app.services import excellence as service
router = APIRouter(prefix='/api/excellence', tags=['Hall of excellence'])

def administrator(user=Depends(get_current_user)):
    service.admin(user)
    return user

@router.get('')
def entries(q: str = Query('', max_length=150), year: int | None = Query(None, ge=1900, le=2200), conference_id: int | None = Query(None, gt=0), offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100), db: Session = Depends(get_db)):
    return service.list_entries(db, q=q, year=year, conference_id=conference_id, offset=offset, limit=limit)

@router.get('/filters')
def filters(db: Session = Depends(get_db)):
    return service.filters(db)

@router.get('/admin')
def admin_entries(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user=Depends(administrator)):
    return service.list_entries(db, public=False, offset=offset, limit=limit)

@router.get('/admin/research')
def research(q: str = Query('', max_length=150), db: Session = Depends(get_db), user=Depends(administrator)):
    return service.research_options(db, q)

@router.post('/admin', status_code=201)
def create(data: ExcellenceWrite, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.write(db, user, data)

@router.put('/admin/{entry_id}')
def update(entry_id: int, data: ExcellenceWrite, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.write(db, user, data, entry_id)

@router.post('/admin/{entry_id}/image')
async def image(entry_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(administrator)):
    return service.set_image(db, user, entry_id, await file.read(service.MAX_IMAGE_BYTES + 1))

@router.delete('/admin/{entry_id}')
def delete(entry_id: int, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.delete(db, user, entry_id)

@router.get('/{entry_id}/abstract')
def abstract(entry_id: int, db: Session = Depends(get_db)):
    return service.abstract(db, entry_id)

@router.get('/{entry_id}/researcher')
def researcher(entry_id: int, db: Session = Depends(get_db)):
    return service.researcher_profile(db, entry_id)

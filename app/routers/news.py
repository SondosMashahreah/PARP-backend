from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import get_current_user
from app.schemas.news import NewsWrite
from app.services import news as service

router = APIRouter(prefix='/api/news', tags=['News'])

def administrator(user=Depends(get_current_user)):
    service.admin(user)
    return user

@router.get('')
def articles(q: str = Query('', max_length=150), offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100), db: Session = Depends(get_db)):
    return service.list_articles(db, q=q, offset=offset, limit=limit)

@router.get('/admin')
def admin_articles(offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100), db: Session = Depends(get_db), user=Depends(administrator)):
    return service.list_articles(db, public=False, offset=offset, limit=limit)

@router.get('/admin/{article_id}')
def admin_detail(article_id: int, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.serialize(service.get_article(db, article_id, False), full=True, private=True)

@router.post('/admin', status_code=201)
def create(data: NewsWrite, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.write(db, user, data)

@router.put('/admin/{article_id}')
def update(article_id: int, data: NewsWrite, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.write(db, user, data, article_id)

@router.post('/admin/{article_id}/image')
async def image(article_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(administrator)):
    return service.set_image(db, user, article_id, await file.read(service.MAX_IMAGE_BYTES + 1))

@router.delete('/admin/{article_id}')
def delete(article_id: int, db: Session = Depends(get_db), user=Depends(administrator)):
    return service.delete(db, user, article_id)

@router.get('/{article_id}')
def detail(article_id: int, db: Session = Depends(get_db)):
    return service.serialize(service.get_article(db, article_id), full=True)

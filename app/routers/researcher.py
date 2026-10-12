from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.researcher import DraftContent, DraftSave, ProgressSave
from app.services import researcher, workflow

router = APIRouter(prefix='/api/researcher', tags=['Researcher workspace'])

@router.get('/me')
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.overview(db, user)

@router.post('/drafts', status_code=201)
def create(data: DraftContent, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.create_draft(db, user, data)

@router.put('/drafts/{draft_id}')
def save(draft_id: int, data: DraftSave, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.save_draft(db, user, draft_id, data)

@router.post('/drafts/{draft_id}/submit')
async def submit(draft_id: int, revision: int = Form(..., ge=1), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.submit_draft(db, user, draft_id, revision, file.filename or 'research', file.content_type or '', await file.read(workflow.MAX_RESEARCH_BYTES + 1))

@router.put('/users/{user_id}/training')
def training(user_id: int, data: ProgressSave, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.record_progress(db, user, user_id, data)

@router.post('/users/{user_id}/certificates', status_code=201)
async def certificate(user_id: int, title: str = Form(..., min_length=1, max_length=250), issuer: str = Form(..., min_length=1, max_length=250), file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return researcher.issue_certificate(db, user, user_id, title, issuer, await file.read(5 * 1024 * 1024 + 1))

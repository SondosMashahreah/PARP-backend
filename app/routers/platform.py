from fastapi import APIRouter, Depends, Form, File, UploadFile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.routers.dependencies import get_current_user
from app.schemas.platform import (
    PaymentUpdate,
    ConferenceCreate,
    ParticipationDecision,
    NoticeCreate,
    AdminUserCreate,
    CommitteeLogin,
    PasswordChange,
)
from app.services import platform as service
from app.services.workflow import ensure_role

router = APIRouter(prefix="/api/platform", tags=["Platform management"])


@router.get("/payments")
def payments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return service.payments(db, user)


@router.post("/research/{submission_id}/payment")
def request_payment(
    submission_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return service.request_payment(db, user, submission_id)


@router.put("/payments/{submission_id}")
def update_payment(
    submission_id: int,
    data: PaymentUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return service.update_payment(db, user, submission_id, data)


@router.get("/conferences")
def conferences(db: Session = Depends(get_db)):
    return service.conferences(db)


@router.post("/conferences")
def create_conference(
    data: ConferenceCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return service.create_conference(db, user, data)


@router.get("/participations")
def participations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return service.participations(db, user)


@router.post("/conferences/{conference_id}/participate")
async def participate(
    conference_id: int,
    title: str = Form(..., min_length=2, max_length=500),
    abstract: str = Form(..., min_length=2, max_length=12000),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ensure_role(user, "researcher")
    return service.participate(
        db,
        user,
        conference_id,
        title,
        abstract,
        file.filename,
        await file.read(25 * 1024 * 1024 + 1),
    )


@router.put("/participations/{participation_id}")
def decide_participation(
    participation_id: int,
    data: ParticipationDecision,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return service.decide_participation(db, user, participation_id, data)


@router.post("/conferences/{conference_id}/notices")
def notify(
    conference_id: int,
    data: NoticeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return service.notify_conference(db, user, conference_id, data.text)


@router.get("/notices")
def notices(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return service.notices(db, user)


@router.post("/users")
def create_user(
    data: AdminUserCreate, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return service.create_user(db, user, data)


@router.post("/committee/login")
def committee_login(data: CommitteeLogin, db: Session = Depends(get_db)):
    return service.committee_login(db, data)


@router.put("/committee/password")
def change_password(
    data: PasswordChange, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return service.change_password(db, user, data)


@router.get("/statistics")
def statistics(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return service.statistics(db, user)


@router.get("/map")
def map_data(db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_role(user, "decision_maker", "directorate_manager")
    return service.statistics(db, user)


from app.schemas.platform import CommitteeSetup


@router.put("/users/{user_id}/committee")
def configure_committee(
    user_id: int,
    data: CommitteeSetup,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return service.configure_committee(db, user, user_id, data)

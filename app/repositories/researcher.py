from sqlalchemy import select
from app.models.researcher import ResearchDraft, TrainingProgress, ResearcherCertificate


def owned_draft(db, user_id, draft_id):
    return db.scalar(select(ResearchDraft).where(ResearchDraft.id == draft_id, ResearchDraft.researcher_id == user_id).with_for_update())


def drafts(db, user_id):
    return db.scalars(select(ResearchDraft).where(ResearchDraft.researcher_id == user_id, ResearchDraft.submission_id.is_(None)).order_by(ResearchDraft.updated_at.desc())).all()


def training(db, user_id):
    return db.scalars(select(TrainingProgress).where(TrainingProgress.user_id == user_id).order_by(TrainingProgress.updated_at.desc())).all()


def certificates(db, user_id):
    return db.scalars(select(ResearcherCertificate).where(ResearcherCertificate.user_id == user_id).order_by(ResearcherCertificate.issued_at.desc())).all()

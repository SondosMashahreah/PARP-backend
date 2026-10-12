"""Additive schema creation. Retired supervisor accounts are preserved and disabled."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import app
from app.core.database import Base, engine
from app.models.user import User
from app.models.platform import (
    PublicationPayment,
    Conference,
    ConferenceParticipation,
    PlatformNotice,
    CommitteeCredential,
)
from app.models.researcher import ResearchDraft, TrainingProgress, ResearcherCertificate


def main():
    for model in (
        ResearchDraft,
        TrainingProgress,
        ResearcherCertificate,
        PublicationPayment,
        Conference,
        ConferenceParticipation,
        PlatformNotice,
        CommitteeCredential,
    ):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        rows = db.scalars(select(User).where(User.role == "supervisor")).all()
        for row in rows:
            row.is_active = False
        db.commit()
        print(
            f"Ready. {len(rows)} retired supervisor accounts preserved and disabled. Reassign explicitly in admin dashboard."
        )


if __name__ == "__main__":
    main()

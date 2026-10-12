"""Create only the three new workspace tables; never alter or delete existing data."""
from app.core.database import engine
from app.models import education, user, workflow  # noqa: F401 - register referenced tables
from app.models.researcher import ResearchDraft, TrainingProgress, ResearcherCertificate

if __name__ == '__main__':
    for model in (ResearchDraft, TrainingProgress, ResearcherCertificate):
        model.__table__.create(engine, checkfirst=True)
    print('Researcher workspace tables are ready.')

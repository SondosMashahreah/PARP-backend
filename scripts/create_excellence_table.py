"""Create only the additive excellence table. Existing PARP tables must exist."""
from app.core.database import engine
from app.models.user import User  # noqa: F401
from app.models.workflow import ResearchSubmission  # noqa: F401
from app.models.platform import Conference  # noqa: F401
from app.models.excellence import ExcellenceEntry
if __name__ == '__main__':
    ExcellenceEntry.__table__.create(engine, checkfirst=True)
    print('Excellence table is ready; existing data was not changed.')

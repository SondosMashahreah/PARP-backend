"""Actual national research counts; directorate managers see published work only.

Each ResearchSubmission is counted exactly once; drafts and practices are excluded.
No fabricated counts, coordinates or user-identifying details are returned.
"""
from sqlalchemy import case, func, select
from app.models.education import Directorate, Governorate, School
from app.models.workflow import ResearchSubmission, UserAffiliation
from app.services.workflow import ensure_role, role_of


def research_governorates(db, user):
    ensure_role(user, "decision_maker", "directorate_manager")
    limited = role_of(user) == "directorate_manager"
    # Countrywide aggregate counts are safe for directorate managers only when
    # limited to already-published work. Do not expose unpublished other-dir data.
    r = ResearchSubmission
    # Use the submission governorate only when it exists in the canonical
    # education directory. Otherwise fall back to verified school/directorate IDs.
    governorate_id = func.coalesce(
        Governorate.id, School.governorate_id, Directorate.governorate_id
    )
    statement = (
        select(
            governorate_id.label("governorate_id"),
            func.count(r.id).label("research_count"),
            func.sum(case((r.status == "published", 1), else_=0)).label("published_count"),
        )
        .select_from(r)
        .outerjoin(School, School.id == r.school_id)
        .outerjoin(Directorate, Directorate.id == r.directorate_id)
        .outerjoin(Governorate, Governorate.id == r.governorate_id)
        .where(r.publication_type == "research")
    )
    if limited:
        statement = statement.where(r.status == "published")
    grouped = db.execute(statement.group_by(governorate_id)).all()
    governorates = db.scalars(select(Governorate).order_by(Governorate.name_ar)).all()
    known_ids = {item.id for item in governorates}
    counts = {identifier: (int(count), int(published or 0)) for identifier, count, published in grouped if identifier in known_ids}
    unassigned = sum(int(count) for identifier, count, _ in grouped if identifier not in known_ids)
    unassigned_published = sum(int(published or 0) for identifier, _, published in grouped if identifier not in known_ids)
    rows = [
        {
            "id": item.id,
            "name_ar": item.name_ar,
            "name_en": item.name_en,
            "research_count": counts.get(item.id, (0, 0))[0],
            "published_count": counts.get(item.id, (0, 0))[1],
        }
        for item in governorates
    ]
    return {
        "metric": "registered_research",
        "scope": "national_published" if limited else "national",
        "total_research": unassigned + sum(row["research_count"] for row in rows),
        "published_research": unassigned_published + sum(row["published_count"] for row in rows),
        "unassigned_research": unassigned,
        "active_governorates": sum(row["research_count"] > 0 for row in rows),
        "max_research_count": max((row["research_count"] for row in rows), default=0),
        "governorates": rows,
    }

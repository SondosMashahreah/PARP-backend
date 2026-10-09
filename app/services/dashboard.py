from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.roles import ROLE_CAPABILITIES, SYSTEM_ADMIN, normalize_role
from app.models.education import Directorate, Governorate, School
from app.models.user import User
from app.models.workflow import (
    ProblemRecord,
    RecommendationRecord,
    ResearchSubmission,
    ReviewAssignment,
    UserAffiliation,
    WorkflowEvent,
)
from app.services.workflow import ensure_role, serialize_affiliation_request


WORKFLOW_STATUSES = (
    "submitted",
    "under_review",
    "revision_requested",
    "approved",
    "rejected",
    "practice_suggested",
    "published",
)


def _count(db: Session, model, *criteria) -> int:
    statement = select(func.count()).select_from(model)
    if criteria:
        statement = statement.where(*criteria)
    return int(db.scalar(statement) or 0)


def _group_counts(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(key or "unknown"): int(value or 0) for key, value in rows}


def _role_distribution(db: Session) -> list[dict]:
    totals: dict[str, int] = {}
    for raw_role, value in db.execute(select(User.role, func.count()).group_by(User.role)).all():
        role = normalize_role(raw_role)
        totals[role] = totals.get(role, 0) + int(value or 0)
    return [
        {"key": role, "value": value}
        for role, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def _research_statuses(db: Session) -> dict[str, int]:
    raw = _group_counts(db, ResearchSubmission.status)
    return {status: raw.get(status, 0) for status in WORKFLOW_STATUSES}


def _recent_activity(db: Session) -> list[dict]:
    rows = db.execute(
        select(WorkflowEvent, User.full_name, ResearchSubmission.title)
        .join(User, User.id == WorkflowEvent.actor_id)
        .join(ResearchSubmission, ResearchSubmission.id == WorkflowEvent.submission_id)
        .order_by(WorkflowEvent.created_at.desc())
        .limit(12)
    ).all()
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "actor_name": actor_name,
            "submission_id": event.submission_id,
            "submission_title": submission_title,
            "created_at": event.created_at,
        }
        for event, actor_name, submission_title in rows
    ]


def _pending_affiliations(db: Session) -> list[dict]:
    rows = db.scalars(
        select(UserAffiliation)
        .where(UserAffiliation.approval_status == "requested")
        .order_by(UserAffiliation.requested_at.asc())
        .limit(12)
    ).all()
    return [serialize_affiliation_request(db, row) for row in rows]


def summary(db: Session, actor: User) -> dict:
    ensure_role(actor, SYSTEM_ADMIN)
    research_statuses = _research_statuses(db)
    assignment_counts = _group_counts(db, ReviewAssignment.status)
    recommendation_counts = _group_counts(db, RecommendationRecord.status)

    return {
        "generated_at": datetime.now(timezone.utc),
        "user": {
            "id": actor.id,
            "full_name": actor.full_name,
            "email": actor.email,
            "role": normalize_role(actor.role),
        },
        "capabilities": ROLE_CAPABILITIES.get(SYSTEM_ADMIN, []),
        "metrics": {
            "users_total": _count(db, User),
            "users_active": _count(db, User, User.is_active.is_(True)),
            "users_verified": _count(db, User, User.is_verified.is_(True)),
            "pending_affiliations": _count(
                db,
                UserAffiliation,
                UserAffiliation.approval_status == "requested",
            ),
            "research_total": _count(db, ResearchSubmission),
            "review_assignments": _count(db, ReviewAssignment),
            "reviews_waiting": assignment_counts.get("invited", 0) + assignment_counts.get("accepted", 0),
            "recommendations": _count(db, RecommendationRecord),
            "recommendations_open": recommendation_counts.get("new", 0) + recommendation_counts.get("under_review", 0),
            "problems": _count(db, ProblemRecord),
        },
        "research_statuses": research_statuses,
        "role_distribution": _role_distribution(db),
        "education": {
            "governorates": _count(db, Governorate),
            "directorates": _count(db, Directorate),
            "schools": _count(db, School),
            "schools_with_coordinates": _count(db, School, School.latitude.is_not(None), School.longitude.is_not(None)),
        },
        "pending_affiliations": _pending_affiliations(db),
        "recent_activity": _recent_activity(db),
    }


def _serialize_admin_user(db: Session, user: User) -> dict:
    affiliation = db.get(UserAffiliation, user.id)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": normalize_role(user.role),
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "affiliation": {
            "governorate_id": affiliation.governorate_id,
            "directorate_id": affiliation.directorate_id,
            "school_id": affiliation.school_id,
            "specialization": affiliation.specialization,
            "research_field": affiliation.research_field,
            "approval_status": affiliation.approval_status,
        } if affiliation else None,
    }


def users(
    db: Session,
    actor: User,
    *,
    q: str = "",
    role: str | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    ensure_role(actor, SYSTEM_ADMIN)
    statement = select(User)

    normalized_query = q.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )

    if role:
        normalized_role = normalize_role(role)
        if normalized_role == "researcher":
            statement = statement.where(User.role.in_(["researcher", "user"]))
        else:
            statement = statement.where(User.role == normalized_role)

    if active is not None:
        statement = statement.where(User.is_active.is_(active))

    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = db.scalars(
        statement.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
    ).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_admin_user(db, row) for row in rows],
    }

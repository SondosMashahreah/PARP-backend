import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import ApplicationError
from app.domain.roles import (
    ALL_AUTH_ROLES,
    DECISION_MAKER,
    DIRECTORATE_MANAGER,
    ORGANIZING_COMMITTEE,
    RESEARCHER,
    REVIEWER,
    SCHOOL_MANAGER,
    SCIENTIFIC_COMMITTEE,
    SYSTEM_ADMIN,
    normalize_role,
)
from app.infrastructure.minio_storage import presigned_file_url, upload_research_file
from app.models.education import Directorate, Governorate, School
from app.models.user import User
from app.models.workflow import (
    ProblemRecord,
    RecommendationRecord,
    ResearchReview,
    ResearchSubmission,
    ResearchVersion,
    ReviewAssignment,
    UserAffiliation,
    WorkflowEvent,
)

MAX_RESEARCH_BYTES = 25 * 1024 * 1024
ALLOWED_RESEARCH_TYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _now():
    return datetime.now(timezone.utc)


def role_of(user: User) -> str:
    return normalize_role(user.role)


def ensure_role(user: User, *roles: str) -> None:
    if role_of(user) not in set(roles):
        raise ApplicationError(403, "You do not have permission for this action")


def affiliation(db: Session, user_id: int) -> UserAffiliation | None:
    return db.get(UserAffiliation, user_id)


def _validate_education_ids(db: Session, governorate_id, directorate_id, school_id):
    governorate = db.get(Governorate, governorate_id) if governorate_id else None
    directorate = db.get(Directorate, directorate_id) if directorate_id else None
    school = db.get(School, school_id) if school_id else None
    if governorate_id and not governorate:
        raise ApplicationError(422, "Unknown governorate")
    if directorate_id and not directorate:
        raise ApplicationError(422, "Unknown directorate")
    if school_id and not school:
        raise ApplicationError(422, "Unknown school")
    if governorate and directorate and directorate.governorate_id and directorate.governorate_id != governorate.id:
        raise ApplicationError(422, "Directorate does not belong to the selected governorate")
    if governorate and school and school.governorate_id and school.governorate_id != governorate.id:
        raise ApplicationError(422, "School does not belong to the selected governorate")
    if directorate and school and school.directorate_id and school.directorate_id != directorate.id:
        raise ApplicationError(422, "School is already linked to another directorate")


def set_affiliation_request(db: Session, user: User, data) -> dict:
    _validate_education_ids(db, data.governorate_id, data.directorate_id, data.school_id)
    row = affiliation(db, user.id) or UserAffiliation(user_id=user.id)
    if not db.get(UserAffiliation, user.id):
        db.add(row)
    row.governorate_id = data.governorate_id
    row.directorate_id = data.directorate_id
    row.school_id = data.school_id
    row.specialization = data.specialization
    row.research_field = data.research_field
    row.approval_status = "requested"
    row.approved_by_id = None
    row.approved_at = None
    row.requested_at = _now()
    db.commit()
    db.refresh(row)
    return serialize_affiliation(row)


def serialize_affiliation(row: UserAffiliation | None) -> dict | None:
    if not row:
        return None
    return {
        "user_id": row.user_id,
        "governorate_id": row.governorate_id,
        "directorate_id": row.directorate_id,
        "school_id": row.school_id,
        "specialization": row.specialization,
        "research_field": row.research_field,
        "approval_status": row.approval_status,
        "approved_by_id": row.approved_by_id,
        "approved_at": row.approved_at,
    }


def approve_affiliation(db: Session, actor: User, target_user_id: int) -> dict:
    ensure_role(actor, SCHOOL_MANAGER, DIRECTORATE_MANAGER, SYSTEM_ADMIN)
    target = affiliation(db, target_user_id)
    if not target:
        raise ApplicationError(404, "Affiliation request not found")
    target_user = db.get(User, target_user_id)
    if role_of(actor) != SYSTEM_ADMIN and (target_user_id == actor.id or not target_user or role_of(target_user) != RESEARCHER):
        raise ApplicationError(403, "Only the administrator may approve institutional managers")
    actor_aff = affiliation(db, actor.id)
    actor_role = role_of(actor)
    if actor_role == SCHOOL_MANAGER:
        if not actor_aff or actor_aff.approval_status != "approved" or not actor_aff.school_id or actor_aff.school_id != target.school_id:
            raise ApplicationError(403, "User is outside your school")
    elif actor_role == DIRECTORATE_MANAGER:
        if not actor_aff or actor_aff.approval_status != "approved" or not actor_aff.directorate_id or actor_aff.directorate_id != target.directorate_id:
            raise ApplicationError(403, "User is outside your directorate")
    _validate_education_ids(db, target.governorate_id, target.directorate_id, target.school_id)
    if target.school_id and target.directorate_id:
        school = db.get(School, target.school_id)
        if school and school.directorate_id is None:
            # The source school workbook has no school→directorate link. Only fill this
            # relationship after an authorized school/directorate/system-admin approval.
            school.directorate_id = target.directorate_id
    target.approval_status = "approved"
    target.approved_by_id = actor.id
    target.approved_at = _now()
    db.commit()
    return serialize_affiliation(target)


def _event(db: Session, submission: ResearchSubmission, actor: User, event_type: str, to_status: str, note: str = ""):
    old = submission.status
    submission.status = to_status
    submission.updated_at = _now()
    db.add(WorkflowEvent(
        submission_id=submission.id,
        actor_id=actor.id,
        event_type=event_type,
        from_status=old,
        to_status=to_status,
        note=note or None,
    ))


def _parse_form_json(value: str) -> dict:
    try:
        result = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ApplicationError(422, "form_json must contain valid JSON") from exc
    if not isinstance(result, dict):
        raise ApplicationError(422, "form_json must be a JSON object")
    return result


def _research_extension(content_type: str | None, filename: str | None) -> str:
    ctype = (content_type or "").lower()
    if ctype in ALLOWED_RESEARCH_TYPES:
        return ALLOWED_RESEARCH_TYPES[ctype]
    suffix = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if suffix in {"pdf", "doc", "docx"}:
        return suffix
    raise ApplicationError(400, "Research file must be PDF, DOC or DOCX")


def _read_keywords(form_data: dict) -> list:
    value = form_data.get("keywords", [])
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:100] for item in value if str(item).strip()][:20]


def create_submission(
    db: Session,
    user: User,
    *,
    title: str,
    research_field: str,
    problem: str,
    recommendations: str,
    abstract: str,
    form_json: str,
    file_name: str,
    content_type: str,
    file_bytes: bytes,
    draft=None,
) -> dict:
    ensure_role(user, RESEARCHER)
    aff = affiliation(db, user.id)
    if not aff or aff.approval_status != "approved" or not aff.school_id or not aff.directorate_id:
        raise ApplicationError(409, "Your school/directorate affiliation must be approved before submitting research")
    if len(file_bytes) > MAX_RESEARCH_BYTES:
        raise ApplicationError(413, "Research file must be 25 MB or smaller")
    extension = _research_extension(content_type, file_name)
    form_data = _parse_form_json(form_json)
    kind = form_data.get('kind', 'research')
    if kind not in ('research', 'practice'): raise ApplicationError(422, 'Invalid submission kind')
    if not (abstract or form_data.get('abstract') or '').strip(): raise ApplicationError(422, 'An abstract is required')
    submission = ResearchSubmission(
        publication_type=kind,
        researcher_id=user.id,
        governorate_id=aff.governorate_id,
        directorate_id=aff.directorate_id,
        school_id=aff.school_id,
        title=" ".join(title.split()),
        title_en=form_data.get("title_en"),
        abstract=abstract.strip() or form_data.get("abstract"),
        research_field=" ".join(research_field.split()),
        keywords=_read_keywords(form_data),
        problem=problem.strip(),
        research_question=form_data.get("research_question"),
        intervention=form_data.get("intervention"),
        results=form_data.get("results"),
        recommendations=recommendations.strip() or form_data.get("recommendations"),
        status="submitted",
    )
    db.add(submission)
    db.flush()
    object_name = upload_research_file(
        user.id,
        submission.id,
        1,
        file_bytes,
        content_type or "application/octet-stream",
        extension,
    )
    db.add(ResearchVersion(
        submission_id=submission.id,
        version_number=1,
        file_object_name=object_name,
        original_file_name=(file_name or f"research.{extension}")[:255],
        content_type=content_type or "application/octet-stream",
        form_data=form_data,
    ))
    db.add(WorkflowEvent(
        submission_id=submission.id,
        actor_id=user.id,
        event_type="submitted",
        from_status=None,
        to_status="submitted",
        note="Initial research submission",
    ))
    if draft is not None:
        draft.submission_id = submission.id
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission, user)


def resubmit(
    db: Session,
    user: User,
    submission_id: int,
    *,
    form_json: str,
    file_name: str,
    content_type: str,
    file_bytes: bytes,
) -> dict:
    ensure_role(user, RESEARCHER)
    submission = db.scalar(select(ResearchSubmission).where(ResearchSubmission.id == submission_id).with_for_update())
    if not submission or submission.researcher_id != user.id:
        raise ApplicationError(404, "Research submission not found")
    if submission.status not in {"revision_requested", "rejected"}:
        raise ApplicationError(409, "This research is not waiting for a revised version")
    if len(file_bytes) > MAX_RESEARCH_BYTES:
        raise ApplicationError(413, "Research file must be 25 MB or smaller")
    extension = _research_extension(content_type, file_name)
    next_version = submission.current_version + 1
    form_data = _parse_form_json(form_json)
    from app.schemas.researcher import DraftContent
    from pydantic import ValidationError
    allowed = set(DraftContent.model_fields) - {"keywords"}
    edits = {key: value for key, value in form_data.items() if key in allowed}
    try:
        validated = DraftContent(**edits)
    except ValidationError as exc:
        raise ApplicationError(422, "Invalid research fields") from exc
    for key in ("title", "research_field", "problem"):
        if key in edits and len(edits[key].strip()) < 2:
            raise ApplicationError(422, "Title, field and problem cannot be empty")
    for key in edits:
        setattr(submission, key, getattr(validated, key))
    if "keywords" in form_data:
        submission.keywords = _read_keywords(form_data)

    object_name = upload_research_file(
        user.id,
        submission.id,
        next_version,
        file_bytes,
        content_type or "application/octet-stream",
        extension,
    )
    db.add(ResearchVersion(
        submission_id=submission.id,
        version_number=next_version,
        file_object_name=object_name,
        original_file_name=(file_name or f"research.{extension}")[:255],
        content_type=content_type or "application/octet-stream",
        form_data=form_data,
    ))
    submission.current_version = next_version
    submission.publication_allowed = False
    _event(db, submission, user, "resubmitted", "submitted", f"Version {next_version}")
    for assignment in db.scalars(select(ReviewAssignment).where(ReviewAssignment.submission_id == submission.id)):
        assignment.status = "invited"
        assignment.accepted_at = None
        assignment.confidentiality_accepted = False
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission, user)


def assign_reviewer(db: Session, actor: User, submission_id: int, reviewer_id: int) -> dict:
    ensure_role(actor, SYSTEM_ADMIN)
    submission = db.get(ResearchSubmission, submission_id)
    reviewer = db.get(User, reviewer_id)
    if not submission:
        raise ApplicationError(404, "Research submission not found")
    if submission.status == "published":
        raise ApplicationError(409, "Published work cannot be reassigned")
    if not reviewer or role_of(reviewer) != REVIEWER or not reviewer.is_active:
        raise ApplicationError(422, "Selected user is not an active reviewer")
    assignment = db.scalar(select(ReviewAssignment).where(
        ReviewAssignment.submission_id == submission_id,
        ReviewAssignment.reviewer_id == reviewer_id,
    ))
    if assignment:
        assignment.status = "invited"
        assignment.accepted_at = None
        assignment.confidentiality_accepted = False
        assignment.assigned_by_id = actor.id
        assignment.assigned_at = _now()
    else:
        assignment = ReviewAssignment(
            submission_id=submission_id,
            reviewer_id=reviewer_id,
            assigned_by_id=actor.id,
        )
        db.add(assignment)
    _event(db, submission, actor, "reviewer_assigned", "under_review", f"Reviewer #{reviewer_id}")
    db.commit()
    db.refresh(assignment)
    return serialize_assignment(db, assignment, actor)


def accept_assignment(db: Session, user: User, assignment_id: int, confidentiality_accepted: bool) -> dict:
    ensure_role(user, REVIEWER)
    assignment = db.get(ReviewAssignment, assignment_id)
    if not assignment or assignment.reviewer_id != user.id:
        raise ApplicationError(404, "Review assignment not found")
    if not confidentiality_accepted:
        raise ApplicationError(422, "Confidentiality must be accepted before reviewing")
    assignment.confidentiality_accepted = True
    assignment.accepted_at = _now()
    assignment.status = "accepted"
    db.commit()
    return serialize_assignment(db, assignment, user)


def submit_review(db: Session, user: User, assignment_id: int, data) -> dict:
    ensure_role(user, REVIEWER)
    assignment = db.get(ReviewAssignment, assignment_id)
    if not assignment or assignment.reviewer_id != user.id:
        raise ApplicationError(404, "Review assignment not found")
    if not assignment.confidentiality_accepted or assignment.status not in {"accepted", "completed"}:
        raise ApplicationError(409, "Accept the review invitation and confidentiality first")
    submission = db.get(ResearchSubmission, assignment.submission_id)
    if not submission:
        raise ApplicationError(404, "Research submission not found")
    if submission.status == "published":
        raise ApplicationError(409, "Published work cannot be reviewed again")
    review = ResearchReview(
        assignment_id=assignment.id,
        submission_id=submission.id,
        reviewer_id=user.id,
        version_number=submission.current_version,
        recommendation=data.recommendation,
        comments=data.comments.strip(),
        rubric=data.rubric,
    )
    db.add(review)
    assignment.status = "completed"
    db.add(WorkflowEvent(
        submission_id=submission.id,
        actor_id=user.id,
        event_type="review_submitted",
        from_status=submission.status,
        to_status=submission.status,
        note=data.comments.strip()[:12000],
    ))
    db.commit()
    db.refresh(review)
    return {
        "id": review.id,
        "submission_id": review.submission_id,
        "version_number": review.version_number,
        "recommendation": review.recommendation,
        "comments": review.comments,
        "rubric": review.rubric,
        "created_at": review.created_at,
    }


def scientific_decision(db: Session, actor: User, submission_id: int, data) -> dict:
    ensure_role(actor, REVIEWER)
    submission = db.scalar(select(ResearchSubmission).where(ResearchSubmission.id == submission_id).with_for_update())
    if not submission:
        raise ApplicationError(404, "Research submission not found")
    assignment = db.scalar(select(ReviewAssignment).where(ReviewAssignment.submission_id == submission_id, ReviewAssignment.reviewer_id == actor.id))
    if not assignment or assignment.status != 'completed': raise ApplicationError(403, 'Complete the assigned review before a decision')
    if submission.status == 'published': raise ApplicationError(409, 'Published items cannot be changed')
    mapping = {
        "approve": "approved",
        "revision": "revision_requested",
        "reject": "rejected",
        "practice": "practice_suggested",
    }
    next_status = mapping[data.decision]
    submission.publication_allowed = data.decision == "approve"
    _event(db, submission, actor, "scientific_decision", next_status, data.note.strip())
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission, actor)


def _create_knowledge_outputs(db: Session, submission: ResearchSubmission):
    if submission.recommendations and not db.scalar(
        select(RecommendationRecord).where(RecommendationRecord.submission_id == submission.id)
    ):
        db.add(RecommendationRecord(
            submission_id=submission.id,
            text=submission.recommendations,
            research_field=submission.research_field,
            directorate_id=submission.directorate_id,
        ))
    if submission.problem and not db.scalar(
        select(ProblemRecord).where(ProblemRecord.submission_id == submission.id)
    ):
        db.add(ProblemRecord(
            submission_id=submission.id,
            text=submission.problem,
            research_field=submission.research_field,
            school_id=submission.school_id,
            directorate_id=submission.directorate_id,
        ))


def publish_research(db: Session, user: User, submission_id: int) -> dict:
    ensure_role(user, RESEARCHER)
    submission = db.scalar(select(ResearchSubmission).where(ResearchSubmission.id == submission_id).with_for_update())
    if not submission or submission.researcher_id != user.id:
        raise ApplicationError(404, "Research submission not found")
    if submission.status != "approved" or not submission.publication_allowed:
        raise ApplicationError(409, "Research can be published only after scientific approval")
    if submission.publication_type != 'research': raise ApplicationError(409, 'Use practice publication')
    from app.models.platform import PublicationPayment
    payment = db.get(PublicationPayment, submission.id)
    if not payment or not payment.confirmed or payment.paid_agorot < payment.required_agorot:
        raise ApplicationError(409, 'Administrator payment confirmation is required')
    submission.published_at = _now()
    _event(db, submission, user, "published", "published", "Published in the National Repository")
    _create_knowledge_outputs(db, submission)
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission, user)


def publish_as_practice(db: Session, user: User, submission_id: int) -> dict:
    ensure_role(user, RESEARCHER)
    submission = db.scalar(select(ResearchSubmission).where(ResearchSubmission.id == submission_id).with_for_update())
    if not submission or submission.researcher_id != user.id:
        raise ApplicationError(404, "Research submission not found")
    if not (submission.status == "practice_suggested" or (submission.publication_type == "practice" and submission.status == "approved" and submission.publication_allowed)):
        raise ApplicationError(409, "This submission was not proposed as a practice")
    submission.publication_type = "practice"
    submission.publication_allowed = True
    submission.published_at = _now()
    _event(db, submission, user, "published_as_practice", "published", "Published as a practice")
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission, user)


def latest_version(db: Session, submission: ResearchSubmission) -> ResearchVersion | None:
    return db.scalar(
        select(ResearchVersion)
        .where(
            ResearchVersion.submission_id == submission.id,
            ResearchVersion.version_number == submission.current_version,
        )
        .limit(1)
    )


def serialize_submission(db: Session, submission: ResearchSubmission, viewer: User | None = None) -> dict:
    author = db.get(User, submission.researcher_id)
    version = latest_version(db, submission)
    events = db.scalars(
        select(WorkflowEvent)
        .where(WorkflowEvent.submission_id == submission.id)
        .order_by(WorkflowEvent.created_at.asc())
    ).all()
    reviews = db.scalars(
        select(ResearchReview)
        .where(ResearchReview.submission_id == submission.id)
        .order_by(ResearchReview.created_at.desc())
    ).all()
    role = role_of(viewer) if viewer else ""
    can_see_reviews = viewer and (
        viewer.id == submission.researcher_id
        or any(review.reviewer_id == viewer.id for review in reviews)
    )
    assigned = viewer and role == REVIEWER and db.scalar(select(ReviewAssignment.id).where(ReviewAssignment.submission_id == submission.id, ReviewAssignment.reviewer_id == viewer.id, ReviewAssignment.confidentiality_accepted.is_(True)))
    private = bool(viewer and (viewer.id == submission.researcher_id or role == SYSTEM_ADMIN or assigned))
    full_text = private or (submission.publication_type == 'practice' and submission.status == 'published')
    return {
        "id": submission.id,
        "researcher_id": submission.researcher_id,
        "researcher_name": author.full_name if author else None,
        "governorate_id": submission.governorate_id,
        "directorate_id": submission.directorate_id,
        "school_id": submission.school_id,
        "title": submission.title,
        "title_en": submission.title_en,
        "abstract": submission.abstract,
        "research_field": submission.research_field,
        "keywords": submission.keywords,
        "problem": submission.problem if full_text else None,
        "research_question": submission.research_question if full_text else None,
        "intervention": submission.intervention if full_text else None,
        "results": submission.results if full_text else None,
        "recommendations": submission.recommendations if full_text else None,
        "status": submission.status,
        "current_version": submission.current_version,
        "publication_allowed": submission.publication_allowed,
        "publication_type": submission.publication_type,
        "published_at": submission.published_at,
        "created_at": submission.created_at,
        "updated_at": submission.updated_at,
        "file": {
            "name": version.original_file_name,
            "content_type": version.content_type,
            "url": presigned_file_url(version.file_object_name),
        } if version and full_text else None,
        "events": [{
            "event_type": event.event_type,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "note": event.note,
            "created_at": event.created_at,
        } for event in events] if private else [],
        "reviews": [{
            "id": review.id,
            "reviewer_id": review.reviewer_id,
            "version_number": review.version_number,
            "recommendation": review.recommendation,
            "comments": review.comments,
            "rubric": review.rubric,
            "created_at": review.created_at,
        } for review in reviews] if can_see_reviews else [],
    }


def serialize_assignment(db: Session, assignment: ReviewAssignment, viewer: User) -> dict:
    submission = db.get(ResearchSubmission, assignment.submission_id)
    return {
        "id": assignment.id,
        "status": assignment.status,
        "confidentiality_accepted": assignment.confidentiality_accepted,
        "accepted_at": assignment.accepted_at,
        "assigned_at": assignment.assigned_at,
        "submission": serialize_submission(db, submission, viewer) if submission else None,
    }


def _scope_statement(db: Session, user: User):
    statement = select(ResearchSubmission)
    role = role_of(user)
    aff = affiliation(db, user.id)
    if role == SCHOOL_MANAGER:
        if not aff or aff.approval_status != "approved" or not aff.school_id:
            return statement.where(False)
        return statement.where(ResearchSubmission.school_id == aff.school_id)
    if role in {DIRECTORATE_MANAGER}:
        if not aff or aff.approval_status != "approved" or not aff.directorate_id:
            return statement.where(False)
        return statement.where(ResearchSubmission.directorate_id == aff.directorate_id)
    return statement


def serialize_affiliation_request(db: Session, row: UserAffiliation) -> dict:
    target = db.get(User, row.user_id)
    return {
        "user": {
            "id": target.id,
            "full_name": target.full_name,
            "email": target.email,
            "role": role_of(target),
        } if target else {"id": row.user_id},
        "affiliation": serialize_affiliation(row),
    }


def _visible_submission_statement(db: Session, user: User):
    role = role_of(user)
    if role == RESEARCHER:
        return select(ResearchSubmission).where(ResearchSubmission.researcher_id == user.id)
    if role == REVIEWER:
        return (select(ResearchSubmission)
                .join(ReviewAssignment, ReviewAssignment.submission_id == ResearchSubmission.id)
                .where(ReviewAssignment.reviewer_id == user.id))
    if role in {SCHOOL_MANAGER, DIRECTORATE_MANAGER}:
        return _scope_statement(db, user)
    if role == SCIENTIFIC_COMMITTEE:
        return select(ResearchSubmission)
    return select(ResearchSubmission).where(False)


def _status_counts(db: Session, user: User) -> dict:
    # Count from the role-scoped query rather than exposing global workflow totals to every role.
    base = _visible_submission_statement(db, user)
    result = {}
    for status in ("submitted", "under_review", "revision_requested", "approved", "published"):
        result[status] = db.scalar(
            select(func.count()).select_from(base.where(ResearchSubmission.status == status).subquery())
        ) or 0
    return result

def workspace(db: Session, user: User) -> dict:
    role = role_of(user)
    payload = {
        "role": role,
        "affiliation": serialize_affiliation(affiliation(db, user.id)),
        "affiliation_requests": [],
        "submissions": [],
        "assignments": [],
        "reviewers": [],
        "recommendations": [],
        "problems": [],
        "users": [],
        "counts": {},
    }
    if role == RESEARCHER:
        rows = db.scalars(
            select(ResearchSubmission)
            .where(ResearchSubmission.researcher_id == user.id)
            .order_by(ResearchSubmission.updated_at.desc())
        ).all()
        payload["submissions"] = [serialize_submission(db, row, user) for row in rows]
    elif role == REVIEWER:
        rows = db.scalars(
            select(ReviewAssignment)
            .where(ReviewAssignment.reviewer_id == user.id)
            .order_by(ReviewAssignment.assigned_at.desc())
        ).all()
        payload["assignments"] = [serialize_assignment(db, row, user) for row in rows]
    elif role == SYSTEM_ADMIN:
        rows = db.scalars(select(ResearchSubmission).order_by(ResearchSubmission.updated_at.desc()).limit(200)).all()
        payload["submissions"] = [serialize_submission(db, row, user) for row in rows]
        reviewers = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
        payload["reviewers"] = []
        for row in reviewers:
            if role_of(row) != REVIEWER:
                continue
            reviewer_aff = affiliation(db, row.id)
            payload["reviewers"].append({
                "id": row.id,
                "full_name": row.full_name,
                "email": row.email,
                "specialization": reviewer_aff.specialization if reviewer_aff else None,
                "research_field": reviewer_aff.research_field if reviewer_aff else None,
            })
    elif role in {SCHOOL_MANAGER, DIRECTORATE_MANAGER}:
        rows = db.scalars(_scope_statement(db, user).order_by(ResearchSubmission.updated_at.desc()).limit(200)).all()
        payload["submissions"] = [serialize_submission(db, row, user) for row in rows]
        if role in {SCHOOL_MANAGER, DIRECTORATE_MANAGER}:
            actor_aff = affiliation(db, user.id)
            request_statement = select(UserAffiliation).where(UserAffiliation.approval_status == "requested")
            if role == SCHOOL_MANAGER and actor_aff and actor_aff.approval_status == "approved" and actor_aff.school_id:
                request_statement = request_statement.where(UserAffiliation.school_id == actor_aff.school_id)
            elif role == DIRECTORATE_MANAGER and actor_aff and actor_aff.approval_status == "approved" and actor_aff.directorate_id:
                request_statement = request_statement.where(UserAffiliation.directorate_id == actor_aff.directorate_id)
            else:
                request_statement = request_statement.where(False)
            pending = db.scalars(request_statement.order_by(UserAffiliation.requested_at.asc()).limit(200)).all()
            payload["affiliation_requests"] = [serialize_affiliation_request(db, row) for row in pending]
    elif role == DECISION_MAKER:
        recs = db.scalars(select(RecommendationRecord).order_by(RecommendationRecord.created_at.desc()).limit(200)).all()
        probs = db.scalars(select(ProblemRecord).order_by(ProblemRecord.created_at.desc()).limit(200)).all()
        payload["recommendations"] = [serialize_recommendation(row) for row in recs]
        payload["problems"] = [serialize_problem(row) for row in probs]
    elif role == ORGANIZING_COMMITTEE:
        pass

    if role == RESEARCHER:
        payload["counts"] = _status_counts(db, user)
    if role == SYSTEM_ADMIN:
        users = db.scalars(select(User).order_by(User.id.desc()).limit(300)).all()
        payload["users"] = [serialize_user_access(db, row) for row in users]
        pending = db.scalars(
            select(UserAffiliation)
            .where(UserAffiliation.approval_status == "requested")
            .order_by(UserAffiliation.requested_at.asc())
            .limit(300)
        ).all()
        payload["affiliation_requests"] = [serialize_affiliation_request(db, row) for row in pending]
    return payload


def serialize_user_access(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": role_of(user),
        "is_active": user.is_active,
        "affiliation": serialize_affiliation(affiliation(db, user.id)),
    }


def update_user_access(db: Session, actor: User, target_user_id: int, data) -> dict:
    ensure_role(actor, SYSTEM_ADMIN)
    target = db.get(User, target_user_id)
    if not target:
        raise ApplicationError(404, "User not found")
    if data.role not in ALL_AUTH_ROLES:
        raise ApplicationError(422, "Unsupported role")
    if role_of(target) == SYSTEM_ADMIN and (data.role != SYSTEM_ADMIN or data.is_active is False):
        active_admins = int(db.scalar(
            select(func.count()).select_from(User).where(
                User.role == SYSTEM_ADMIN,
                User.is_active.is_(True),
            )
        ) or 0)
        if active_admins <= 1:
            raise ApplicationError(409, "The last active system administrator cannot be disabled or demoted")
    _validate_education_ids(db, data.governorate_id, data.directorate_id, data.school_id)
    if data.school_id and data.directorate_id:
        school = db.get(School, data.school_id)
        if school and school.directorate_id is None:
            school.directorate_id = data.directorate_id
    target.role = data.role
    if data.is_active is not None:
        target.is_active = data.is_active
    row = affiliation(db, target.id) or UserAffiliation(user_id=target.id)
    if not db.get(UserAffiliation, target.id):
        db.add(row)
    row.governorate_id = data.governorate_id
    row.directorate_id = data.directorate_id
    row.school_id = data.school_id
    row.specialization = data.specialization
    row.research_field = data.research_field
    row.approval_status = "approved"
    row.approved_by_id = actor.id
    row.approved_at = _now()
    db.commit()
    return serialize_user_access(db, target)


def public_repository(db: Session, publication_type: str = "research") -> list[dict]:
    rows = db.scalars(
        select(ResearchSubmission)
        .where(
            ResearchSubmission.status == "published",
            ResearchSubmission.publication_type == publication_type,
        )
        .order_by(ResearchSubmission.published_at.desc())
        .limit(500)
    ).all()
    return [serialize_submission(db, row, None) for row in rows]


def profile_publications(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(ResearchSubmission)
        .where(
            ResearchSubmission.researcher_id == user.id,
            ResearchSubmission.status == "published",
        )
        .order_by(ResearchSubmission.published_at.desc())
    ).all()
    return [serialize_submission(db, row, user) for row in rows]


def serialize_recommendation(row: RecommendationRecord) -> dict:
    return {
        "id": row.id,
        "submission_id": row.submission_id,
        "text": row.text,
        "research_field": row.research_field,
        "directorate_id": row.directorate_id,
        "status": row.status,
        "created_at": row.created_at,
    }


def serialize_problem(row: ProblemRecord) -> dict:
    return {
        "id": row.id,
        "submission_id": row.submission_id,
        "text": row.text,
        "research_field": row.research_field,
        "school_id": row.school_id,
        "directorate_id": row.directorate_id,
        "created_at": row.created_at,
    }


def recommendations(db: Session, user: User) -> list[dict]:
    ensure_role(user, DECISION_MAKER, SCIENTIFIC_COMMITTEE)
    rows = db.scalars(select(RecommendationRecord).order_by(RecommendationRecord.created_at.desc())).all()
    return [serialize_recommendation(row) for row in rows]


def update_recommendation_status(db: Session, user: User, recommendation_id: int, status: str) -> dict:
    ensure_role(user, DECISION_MAKER)
    row = db.get(RecommendationRecord, recommendation_id)
    if not row:
        raise ApplicationError(404, "Recommendation not found")
    row.status = status
    db.commit()
    return serialize_recommendation(row)


def problems(db: Session, user: User) -> list[dict]:
    ensure_role(user, RESEARCHER, DECISION_MAKER, DIRECTORATE_MANAGER, SCIENTIFIC_COMMITTEE)
    statement = select(ProblemRecord)
    if role_of(user) == DIRECTORATE_MANAGER:
        aff = affiliation(db, user.id)
        statement = statement.where(ProblemRecord.directorate_id == aff.directorate_id) if aff and aff.approval_status == 'approved' else statement.where(False)
    return [serialize_problem(row) for row in db.scalars(statement.order_by(ProblemRecord.created_at.desc())).all()]

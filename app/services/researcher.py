import json
from sqlalchemy import select
from app.domain.errors import ApplicationError
from app.domain.roles import RESEARCHER, ORGANIZING_COMMITTEE, SYSTEM_ADMIN
from app.models.user import User
from app.models.researcher import ResearchDraft, TrainingProgress, ResearcherCertificate
from app.repositories import researcher as repository
from app.services import workflow
from app.infrastructure.minio_storage import presigned_file_url, upload_certificate


def draft_payload(row):
    return dict(id=row.id, content=row.content, revision=row.revision, updated_at=row.updated_at, submission_id=row.submission_id)


def overview(db, user):
    workflow.ensure_role(user, RESEARCHER)
    return {
        'drafts': [draft_payload(row) for row in repository.drafts(db, user.id)],
        'training': [dict(id=r.id, title=r.title, completed=r.completed, total=r.total, updated_at=r.updated_at) for r in repository.training(db, user.id)],
        'certificates': [dict(id=r.id, title=r.title, issuer=r.issuer, issued_at=r.issued_at, url=presigned_file_url(r.file_object_name)) for r in repository.certificates(db, user.id)],
    }


def create_draft(db, user, content):
    workflow.ensure_role(user, RESEARCHER)
    row = ResearchDraft(researcher_id=user.id, content=content.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return draft_payload(row)


def get_draft(db, user, draft_id):
    workflow.ensure_role(user, RESEARCHER)
    row = repository.owned_draft(db, user.id, draft_id)
    if row is None:
        raise ApplicationError(404, 'Draft not found')
    return row


def save_draft(db, user, draft_id, data):
    row = get_draft(db, user, draft_id)
    if row.submission_id or row.revision != data.revision:
        raise ApplicationError(409, 'Draft changed or was submitted. Reload before editing.')
    row.content = data.content.model_dump()
    row.revision += 1
    db.commit(); db.refresh(row)
    return draft_payload(row)


def submit_draft(db, user, draft_id, revision, filename, content_type, data):
    row = get_draft(db, user, draft_id)
    if row.submission_id:
        return {'id': row.submission_id, 'already_submitted': True}
    if row.revision != revision:
        raise ApplicationError(409, 'Draft changed. Reload before submitting.')
    content = row.content
    if any(len(content.get(key, '').strip()) < 2 for key in ('title', 'research_field', 'problem', 'abstract')):
        raise ApplicationError(422, 'Title, research field, problem and abstract are required before submission')
    if not data:
        raise ApplicationError(422, 'Research file is empty')
    form = {**content, 'keywords': [s.strip() for s in content.get('keywords', '').split(',') if s.strip()]}
    # create_submission links the locked draft before its existing transaction commits.
    return workflow.create_submission(db, user, title=content['title'], research_field=content['research_field'], problem=content['problem'], recommendations=content.get('recommendations', ''), abstract=content.get('abstract', ''), form_json=json.dumps(form), file_name=filename, content_type=content_type, file_bytes=data, draft=row)


def staff_target(db, actor, user_id):
    workflow.ensure_role(actor, ORGANIZING_COMMITTEE, SYSTEM_ADMIN)
    target = db.get(User, user_id)
    if not target or workflow.role_of(target) != RESEARCHER:
        raise ApplicationError(404, 'Researcher not found')
    return target


def record_progress(db, actor, user_id, data):
    staff_target(db, actor, user_id)
    row = db.scalar(select(TrainingProgress).where(TrainingProgress.user_id == user_id, TrainingProgress.course_key == data.course_key))
    if row is None:
        row = TrainingProgress(user_id=user_id, **data.model_dump()); db.add(row)
    else:
        for key, value in data.model_dump().items(): setattr(row, key, value)
    db.commit(); db.refresh(row)
    return {'id': row.id}


def issue_certificate(db, actor, user_id, title, issuer, data):
    staff_target(db, actor, user_id)
    if len(data) > 5 * 1024 * 1024:
        raise ApplicationError(413, 'Certificate must be 5 MB or smaller')
    if not data.startswith(b'%PDF-'):
        raise ApplicationError(422, 'A PDF certificate is required')
    row = ResearcherCertificate(user_id=user_id, title=title, issuer=issuer, file_object_name=upload_certificate(user_id, data))
    db.add(row); db.commit(); db.refresh(row)
    return {'id': row.id}

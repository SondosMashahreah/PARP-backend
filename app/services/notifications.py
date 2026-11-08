"""Server-owned notifications; clients can only read their own inbox.

Changes are recorded in the SAME database transaction as their originating action.
The application imports this module at boot to register the ORM listener.
"""
from datetime import datetime, timezone

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.domain.roles import normalize_role
from app.models.notification import Notification
from app.models.news import NewsArticle
from app.models.platform import (
    CommitteeAccount, Conference, ConferenceParticipation, PlatformNotice,
    PublicationPayment,
)
from app.models.researcher import ResearcherCertificate, TrainingProgress
from app.models.user import User
from app.models.workflow import (
    ResearchSubmission, ReviewAssignment, UserAffiliation, WorkflowEvent,
)


def recipient_key(user):
    return f'committee:{user.id}' if isinstance(user, CommitteeAccount) else f'user:{user.id}'


def send(db, recipients, kind, ar, en, *, body_ar='', body_en='', href='/workspace'):
    """Enqueue notifications; the caller's transaction owns the commit/rollback."""
    # Only internal SPA paths can be opened by notification actions.
    if not href.startswith('/') or href.startswith('//') or '\\' in href:
        href = '/'
    for key in set(recipients):
        if not key:
            continue
        db.add(Notification(
            recipient_key=key, kind=kind,
            title_ar=str(ar)[:300], title_en=str(en)[:300],
            body_ar=str(body_ar or '')[:1200], body_en=str(body_en or '')[:1200],
            href=href[:500],
        ))


def _user(db, user_id):
    return {f'user:{user_id}'} if user_id else set()


def _roles(db, *roles):
    wanted = set(roles)
    return {
        f'user:{user_id}'
        for user_id, role in db.execute(select(User.id, User.role).where(User.is_active.is_(True)))
        if normalize_role(role) in wanted
    }


def _everyone(db):
    ids = _roles(db,
        'researcher', 'reviewer', 'school_manager', 'directorate_manager',
        'scientific_committee', 'organizing_committee', 'decision_maker', 'system_admin',
    )
    ids.update(f'committee:{uid}' for uid in db.scalars(
        select(CommitteeAccount.id).where(CommitteeAccount.is_active.is_(True))
    ))
    return ids


def _institution_staff(db, submission):
    targets = _roles(db, 'system_admin')
    if not submission:
        return targets
    for user, affiliation in db.execute(
        select(User, UserAffiliation).join(UserAffiliation, User.id == UserAffiliation.user_id)
        .where(User.is_active.is_(True), UserAffiliation.approval_status == 'approved')
    ):
        role = normalize_role(user.role)
        if role == 'school_manager' and submission.school_id and affiliation.school_id == submission.school_id:
            targets.add(f'user:{user.id}')
        if role == 'directorate_manager' and submission.directorate_id and affiliation.directorate_id == submission.directorate_id:
            targets.add(f'user:{user.id}')
    return targets


def _workflow(db, row):
    submission = db.get(ResearchSubmission, row.submission_id)
    if not submission:
        return
    title = submission.title
    href = '/workspace'
    if row.event_type in ('submitted', 'resubmitted'):
        changed = row.event_type == 'resubmitted'
        send(db, _user(db, submission.researcher_id), 'research',
             'تم استلام النسخة المعدّلة من بحثك' if changed else 'تم استلام بحثك بنجاح',
             'Your revised research has been received' if changed else 'Your research was submitted',
             body_ar=title, body_en=submission.title_en or title, href=href)
        send(db, _institution_staff(db, submission), 'research',
             'بحث معدّل بانتظار المتابعة' if changed else 'بحث جديد بانتظار المتابعة',
             'Revised research needs attention' if changed else 'New research submission',
             body_ar=title, body_en=submission.title_en or title, href=href)
        # ReviewAssignment transitions back to 'invited' below; do not
        # notify the same reviewer twice for a single resubmission.
    elif row.event_type == 'review_submitted':
        send(db, _roles(db, 'system_admin'), 'review',
             'اكتمل تحكيم أحد البحوث', 'A research review was submitted',
             body_ar=title, body_en=submission.title_en or title, href=href)
    elif row.event_type == 'scientific_decision':
        status = {
            'approved': ('تمت الموافقة على بحثك', 'Your research was approved'),
            'rejected': ('صدر قرار بشأن بحثك: غير مقبول', 'Your research was not approved'),
            'revision_requested': ('مطلوب تعديلات على بحثك', 'Revisions are requested for your research'),
            'practice_suggested': ('اقتراح نشر بحثك كممارسة', 'Your research was suggested as a practice'),
        }.get(row.to_status, ('تحديث حالة بحثك', 'Research status updated'))
        send(db, _user(db, submission.researcher_id), 'decision', *status,
             body_ar=title, body_en=submission.title_en or title, href=href)
    elif row.event_type in ('published', 'published_as_practice'):
        send(db, _everyone(db), 'publication',
             'تم نشر بحث جديد في PARP' if row.event_type == 'published' else 'تم نشر ممارسة جديدة في PARP',
             'New research published on PARP' if row.event_type == 'published' else 'New practice published on PARP',
             body_ar=title, body_en=submission.title_en or title, href='/repository')


def _affiliation(db, row, is_new):
    state = inspect(row)
    change = state.attrs.approval_status.history.has_changes()
    if row.approval_status == 'approved' and (is_new or change):
        send(db, _user(db, row.user_id), 'affiliation',
             'تم اعتماد انتسابك المؤسسي', 'Your institution affiliation was approved',
             href='/profile')
    elif row.approval_status == 'requested' and (
        is_new or change or state.attrs.requested_at.history.has_changes()
    ):
        staff = _roles(db, 'system_admin')
        for user, affiliation in db.execute(
            select(User, UserAffiliation).join(UserAffiliation, User.id == UserAffiliation.user_id)
            .where(User.is_active.is_(True), UserAffiliation.approval_status == 'approved')
        ):
            role = normalize_role(user.role)
            if role == 'school_manager' and row.school_id and affiliation.school_id == row.school_id:
                staff.add(f'user:{user.id}')
            if role == 'directorate_manager' and row.directorate_id and affiliation.directorate_id == row.directorate_id:
                staff.add(f'user:{user.id}')
        send(db, staff, 'affiliation',
             'طلب انتساب جديد يحتاج مراجعة', 'New affiliation request needs review',
             href='/workspace')


def _assignment(db, row, is_new):
    if row.status != 'invited':
        return
    if not is_new and not inspect(row).attrs.status.history.has_changes():
        return
    submission = db.get(ResearchSubmission, row.submission_id)
    send(db, _user(db, row.reviewer_id), 'review',
         'دُعيت لتحكيم بحث', 'You have a new review invitation',
         body_ar=submission.title if submission else '',
         body_en=(submission.title_en or submission.title) if submission else '', href='/workspace')


def _participation(db, row):
    audience = _roles(db, 'scientific_committee')
    audience.update(f'committee:{uid}' for uid in db.scalars(
        select(CommitteeAccount.id).where(
            CommitteeAccount.is_active.is_(True), CommitteeAccount.conference_id == row.conference_id
        )
    ))
    send(db, audience, 'conference',
         'مشاركة مؤتمر جديدة بانتظار المراجعة', 'New conference participation',
         body_ar=row.title, body_en=row.title, href='/conference')


def _notice(db, row):
    send(db, _user(db, row.user_id), 'conference',
         'إشعار جديد من المؤتمر', 'New conference notification',
         body_ar=row.text, body_en=row.text, href='/conference')


def _payment(db, row, is_new):
    research = db.get(ResearchSubmission, row.submission_id)
    if not research:
        return
    if is_new:
        send(db, _roles(db, 'system_admin'), 'payment',
             'طلب دفع نشر جديد', 'New publication payment request',
             body_ar=research.title, body_en=research.title_en or research.title,
             href='/dashboard#payments')
    elif inspect(row).attrs.history.history.has_changes():
        send(db, _user(db, research.researcher_id), 'payment',
             'تم تحديث حالة رسوم نشر بحثك', 'Your publication payment was updated',
             body_ar=research.title, body_en=research.title_en or research.title,
             href='/workspace')


def _news(db, row, is_new):
    changed = is_new or inspect(row).attrs.published.history.has_changes()
    if row.published and changed:
        send(db, _everyone(db), 'news',
             'خبر جديد على المنصة', 'New platform news',
             body_ar=row.title, body_en=row.title_en or row.title,
             href=f'/news?article={row.id}')


@event.listens_for(Session, 'before_flush')
def _capture_notification_events(db, flush_context, instances):
    """Observe committed domain changes without changing existing service flows."""
    for row in list(db.new):
        if isinstance(row, WorkflowEvent):
            _workflow(db, row)
        elif isinstance(row, UserAffiliation):
            _affiliation(db, row, True)
        elif isinstance(row, ReviewAssignment):
            _assignment(db, row, True)
        elif isinstance(row, PlatformNotice):
            _notice(db, row)
        elif isinstance(row, ConferenceParticipation):
            _participation(db, row)
        elif isinstance(row, Conference):
            send(db, _roles(db, 'researcher', 'scientific_committee', 'organizing_committee'), 'conference',
                 'مؤتمر جديد على المنصة', 'New conference announced',
                 body_ar=row.title, body_en=row.title, href='/conference')
        elif isinstance(row, PublicationPayment):
            _payment(db, row, True)
        elif isinstance(row, NewsArticle):
            _news(db, row, True)
        elif isinstance(row, ResearcherCertificate):
            send(db, _user(db, row.user_id), 'certificate',
                 'تم إصدار شهادة جديدة لك', 'Your certificate is ready',
                 body_ar=row.title, body_en=row.title, href='/workspace')
        elif isinstance(row, TrainingProgress) and row.total and row.completed >= row.total:
            send(db, _user(db, row.user_id), 'training',
                 'أكملت تدريبًا على المنصة', 'You completed a training course',
                 body_ar=row.title, body_en=row.title, href='/workspace')
    for row in list(db.dirty):
        if isinstance(row, UserAffiliation):
            _affiliation(db, row, False)
        elif isinstance(row, ReviewAssignment):
            _assignment(db, row, False)
        elif isinstance(row, PublicationPayment):
            _payment(db, row, False)
        elif isinstance(row, NewsArticle):
            _news(db, row, False)
        elif isinstance(row, TrainingProgress) and row.total and row.completed >= row.total and (
            inspect(row).attrs.completed.history.has_changes() or inspect(row).attrs.total.history.has_changes()
        ):
            send(db, _user(db, row.user_id), 'training',
                 'أكملت تدريبًا على المنصة', 'You completed a training course',
                 body_ar=row.title, body_en=row.title, href='/workspace')

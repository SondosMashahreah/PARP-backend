"""Platform use cases: payments, conferences and scoped participation reporting."""

from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.domain.errors import ApplicationError
from app.models.platform import (
    PublicationPayment,
    Conference,
    ConferenceParticipation,
    PlatformNotice,
    CommitteeCredential,
)
from app.models.workflow import ResearchSubmission, UserAffiliation
from app.models.education import School, Directorate
from app.models.user import User
from app.services.workflow import (
    ensure_role,
    affiliation,
    role_of,
    serialize_submission,
)
from app.infrastructure.minio_storage import _upload, presigned_file_url
from app.core.security import hash_password, verify_password
from app.services.auth import token_response


def locked_research(db, submission_id):
    row = db.scalar(
        select(ResearchSubmission)
        .where(ResearchSubmission.id == submission_id)
        .with_for_update()
    )
    if not row:
        raise ApplicationError(404, "Research not found")
    return row


def payment_payload(db, row):
    research = db.get(ResearchSubmission, row.submission_id)
    author = db.get(User, research.researcher_id)
    school = db.get(School, research.school_id) if research.school_id else None
    directorate = (
        db.get(Directorate, research.directorate_id)
        if research.directorate_id
        else None
    )
    return dict(
        submission_id=row.submission_id,
        title=research.title,
        researcher=author.full_name,
        school=school.name_ar if school else research.school_id,
        directorate=directorate.name_ar if directorate else research.directorate_id,
        required_agorot=row.required_agorot,
        paid_agorot=row.paid_agorot,
        confirmed=row.confirmed,
        receipt=row.receipt,
        history=row.history,
    )


def request_payment(db, user, submission_id):
    ensure_role(user, "researcher")
    research = locked_research(db, submission_id)
    if research.researcher_id != user.id:
        raise ApplicationError(404, "Research not found")
    if research.status != "approved" or research.publication_type != "research":
        raise ApplicationError(
            409, "Only approved research requires publication payment"
        )
    row = db.get(PublicationPayment, submission_id)
    if not row:
        row = PublicationPayment(submission_id=submission_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return payment_payload(db, row)


def payments(db, user):
    ensure_role(user, "system_admin", "researcher")
    query = select(PublicationPayment).join(ResearchSubmission)
    if role_of(user) == "researcher":
        query = query.where(ResearchSubmission.researcher_id == user.id)
    return [payment_payload(db, r) for r in db.scalars(query).all()]


def update_payment(db, user, submission_id, data):
    ensure_role(user, "system_admin")
    research = locked_research(db, submission_id)
    if research.status != "approved" or research.publication_type != "research":
        raise ApplicationError(409, "Only approved unpublished research can be paid")
    row = db.get(PublicationPayment, submission_id)
    if not row:
        raise ApplicationError(404, "Publication payment request not found")
    previous = dict(
        required_agorot=row.required_agorot,
        paid_agorot=row.paid_agorot,
        confirmed=row.confirmed,
        receipt=row.receipt,
    )
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.confirmed_by = user.id if data.confirmed else None
    row.history = [
        *row.history,
        dict(
            actor_id=user.id,
            at=datetime.now(timezone.utc).isoformat(),
            before=previous,
            after=data.model_dump(),
        ),
    ]
    db.commit()
    return payment_payload(db, row)


def conference_payload(row):
    return dict(
        id=row.id,
        title=row.title,
        category=row.category,
        venue=row.venue,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        deadline=row.deadline,
    )


def conferences(db):
    return [
        conference_payload(r)
        for r in db.scalars(
            select(Conference).order_by(Conference.starts_at.desc())
        ).all()
    ]


def create_conference(db, user, data):
    ensure_role(user, "scientific_committee")
    row = Conference(**data.model_dump(), created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return conference_payload(row)


def scope(db, user, query, model):
    role = role_of(user)
    if role == "researcher":
        return query.where(model.researcher_id == user.id)
    if role in ("school_manager", "directorate_manager"):
        aff = affiliation(db, user.id)
        if not aff or aff.approval_status != "approved":
            return query.where(False)
        if role == "school_manager":
            return (
                query.where(model.school_id == aff.school_id)
                if aff.school_id
                else query.where(False)
            )
        return (
            query.where(model.directorate_id == aff.directorate_id)
            if aff.directorate_id
            else query.where(False)
        )
    if role == "organizing_committee" and model is ConferenceParticipation:
        credential = db.get(CommitteeCredential, user.id)
        return (
            query.where(model.conference_id == credential.conference_id)
            if credential and not credential.must_change_password
            else query.where(False)
        )
    if role in ("decision_maker", "scientific_committee", "system_admin"):
        return query
    return query.where(False)


def participation_payload(db, row, user):
    author = db.get(User, row.researcher_id)
    return dict(
        id=row.id,
        conference_id=row.conference_id,
        researcher_id=row.researcher_id,
        researcher=author.full_name,
        title=row.title,
        abstract=row.abstract,
        school_id=row.school_id,
        directorate_id=row.directorate_id,
        status=row.status,
        notes=row.notes,
        url=presigned_file_url(row.object_name),
    )


def participations(db, user):
    query = scope(db, user, select(ConferenceParticipation), ConferenceParticipation)
    return [
        participation_payload(db, r, user)
        for r in db.scalars(
            query.order_by(ConferenceParticipation.created_at.desc())
        ).all()
    ]


def participate(db, user, conference_id, title, abstract, filename, data):
    ensure_role(user, "researcher")
    conf = db.get(Conference, conference_id)
    if not conf:
        raise ApplicationError(404, "Conference not found")
    deadline = (
        conf.deadline
        if conf.deadline.tzinfo
        else conf.deadline.replace(tzinfo=timezone.utc)
    )
    if datetime.now(timezone.utc) > deadline:
        raise ApplicationError(409, "Conference submission deadline has passed")
    aff = affiliation(db, user.id)
    if (
        not aff
        or aff.approval_status != "approved"
        or not aff.school_id
        or not aff.directorate_id
    ):
        raise ApplicationError(409, "An approved school affiliation is required")
    if not title.strip() or not abstract.strip():
        raise ApplicationError(422, "Title and abstract are required")
    if not data or len(data) > 25 * 1024 * 1024:
        raise ApplicationError(422, "PowerPoint must be nonempty and at most 25 MB")
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext == "pptx":
        try:
            with ZipFile(BytesIO(data)) as archive:
                if "ppt/presentation.xml" not in archive.namelist() or any(
                    "vbaProject" in n for n in archive.namelist()
                ):
                    raise ApplicationError(
                        422, "A non-macro PowerPoint presentation is required"
                    )
        except BadZipFile:
            raise ApplicationError(422, "Invalid PPTX file")
    elif ext == "ppt":
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ApplicationError(422, "Invalid PPT file")
    else:
        raise ApplicationError(422, "Use PPT or PPTX")
    row = db.scalar(
        select(ConferenceParticipation)
        .where(
            ConferenceParticipation.conference_id == conference_id,
            ConferenceParticipation.researcher_id == user.id,
        )
        .with_for_update()
    )
    if row and row.status not in ("revision_requested", "rejected"):
        raise ApplicationError(409, "This participation has already been submitted")
    object_name = _upload(
        f"conferences/{conference_id}/{user.id}/{uuid4().hex}.{ext}",
        data,
        (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if ext == "pptx"
            else "application/vnd.ms-powerpoint"
        ),
    )
    if row:
        row.title = title.strip()
        row.abstract = abstract.strip()
        row.object_name = object_name
        row.status = "submitted"
    else:
        row = ConferenceParticipation(
            conference_id=conference_id,
            researcher_id=user.id,
            school_id=aff.school_id,
            directorate_id=aff.directorate_id,
            title=title.strip(),
            abstract=abstract.strip(),
            object_name=object_name,
        )
        db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApplicationError(409, "Participation already exists")
    db.refresh(row)
    return participation_payload(db, row, user)


def decide_participation(db, user, participation_id, data):
    ensure_role(user, "scientific_committee")
    row = db.get(ConferenceParticipation, participation_id)
    if not row:
        raise ApplicationError(404, "Participation not found")
    row.status = data.status
    row.notes = data.notes
    db.add(
        PlatformNotice(
            user_id=row.researcher_id,
            conference_id=row.conference_id,
            text=f"{row.title}: {data.status}\n{data.notes}",
        )
    )
    db.commit()
    return participation_payload(db, row, user)


def notify_conference(db, user, conference_id, text):
    ensure_role(user, "scientific_committee")
    if not db.get(Conference, conference_id):
        raise ApplicationError(404, "Conference not found")
    recipients = db.scalars(
        select(ConferenceParticipation.researcher_id)
        .where(ConferenceParticipation.conference_id == conference_id)
        .distinct()
    ).all()
    for recipient in recipients:
        db.add(
            PlatformNotice(user_id=recipient, conference_id=conference_id, text=text)
        )
    db.commit()
    return {"recipients": len(recipients)}


def notices(db, user):
    return [
        dict(id=r.id, text=r.text, created_at=r.created_at)
        for r in db.scalars(
            select(PlatformNotice)
            .where(PlatformNotice.user_id == user.id)
            .order_by(PlatformNotice.created_at.desc())
        ).all()
    ]


def create_user(db, actor, data):
    ensure_role(actor, "system_admin")
    if db.scalar(
        select(User.id).where(func.lower(User.email) == str(data.email).lower())
    ):
        raise ApplicationError(409, "Email already exists")
    if data.role == "organizing_committee" and not db.get(
        Conference, data.conference_id
    ):
        raise ApplicationError(404, "Conference not found")
    if data.username and db.scalar(
        select(CommitteeCredential.user_id).where(
            CommitteeCredential.username == data.username.lower()
        )
    ):
        raise ApplicationError(409, "Username already exists")
    row = User(
        full_name=data.full_name,
        email=str(data.email).lower(),
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
        is_verified=True,
    )
    db.add(row)
    db.flush()
    if data.role == "organizing_committee":
        db.add(
            CommitteeCredential(
                user_id=row.id,
                username=data.username.lower(),
                conference_id=data.conference_id,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApplicationError(409, "Account already exists")
    return dict(id=row.id, full_name=row.full_name, role=row.role)


def committee_login(db, data):
    credential = db.scalar(
        select(CommitteeCredential).where(
            CommitteeCredential.username == data.username.lower()
        )
    )
    user = db.get(User, credential.user_id) if credential else None
    if (
        not user
        or not user.is_active
        or role_of(user) != "organizing_committee"
        or not verify_password(data.password, user.password_hash)
    ):
        raise ApplicationError(401, "Invalid credentials")
    return {
        **token_response(user),
        "must_change_password": credential.must_change_password,
    }


def change_password(db, user, data):
    ensure_role(user, "organizing_committee")
    credential = db.get(CommitteeCredential, user.id)
    if not credential:
        raise ApplicationError(403, "No committee account")
    user.password_hash = hash_password(data.password)
    credential.must_change_password = False
    db.commit()
    return {"ok": True}


def statistics(db, user):
    ensure_role(
        user, "school_manager", "directorate_manager", "decision_maker", "system_admin"
    )
    research = db.scalars(
        scope(db, user, select(ResearchSubmission), ResearchSubmission)
    ).all()
    participation = db.scalars(
        scope(db, user, select(ConferenceParticipation), ConferenceParticipation)
    ).all()
    aff = affiliation(db, user.id)
    school_query = select(School)
    directorate_query = select(Directorate)
    if role_of(user) in ("school_manager", "directorate_manager"):
        if not aff or aff.approval_status != "approved":
            school_query = school_query.where(False)
            directorate_query = directorate_query.where(False)
        else:
            school_query = (
                school_query.where(School.id == aff.school_id)
                if role_of(user) == "school_manager"
                else school_query.where(School.directorate_id == aff.directorate_id)
            )
            directorate_query = directorate_query.where(
                Directorate.id == aff.directorate_id
            )
    schools = db.scalars(school_query).all()
    directors = db.scalars(directorate_query).all()

    def counts(rs, ps):
        return dict(
            research=len([r for r in rs if r.publication_type == "research"]),
            practices=len([r for r in rs if r.publication_type == "practice"]),
            published=sum(r.status == "published" for r in rs),
            approved=sum(r.status == "approved" for r in rs),
            participations=len(ps),
            researchers=len({r.researcher_id for r in [*rs, *ps]}),
        )

    school_rows = [
        dict(
            id=s.id,
            name_ar=s.name_ar,
            name_en=s.name_en,
            directorate_id=s.directorate_id,
            latitude=s.latitude,
            longitude=s.longitude,
            **counts(
                [r for r in research if r.school_id == s.id],
                [p for p in participation if p.school_id == s.id],
            ),
        )
        for s in schools
    ]
    for row in school_rows:
        row['schools'] = int(row['research'] + row['practices'] + row['participations'] > 0)
    return dict(
        totals=counts(research, participation),
        directorates=[
            dict(
                id=d.id,
                name_ar=d.name_ar,
                name_en=d.name_en,
                latitude=d.latitude,
                longitude=d.longitude,
                geometry=d.geometry,
                schools=sum(
                    s["directorate_id"] == d.id
                    and (s["research"] + s["practices"] + s["participations"] > 0)
                    for s in school_rows
                ),
                **counts(
                    [r for r in research if r.directorate_id == d.id],
                    [p for p in participation if p.directorate_id == d.id],
                ),
            )
            for d in directors
        ],
        schools=school_rows,
        research=[serialize_submission(db, r, user) for r in research],
        participations=[participation_payload(db, p, user) for p in participation],
    )


def configure_committee(db, actor, user_id, data):
    """Provision an existing committee account without deleting its history."""
    ensure_role(actor, "system_admin")
    target = db.get(User, user_id)
    if not target or role_of(target) != "organizing_committee":
        raise ApplicationError(404, "Organizing committee account not found")
    if not db.get(Conference, data.conference_id):
        raise ApplicationError(404, "Conference not found")
    existing = db.scalar(
        select(CommitteeCredential).where(
            CommitteeCredential.username == data.username.lower()
        )
    )
    if existing and existing.user_id != user_id:
        raise ApplicationError(409, "Username already in use")
    row = db.get(CommitteeCredential, user_id)
    if not row:
        row = CommitteeCredential(user_id=user_id)
        db.add(row)
    row.username = data.username.lower()
    row.conference_id = data.conference_id
    row.must_change_password = True
    target.password_hash = hash_password(data.password)
    target.is_verified = True
    db.commit()
    return {"id": user_id}

"""Verified platform researchers for ARDS co-author selection.

Only approved institutional affiliations are returned; emails, passwords,
phone numbers, and other account details are deliberately excluded.
"""
from sqlalchemy import select

from app.domain.errors import ApplicationError
from app.domain.roles import RESEARCHER, normalize_role
from app.models.education import Directorate, School
from app.models.user import User
from app.models.workflow import UserAffiliation


def _profile(db, account: User | None) -> dict | None:
    if not account or not account.is_active or normalize_role(account.role) != RESEARCHER:
        return None
    aff = db.get(UserAffiliation, account.id)
    if not aff or aff.approval_status != 'approved' or not aff.school_id or not aff.directorate_id:
        return None
    school = db.get(School, aff.school_id)
    directorate = db.get(Directorate, aff.directorate_id)
    if not school or not directorate:
        return None
    # Use the approved association; the imported school directory may not yet
    # contain a school→directorate relationship for every school.
    if school.directorate_id and school.directorate_id != directorate.id:
        return None
    return {
        'user_id': account.id,
        'full_name': account.full_name,
        'school_id': school.id,
        'school': school.name_ar,
        'school_en': school.name_en or '',
        'directorate_id': directorate.id,
        'directorate': directorate.name_ar,
        'directorate_en': directorate.name_en or '',
    }


def own_profile(db, actor) -> dict:
    if normalize_role(actor.role) != RESEARCHER:
        raise ApplicationError(403, 'Researcher access is required')
    value = _profile(db, db.get(User, actor.id))
    return {'researcher': value, 'affiliation_status': 'approved' if value else 'unavailable'}


def search_profiles(db, actor, query: str, limit: int = 15) -> dict:
    if normalize_role(actor.role) != RESEARCHER:
        raise ApplicationError(403, 'Researcher access is required')
    needle = query.strip()
    if len(needle) < 2:
        raise ApplicationError(422, 'Type at least two characters')
    # Use bound parameters; escape SQL LIKE wildcards from the search term.
    escaped = needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    rows = db.scalars(
        select(User)
        .join(UserAffiliation, UserAffiliation.user_id == User.id)
        .where(
            User.is_active.is_(True),
            User.role.in_(['researcher', 'user']),
            UserAffiliation.approval_status == 'approved',
            UserAffiliation.school_id.is_not(None),
            UserAffiliation.directorate_id.is_not(None),
            User.full_name.ilike(f'%{escaped}%', escape='\\'),
        )
        .order_by(User.full_name, User.id)
        .limit(min(max(limit, 1), 20))
    ).all()
    return {'items': [value for account in rows if (value := _profile(db, account)) is not None]}


def canonicalize_linked_researchers(db, actor, content: dict) -> dict:
    """Replace client-supplied affiliations with authoritative approved records.

    Old ARDS-1.0 drafts without researchers_mode remain readable and valid.
    New editor records use researchers_mode='linked' and are strictly verified.
    """
    if content.get('kind', 'research') != 'research' or content.get('researchers_mode') != 'linked':
        return content
    rows = content.get('researchers')
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        raise ApplicationError(422, 'Select at least one registered researcher')
    resolved = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ApplicationError(422, 'Invalid researcher record')
        researcher_id = row.get('user_id')
        if type(researcher_id) is not int or researcher_id <= 0 or researcher_id in seen:
            raise ApplicationError(422, 'Researchers must be distinct, selected platform accounts')
        seen.add(researcher_id)
        author = _profile(db, db.get(User, researcher_id))
        if not author:
            raise ApplicationError(422, 'A selected researcher no longer has an approved school and directorate')
        resolved.append(author)
    if actor.id not in seen:
        raise ApplicationError(422, 'The submitting researcher must be included in the author list')
    return {**content, 'researchers': resolved}

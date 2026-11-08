"""Authenticated personal inbox API; never accepts a recipient ID from clients."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.notification import Notification
from app.routers.dependencies import get_current_user
from app.services.notifications import recipient_key

router = APIRouter(prefix='/api/notifications', tags=['Notifications'])


def _as_utc(value):
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _serialize(row):
    return {
        'id': row.id,
        'kind': row.kind,
        'title_ar': row.title_ar, 'title_en': row.title_en,
        'body_ar': row.body_ar, 'body_en': row.body_en,
        'href': row.href,
        'created_at': _as_utc(row.created_at),
        'read_at': _as_utc(row.read_at),
    }


@router.get('')
def inbox(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user), db: Session = Depends(get_db),
):
    key = recipient_key(user)
    statement = select(Notification).where(Notification.recipient_key == key)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    unread_count = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.recipient_key == key, Notification.read_at.is_(None)
    )) or 0
    rows = db.scalars(statement.order_by(Notification.created_at.desc(), Notification.id.desc())
                      .limit(limit).offset(offset)).all()
    return {'items': [_serialize(row) for row in rows],
            'unread_count': int(unread_count), 'total': int(total)}


@router.post('/read-all')
def read_all(user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(update(Notification).where(
        Notification.recipient_key == recipient_key(user), Notification.read_at.is_(None)
    ).values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return {'updated': result.rowcount or 0}


@router.post('/{notification_id}/read')
def mark_read(notification_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(update(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_key == recipient_key(user),
        Notification.read_at.is_(None),
    ).values(read_at=datetime.now(timezone.utc)))
    if not result.rowcount:
        # An already-read item is allowed; another user's item remains invisible.
        found = db.scalar(select(Notification.id).where(
            Notification.id == notification_id, Notification.recipient_key == recipient_key(user)
        ))
        if not found:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail='Notification not found')
    db.commit()
    return {'ok': True}

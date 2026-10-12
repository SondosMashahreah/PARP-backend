from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.domain.roles import normalize_role, ALL_AUTH_ROLES
from app.models.user import User
from app.repositories.users import by_id


security = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_token(credentials.credentials, "access")
    if not payload or not str(payload.get("sub", "")).isdigit():
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid account")
    if settings.AUTH_REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid account")
    if normalize_role(user.role) not in ALL_AUTH_ROLES:
        raise HTTPException(403, "This role has been retired; contact the administrator")
    if user.role == "user":
        user.role = normalize_role(user.role)
        db.commit()
        db.refresh(user)
    if normalize_role(user.role) == 'organizing_committee':
        from app.models.platform import CommitteeCredential
        credential = db.get(CommitteeCredential, user.id)
        if not credential:
            raise HTTPException(403, 'Administrator must create a conference-linked username')
        allowed = {'/auth/me', '/api/platform/committee/password', '/api/platform/conferences', '/api/platform/notices', '/api/workflow/workspace'}
        if credential.must_change_password and request.url.path not in allowed:
            raise HTTPException(403, 'Change your temporary password first')
    return user

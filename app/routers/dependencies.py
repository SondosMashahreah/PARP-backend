from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.domain.roles import normalize_role, ALL_AUTH_ROLES
from app.models.user import User
from app.models.platform import CommitteeAccount
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
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    subject = str(payload.get("sub", ""))

    if subject.startswith("committee:"):
        raw_id = subject.split(":", 1)[1]
        if not raw_id.isdigit():
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        account = db.get(CommitteeAccount, int(raw_id))
        if not account or not account.is_active:
            raise HTTPException(status_code=401, detail="Invalid account")
        return account

    if not subject.isdigit():
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = by_id(db, int(subject))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid account")
    if settings.AUTH_REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid account")
    if normalize_role(user.role) not in ALL_AUTH_ROLES:
        raise HTTPException(
            403,
            "This role has been retired; contact the administrator",
        )
    if user.role == "user":
        user.role = normalize_role(user.role)
        db.commit()
        db.refresh(user)
    return user

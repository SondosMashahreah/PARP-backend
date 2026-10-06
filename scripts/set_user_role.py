"""Bootstrap or update a PARP user's role and optional institutional affiliation.

Examples:
python -m scripts.set_user_role admin@meo.edu.ps system_admin
python -m scripts.set_user_role reviewer@meo.edu.ps reviewer --specialization mathematics
"""
import argparse

from app.core.database import SessionLocal
from app.domain.roles import validate_role
# Register education tables before UserAffiliation so SQLAlchemy can resolve its foreign keys.
from app.models.education import Directorate, Governorate, School  # noqa: F401
from app.models.user import User
from app.models.workflow import UserAffiliation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("role")
    parser.add_argument("--governorate-id")
    parser.add_argument("--directorate-id")
    parser.add_argument("--school-id")
    parser.add_argument("--specialization")
    parser.add_argument("--research-field")
    args = parser.parse_args()

    role = validate_role(args.role)
    with SessionLocal.begin() as db:
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if not user:
            raise SystemExit("User not found; register the account first.")
        user.role = role

        affiliation_values = (
            args.governorate_id,
            args.directorate_id,
            args.school_id,
            args.specialization,
            args.research_field,
        )
        # Roles such as system_admin do not need an empty affiliation row. Create one
        # only when affiliation/specialization data is actually supplied.
        if any(value not in (None, "") for value in affiliation_values):
            row = db.get(UserAffiliation, user.id)
            if not row:
                row = UserAffiliation(user_id=user.id)
                db.add(row)
            row.governorate_id = args.governorate_id
            row.directorate_id = args.directorate_id
            row.school_id = args.school_id
            row.specialization = args.specialization
            row.research_field = args.research_field
            row.approval_status = "approved"

    print(f"Updated {args.email} -> {role}")


if __name__ == "__main__":
    main()

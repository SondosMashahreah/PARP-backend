import re
import unicodedata
from sqlalchemy import select, or_
from app.models.education import School, Governorate, Directorate


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").lower()
    value = "".join(c for c in value if not unicodedata.combining(c) and c != "ـ")
    value = value.translate(str.maketrans("أإآٱىة٠١٢٣٤٥٦٧٨٩", "اااايه0123456789"))
    return " ".join(re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE).split())


def school_query(filters):
    statement = select(School).outerjoin(Governorate, School.governorate_id == Governorate.id).outerjoin(Directorate, School.directorate_id == Directorate.id)
    for field in ("region", "governorate_id", "directorate_id", "school_type"):
        value = filters.get(field)
        if value == "unassigned" and field in ("governorate_id", "directorate_id"):
            statement = statement.where(getattr(School, field).is_(None))
        elif value:
            statement = statement.where(getattr(School, field) == value)
    for token in normalize_query(filters.get("q", "")).split():
        # SQLAlchemy binds parameters and escapes LIKE wildcard characters.
        statement = statement.where(or_(School.search_text.contains(token, autoescape=True),
            Governorate.search_text.contains(token, autoescape=True), Directorate.search_text.contains(token, autoescape=True)))
    if filters.get("location") == "located":
        statement = statement.where(School.latitude.is_not(None), School.longitude.is_not(None))
    elif filters.get("location") == "missing":
        statement = statement.where(School.latitude.is_(None))
    return statement


def school_payload(school):
    keys = ("id", "national_code", "name_ar", "name_en", "school_type", "governorate_id", "directorate_id", "region", "latitude", "longitude", "coordinate_source")
    return {key: getattr(school, key) for key in keys}

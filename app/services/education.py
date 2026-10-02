import math
from app.domain.errors import ApplicationError
from app.domain.education import normalize_query, school_payload  # noqa: F401
from app.repositories.education import school_query  # noqa: F401
from app.repositories import education as repository


def school_detail(school_id, db):
    result = repository.school_detail(school_id, db)
    if result is None:
        raise ApplicationError(404, "School not found")
    return result

def school_points(bbox, f, limit, db):
    bbox = parse_bbox(bbox)
    return repository.school_points(bbox, f, limit, db)


def parse_bbox(value):
    try:
        west, south, east, north = [float(v) for v in value.split(",")]
        if not all(math.isfinite(v) for v in (west, south, east, north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError()
        return west, south, east, north
    except (ValueError, TypeError):
        raise ApplicationError(422, "bbox must be west,south,east,north in WGS84 degrees")

def schools(f, offset, limit, db):
    return repository.schools(f, offset, limit, db)

def directorate_boundaries(db):
    return repository.directorate_boundaries(db)

def boundaries(db):
    return repository.boundaries(db)

def catalog(db):
    return repository.catalog(db)

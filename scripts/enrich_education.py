"""Apply verified school coordinates/directorate links by stable record ID, in one transaction."""
import argparse
import json
import math
from app.core.database import SessionLocal
from app.models.education import Directorate, School


def enrich(db, records):
    seen = set()
    for record in records:
        uid = record.get("id")
        if uid in seen:
            raise ValueError(f"Repeated school ID: {uid}")
        seen.add(uid)
        school = db.get(School, uid) if uid else None
        if school is None:
            raise ValueError(f"Unknown school ID: {uid}")
        if "directorate_id" in record:
            directorate = db.get(Directorate, record["directorate_id"])
            if directorate is None:
                raise ValueError(f"Unknown directorate for {uid}")
            school.directorate_id = directorate.id
        if "latitude" in record or "longitude" in record:
            lat, lon = record.get("latitude"), record.get("longitude")
            source = record.get("coordinate_source", "").strip()
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon)):
                raise ValueError(f"A finite latitude/longitude pair is required for {uid}")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not source or len(source) > 500:
                raise ValueError(f"Invalid coordinates or missing source for {uid}")
            school.latitude, school.longitude, school.coordinate_source = lat, lon, source
    db.flush()
    return len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="UTF-8 JSON array of verified records")
    args = parser.parse_args()
    with open(args.file, encoding="utf-8-sig") as handle:
        records = json.load(handle)
    with SessionLocal.begin() as db:
        updated = enrich(db, records)
    print(f"Updated {updated} schools")


if __name__ == "__main__":
    main()

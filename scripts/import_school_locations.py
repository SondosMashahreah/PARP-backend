"""Fill missing school coordinates from the reviewed bundle; preview unless --apply."""
import argparse
import json
import math
from pathlib import Path

from sqlalchemy import inspect, select, update

from app.core.database import SessionLocal, engine
from app.models.education import EducationSource, School

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "education" / "school-locations.json"
IDENTITY_FIELDS = ("national_code", "name_ar", "name_en", "governorate_id", "region")
# Sanity bounds only; the offline preparation checks the actual governorate polygons.
REGION_BOUNDS = {"PS01": (34.8, 31.2, 35.7, 32.7), "PS02": (34.15, 31.15, 34.65, 31.7)}


def load_bundle(path=DEFAULT_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("Unsupported school location bundle")
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("The bundle needs a non-empty records array")
    sources = bundle.get("sources")
    if (not isinstance(sources, list) or not sources
            or any(not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in sources)):
        raise ValueError("Source attribution is required")
    source_ids = {s["id"] for s in sources}
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every location record must be an object")
        uid = record.get("id")
        if not isinstance(uid, str) or not uid.startswith("school-") or uid in seen:
            raise ValueError(f"Invalid or repeated school ID: {uid}")
        seen.add(uid)
        if any(field not in record for field in IDENTITY_FIELDS):
            raise ValueError(f"School identity is incomplete: {uid}")
        if any(not isinstance(record[field], str) for field in IDENTITY_FIELDS if field != "governorate_id"):
            raise ValueError(f"Invalid school identity: {uid}")
        if record["governorate_id"] is not None and not isinstance(record["governorate_id"], str):
            raise ValueError(f"Invalid governorate identity: {uid}")
        lat, lon = record.get("latitude"), record.get("longitude")
        if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon)):
            raise ValueError(f"A finite latitude/longitude pair is required: {uid}")
        bounds = REGION_BOUNDS.get(record["region"])
        if not bounds or not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
            raise ValueError(f"Coordinates are outside the school region: {uid}")
        source = record.get("coordinate_source")
        if not isinstance(source, str) or not source.strip() or len(source) > 500:
            raise ValueError(f"A source of at most 500 characters is required: {uid}")
        if record.get("source_id") not in source_ids or not record.get("source_record_id") or not record.get("match_method"):
            raise ValueError(f"Match provenance is incomplete: {uid}")
    return records


def import_locations(db, bundle, *, apply=False):
    """Caller owns the transaction. Validate all rows before writing anything.

    Existing coordinates and edited identities are preserved. A conditional UPDATE
    also protects against a coordinate/identity edit between the read and write.
    """
    records = validate_bundle(bundle)
    schools = {s.id: s for s in db.scalars(select(School))}
    unknown = [r["id"] for r in records if r["id"] not in schools]
    if unknown:
        raise ValueError(f"{len(unknown)} unknown school IDs. Run scripts.import_education first; first missing ID: {unknown[0]}")
    report = {
        "mode": "apply" if apply else "preview",
        "bundle_records": len(records), "eligible": 0, "added": 0,
        "already_present": 0, "preserved_existing": 0, "identity_changed": 0,
        "changed_during_import": 0, "review": [],
    }
    eligible = []
    for record in records:
        school = schools[record["id"]]
        if any(getattr(school, field) != record[field] for field in IDENTITY_FIELDS):
            report["identity_changed"] += 1
            report["review"].append({"id": school.id, "reason": "identity_changed"})
            continue
        if school.latitude is not None or school.longitude is not None:
            same = (school.latitude == record["latitude"] and school.longitude == record["longitude"]
                    and school.coordinate_source == record["coordinate_source"])
            reason = "already_present" if same else "preserved_existing"
            report[reason] += 1
            if not same:
                report["review"].append({"id": school.id, "reason": reason})
            continue
        eligible.append(record)
    report["eligible"] = len(eligible)
    if apply:
        for record in eligible:
            statement = update(School).where(
                School.id == record["id"], School.latitude.is_(None), School.longitude.is_(None),
                *(getattr(School, field) == record[field] for field in IDENTITY_FIELDS),
            ).values(**{k: record[k] for k in ("latitude", "longitude", "coordinate_source")})
            added = db.execute(statement.execution_options(synchronize_session=False)).rowcount
            report["added"] += added
            if not added:
                report["changed_during_import"] += 1
                report["review"].append({"id": record["id"], "reason": "changed_during_import"})
        db.expire_all()
        source = db.get(EducationSource, "school-locations-v1")
        if source is None:
            # Attribution for the offered bundle, not a claim that every row was applied.
            db.add(EducationSource(id="school-locations-v1", report={
                "bundle_id": bundle.get("bundle_id"), "prepared_on": bundle.get("prepared_on"),
                "offered_records": len(records), "sources": bundle["sources"],
            }))
        db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--apply", action="store_true", help="Commit missing coordinates. Without this flag, preview only.")
    parser.add_argument("--report", type=Path, help="Optional JSON report of skipped records")
    args = parser.parse_args()
    if any(not inspect(engine).has_table(t) for t in (School.__tablename__, EducationSource.__tablename__)):
        raise SystemExit("Import the directory first: python -m scripts.import_education --create-tables")
    try:
        bundle = load_bundle(args.file)
        with SessionLocal.begin() as db:
            report = import_locations(db, bundle, apply=args.apply)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({k: v for k, v in report.items() if k != "review"}, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.apply:
        print("Preview only. To add eligible locations, repeat with --apply.")


if __name__ == "__main__":
    main()

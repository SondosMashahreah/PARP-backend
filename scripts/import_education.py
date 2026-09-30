"""Explicit, transactional, repeatable import. No deletes, no automatic startup migration."""
import argparse
import json
from pathlib import Path
from sqlalchemy import inspect
from app.core.database import SessionLocal, engine
from app.models.education import Directorate, EducationSource, Governorate, School
from app.services.education import normalize_query

DATA = Path(__file__).resolve().parents[1] / "data" / "education"
TABLES = [Governorate.__table__, Directorate.__table__, School.__table__, EducationSource.__table__]


def import_data(db, directory=DATA):
    stats = {"inserted": 0, "existing": 0}
    for filename, model in [("governorates.json", Governorate), ("directorates.json", Directorate), ("schools.json", School)]:
        for item in json.loads((directory / filename).read_text(encoding="utf-8")):
            if db.get(model, item["id"]) is not None:
                stats["existing"] += 1
                continue  # Preserve subsequent edits, coordinates and verified school/directorate links.
            if model is School:
                item["search_text"] = normalize_query(f'{item["name_ar"]} {item["name_en"]} {item["national_code"]}')
            else:
                item["search_text"] = normalize_query(f'{item["name_ar"]} {item["name_en"]}')
            db.add(model(**item))
            stats["inserted"] += 1
        db.flush()
    if db.get(EducationSource, "schools-upload") is None:
        db.add(EducationSource(id="schools-upload", report=json.loads((directory / "source-report.json").read_text(encoding="utf-8"))))
    db.flush()
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-tables", action="store_true", help="Create only missing education tables; never alters or drops existing tables")
    args = parser.parse_args()
    if args.create_tables:
        for table in TABLES:
            table.create(engine, checkfirst=True)
    missing = [t.name for t in TABLES if not inspect(engine).has_table(t.name)]
    if missing:
        raise SystemExit("Missing tables. Run with --create-tables on the initial import: " + ", ".join(missing))
    with SessionLocal.begin() as db:
        result = import_data(db)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

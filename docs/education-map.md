# Education directory API

This feature extends the existing FastAPI application and its configured SQLAlchemy/PostgreSQL database. It does not create a second production database. The current repository includes users, JWT/OTP authentication, profile/MinIO support and the AI assistant. These are retained. There are no existing school/directorate/research models to reuse. Every new education route requires the existing `get_current_user` dependency (active, verified account). Responses contain only institutional directory fields and never user profiles or research statistics.

## Setup (from the backend repository root)

Use the existing Python environment and `.env`. The existing `DATABASE_URL` and `SECRET_KEY` remain authoritative. `.env.example` illustrates the PostgreSQL 16 service already defined in `docker-compose.yml`; never overwrite an existing `.env` with it. Start that service if this project uses the supplied local Docker configuration:

```powershell
docker compose up -d postgres
python -m scripts.import_education --create-tables
uvicorn app.main:app --reload
```

`--create-tables` creates only missing `education_*` tables. It never drops, truncates, alters, or recreates existing tables. Education schema creation is explicit, not an application-startup side effect. The existing startup creation of the user table is preserved and scoped to `User.__table__`. The data import runs in one transaction. Re-running inserts only IDs not already present and preserves edited school records, verified coordinates, and directorate links. Existing records are deliberately not refreshed from the seed; future corrections should use a reviewed migration. Run a single importer at a time.

Initial successful output: `{"inserted": 3132, "existing": 0}`. This means **3094 school records + 16 governorates + 22 directorate/agency records**, not 3132 distinct schools. A subsequent import reports zero inserts and 3132 existing records. The source-audit row is not counted in this output.

No new production Python dependency is required. The repository's existing pinned `requirements.txt` is unchanged (UTF-16). Tests additionally require `httpx`; install it in the development environment with `python -m pip install httpx` if absent.

## API

| GET route | Response / filters |
| --- | --- |
| `/api/education/catalog` | Bilingual governorates, directorates/agencies, available classifications, actual school-record counts, source summary |
| `/api/education/boundaries` | GeoJSON FeatureCollection of the 16 supplied governorate polygons |
| `/api/education/directorates/boundaries` | Only verified directorate geometries actually stored in the database; initially empty |
| `/api/education/schools` | `q`, `region`, `governorate_id`, `directorate_id`, `school_type`, `location`; `offset` and `limit` (1–100, default 25) |
| `/api/education/schools/points` | Same filters + required `bbox=west,south,east,north`; `limit` max 5000, default 2000. Located schools only; `total` and `truncated` included |
| `/api/education/schools/{id}` | Public school detail or 404 |

`region`: `PS01` or `PS02`. `location`: `all`, `located`, `missing`. `unassigned` is supported for governorate/directorate filters. Arabic diacritics, Alef forms, Arabic numerals, and English case are normalized. Search matches school names/national codes and linked governorate/directorate names. SQL parameters are bound and LIKE wildcard characters escaped. No caller-supplied SQL is executed.

The API paginates school records; it does not deliver the entire directory on every search. Located points are constrained by viewport and an explicit ceiling. GeoJSON responses are gzip-compressed when accepted by the client. At a substantially larger scale, introduce PostgreSQL search/spatial indexes and vector tiles based on actual measurements; this implementation does not claim million-user load testing.

## Verified coordinates and school-to-directorate links

The uploaded school workbook contains neither. A school's governorate centroid must **never** become its school marker. Obtain verified coordinates and/or school/directorate membership, then create a UTF-8 JSON array using the API's stable school IDs:

```json
[
  {"id": "COPY_A_REAL_SCHOOL_ID_FROM_THE_API", "directorate_id": "dir-nablus"}
]
```

Only add a directorate ID when the school relationship is verified; the example's directorate is not a suggested assignment. For locations, add numeric `latitude`, `longitude`, and nonempty `coordinate_source`. Coordinates must be WGS84 degrees and supplied together. No sample coordinates are provided to avoid accidental import as real locations.

```powershell
python -m scripts.enrich_education .\verified-school-links.json
```

The command validates IDs, finite coordinate pairs, ranges and provenance, rejects duplicate records, and rolls back the whole batch on error. National codes are **not unique** in the source, so they are never used as primary keys. Subsequent seed imports preserve this enrichment.

Directorate polygon geometry belongs to `education_directorates.geometry`; actual verified GeoJSON polygons can be added through a reviewed data migration. Do not copy governorate polygons into that field. The API and map renderer already support this layer once verified geometry is stored.

## Deployment

Keep the existing `FRONTEND_ORIGIN` CORS configuration and `VITE_API_URL` frontend backend address. Credential support, allowed methods/headers and the auth/profile/assistant routers are preserved. The directory client reuses the existing access-token refresh flow. Configure SPA fallback for `/map` and `/observatory/map` without sending API requests to `index.html`. Requests in Swagger require a valid Bearer access token from the existing sign-in flow.

Use the existing database credentials. Private research metrics, if introduced later, need their own authorization in backend routes; hiding controls in the frontend is not authorization.

## Validation

```powershell
python -m unittest discover -s tests -v
```

The six tests create an isolated in-memory SQLite database and a verified test account, seed the actual supplied data, and exercise JWT access enforcement, existing route registration, API filtering/pagination, Arabic/English search, real geometry counts, missing locations, invalid bounding boxes, duplicate-code preservation, repeat-import preservation, and transactional enrichment. Synthetic coordinates occur **only in that test database** and are rolled back/cleaned up. Production targets the existing PostgreSQL database; a running PostgreSQL service was not available for runtime verification here. Checked with Python 3.12, FastAPI 0.115.6, SQLAlchemy 2.0.36, Pydantic 2.10.4 and httpx 0.28.1 in an isolated validation environment; the repository's pinned production versions were not changed.

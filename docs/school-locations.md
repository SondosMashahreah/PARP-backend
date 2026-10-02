# School reference locations — 2026-10-01

This is an incremental enrichment of the existing 3,094 school records. It does not add schools, change IDs, link educational directorates, or supply research indicators. No schema migration or extra runtime dependency is needed.

| Region | Directory records | Matched coordinates | Unresolved |
| --- | ---: | ---: | ---: |
| West Bank | 2,360 | 2,359 | 1 |
| Gaza Strip | 734 | 22 | 712 |
| Total | 3,094 | 2,381 | 713 |

These are dated reference locations, not evidence of present-day operation, building condition, or field verification. Some schools/shifts legitimately share premises; a count of school records is not necessarily a count of buildings. The 713 unresolved records remain searchable with no invented map pin.

## Apply to the existing database

Activate the project's Python environment and run from the backend root, using its existing DATABASE_URL:

```powershell
python -m scripts.import_education --create-tables
python -m scripts.import_school_locations
python -m scripts.import_school_locations --apply
```

The first command creates only missing education tables and inserts only missing directory records. The second previews the location import without writing. The third commits eligible coordinates in one transaction. No download happens during import or application startup.

Existing coordinates are always preserved, even if they differ from the bundle. Edited school names, codes, governorate assignments, or regions are skipped for review. Unknown IDs or invalid coordinates abort before any location writes. Conditional updates protect against concurrent edits. Repeating the import does not overwrite edits or duplicate records. Original directorate links remain intact. To record skipped rows:

```powershell
python -m scripts.import_school_locations --report "$env:TEMP\PARP-location-import.json"
```

Expected clean-seed preview: `eligible=2381`. First apply: `added=2381`. Repeat: `already_present=2381`, `added=0`. Smaller added counts are expected if there are existing user coordinates/identity edits; examine the report. Restart/reload the frontend directory after importing. Select a school or zoom to level 10+ for markers; clusters expand when selected. The list remains usable without WebGL.

## Sources and matching

1. **Ministry of Education and UNICEF via OCHA oPt / HDX:** [State of Palestine - West Bank schools](https://data.humdata.org/dataset/state-of-palestine-west-bank-schools). Dataset date **2015-06-01**; 2,359 point features. Match uses a unique national code on both sides plus an exact normalized Arabic or English name. A point must fall inside its listed governorate when one exists. Two originally unassigned governorates remain NULL: their unique code/name matches are retained without inventing an administrative link.
2. **© OpenStreetMap contributors, exported by Humanitarian OpenStreetMap Team:** [Education Facilities of Palestine, State of](https://data.humdata.org/dataset/hotosm_pse_education_facilities), snapshot **2026-09-06**. Only `amenity=school` features qualify. An exact normalized name must uniquely identify both a source feature and target school inside the listed governorate. Multiple matching nodes/footprints or shifts remain unresolved. Point coordinates are copied. For a polygon school footprint, an interior representative point is computed and labelled accordingly; this is not a surveyed entrance or governorate centre. 22 Gaza school records qualify.

Normalization removes diacritics/punctuation, normalizes alef/yaa variants, collapses spaces, ignores case, and removes a leading Arabic word `مدرسة`. It retains gender, grade, shift letters/numbers and word order. No fuzzy names, address geocoding, anonymous same-name results, or approximate governorate-centre placements are imported.

The original uploaded workbook is byte-identical to the [HDX Schools XLSX](https://data.humdata.org/dataset/state-of-palestine-schools), whose catalog date is **2022-03-07** (SHA-256 `25a58a2b007e1fcbfb8f6c27b7a6847192a2a6791aef954072caa8fed3912db3`). A catalog date is not proof that every record was surveyed on that date. It also does not make the 2015 coordinates current.

Other public ArcGIS and UNOSAT sources were inspected but not imported because some observation dates/provenance were unclear or identities conflicted. This bundle does not claim complete coverage of Gaza. Completing it needs a school coordinate file with stable school codes and clear provenance; the unresolved CSV identifies the exact remaining records.

## Data and attribution

- `data/education/school-locations.json`: import bundle with per-record identity, coordinates, matching method, original source names and IDs, dates and attribution. Coordinates are WGS84; latitude/longitude in database fields, `[longitude, latitude]` in GeoJSON.
- `data/education/school-location-report.json`: source resource URLs, input hashes, matching counts and coverage by governorate.
- `data/education/school-locations-unresolved.csv`: all 713 unresolved records and reasons; UTF-8 BOM for Excel on Windows. No suggested/fuzzy locations are silently imported.
- `data/education/school-locations-osm.geojson`: the complete OSM-derived subset used here, with attribution and ODbL license URL. The same downloadable file is included in the frontend's `public/data/` for users of the map.

West Bank data retains the source's Creative Commons Attribution attribution. The OSM-derived subset is made available under **ODbL 1.0**, © OpenStreetMap contributors, with the original HOT snapshot referenced. Retain attribution and license links when distributing these data. These dataset notices do not change the application's source-code license.

## Reproduce preparation (optional, not needed to install)

`tools/prepare_school_locations.py` is an offline preparation tool, separate from the server. Use a separate Python environment with `pyshp==2.3.1`, `shapely==2.0.6`, `numpy==2.1.3`. Download the two ZIPs from the exact resource URLs in the report, then:

```text
python tools/prepare_school_locations.py --wb-zip schools_wb.zip --osm-zip hot-schools.zip
```

The tool verifies the original input hashes and stops if upstream files changed. Review new versions before changing the expected hashes. The server importer uses existing SQLAlchemy dependencies only.

## Validation

`python -m unittest discover -s tests -v` exercises the actual bundle, dry run, idempotency, edit preservation, atomic rollback, invalid/swapped coordinates, unknown IDs, bilingual search, authenticated point endpoints and bounding-box filtering against an isolated SQLite database. It does not access the user's database. The frontend patch is additionally checked by its build, tests and ESLint. Live WebGL rendering and a live PostgreSQL instance were not tested in this workspace.

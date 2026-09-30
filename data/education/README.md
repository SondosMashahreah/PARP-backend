# Data provenance and coverage

Prepared 2026-09-30 from the user's supplied files and the two public institutional directories below. These files are import inputs, not frontend demo data.

- `governorates.json`: all 16 features from `pse_admin2.geojson`, with polygon/multipolygon coordinates retained exactly. Labels use the source's administrative centres; they are not school or directorate office locations. Boundary validity: **2023-10-19**. Arabic governorate names are matched to the source codes.
- `schools.json`: the six original columns from `schools_opt_.xlsx`, retained in `source_values`, plus normalized fields and stable IDs. **3132 source rows, 38 exactly duplicate rows, 3094 distinct full records.** Different records sharing national code `38331760` remain distinct. Two `<Null>` governorate entries remain unassigned. The file's observation date was not supplied.
- `directorates.json`: union of the published [eSchool directory](https://eschool.edu.ps/) and [Ministry directorate map](https://moe.edu.ps/services/map), consulted 2026-09-30. The eSchool list supplies 21 names (including agency entries); the Ministry list adds Jerusalem. English directory labels are translations. The southern-governorates entry remains regional, not a guessed Gaza-city jurisdiction. This is **not a certification of a complete/current national census**. No directorate boundaries or office locations are invented.
- `source-report.json`: source SHA-256, all duplicate row numbers and retained row IDs, unassigned counts and coverage notes. Import preparation date is distinct from the unknown school-data observation date.

`DISTRICT` in the school file identifies a governorate, not an educational directorate. Aliases mapped to source codes: `Gaza North → PS0255`, `Middle Area → PS0265`, `Khan Yunis → PS0270`; other English governorate names match the supplied boundary labels. Types are lowercased; `PA` is retained as its own source classification rather than assumed to mean `government`. Region values are matched from the workbook to `PS01/PS02`.

Stable record ID: `school-` plus the first 20 hexadecimal characters of SHA-256 of Python `json.dumps(original_six_fields, ensure_ascii=False, sort_keys=True)`. Deduplication compares that canonical full record, not just name/code. The complete duplicate audit is retained.

**No coordinates or school-to-directorate links were supplied.** Every seed school has `latitude`, `longitude`, `coordinate_source`, and `directorate_id` set to null. `pse_adminpoints.geojson` contains administrative label points, not school locations. `pse_adminlines.geojson` describes boundaries, not school locations. Country/region boundaries in admin0/admin1 were not used as directorate polygons.

All displayed totals are counts of stored directory records. They are not current enrolment, active-school, research, teacher, or problem statistics. The National Observatory must receive research indicators from a separate genuine source before displaying those metrics.

"""Offline, reproducible matching. GIS dependencies are NOT server dependencies.

pip install pyshp==2.3.1 shapely==2.0.6 numpy==2.1.3
python tools/prepare_school_locations.py --wb-zip schools_wb.zip --osm-zip hot-schools.zip
Inputs and SHA-256 are recorded in school-location-report.json.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile

import shapefile
from shapely.geometry import Point, shape

DATA = Path(__file__).resolve().parents[1] / 'data' / 'education'
PREPARED = '2026-10-01'
WB_URL = 'https://data.humdata.org/dataset/state-of-palestine-west-bank-schools'
HOT_URL = 'https://data.humdata.org/dataset/hotosm_pse_education_facilities'
WB_SHA256 = '711ae0f732b58b0f804d7712f49e59038381be58c14825801404805fe01612cf'
HOT_SHA256 = 'f3c07627229df23c3976082fd0cdd0ddd821df38fffcb6bc4f8364c84cab6f5c'


def normalize_name(value):
    # Retain grade, gender, shift, numbers, and word order. No fuzzy matching.
    value = unicodedata.normalize('NFKC', value or '').lower().strip()
    value = re.sub('[\u064b-\u065f\u0670ـ]', '', value)
    value = re.sub('[أإآٱ]', 'ا', value).replace('ى', 'ي')
    value = re.sub(r'[^\w\s]', ' ', value)
    value = re.sub(r'^مدرسة\s+', '', value)
    return ' '.join(value.split())


def verified_input(path, expected):
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f'Source changed: {path}; expected {expected}, found {actual}. Review it before updating this preparation.')
    return zipfile.ZipFile(io.BytesIO(raw))


def prepare(wb_zip, osm_zip, output=DATA):
    schools = json.loads((DATA / 'schools.json').read_text(encoding='utf-8'))
    governors = json.loads((DATA / 'governorates.json').read_text(encoding='utf-8'))
    polygons = {g['id']: shape(g['geometry']) for g in governors}
    def containing(point):
        return [uid for uid, polygon in polygons.items() if polygon.covers(point)]
    with verified_input(wb_zip, WB_SHA256) as archive:
        reader = shapefile.Reader(shp=io.BytesIO(archive.read('schools_WB.shp')),
                                 shx=io.BytesIO(archive.read('schools_WB.shx')),
                                 dbf=io.BytesIO(archive.read('schools_WB.dbf')), encoding='utf-8')
        wb = []
        for row in reader.iterShapeRecords():
            item = row.record.as_dict()
            lon, lat = row.shape.points[0]
            item.update(longitude=lon, latitude=lat, governorates=containing(Point(lon, lat)))
            wb.append(item)
    with verified_input(osm_zip, HOT_SHA256) as archive:
        hot_raw = json.loads(archive.read('education_facilities.geojson'))['features']
    source_codes = defaultdict(list)
    for item in wb:
        source_codes[str(item['schid'])].append(item)
    target_codes = Counter(s['national_code'] for s in schools)
    accepted = {}
    reasons = {}
    identity = ('id', 'national_code', 'name_ar', 'name_en', 'governorate_id', 'region')
    for school in schools:
        if school['region'] != 'PS01':
            continue
        candidates = source_codes[school['national_code']]
        if len(candidates) != 1 or target_codes[school['national_code']] != 1:
            reasons[school['id']] = 'no_unique_national_code_match'
            continue
        candidate = candidates[0]
        same_ar = normalize_name(school['name_ar']) == normalize_name(candidate['Arabic_sch'])
        same_en = bool(school['name_en']) and normalize_name(school['name_en']) == normalize_name(candidate['English_Sc'])
        if not (same_ar or same_en):
            reasons[school['id']] = 'national_code_name_conflict'
            continue
        if school['governorate_id'] and school['governorate_id'] not in candidate['governorates']:
            reasons[school['id']] = 'governorate_conflict'
            continue
        # The two schools with NULL governorates retain NULL. No invented link.
        accepted[school['id']] = {**{k: school[k] for k in identity},
            'latitude': candidate['latitude'], 'longitude': candidate['longitude'],
            'source_id': 'hdx-wb-2015', 'source_record_id': str(candidate['OBJECTID']),
            'source_name_ar': candidate['Arabic_sch'], 'source_name_en': candidate['English_Sc'],
            'match_method': 'unique_national_code_and_exact_name',
            'geometry_method': 'source_point', 'source_date': '2015-06-01',
            'spatial_check': 'inside_listed_governorate' if school['governorate_id'] else 'source_governorate_unassigned_retained',
            'coordinate_source': f"HDX / MoE + UNICEF; West Bank schools, 2015-06-01; schid {candidate['schid']}; exact code + name; {WB_URL}",
        }
    # OSM names are matched only to amenity=school, within the listed governorate.
    # Multiple footprints/nodes or multiple target schools sharing a name remain unresolved.
    hot, index = {}, defaultdict(set)
    for feature in hot_raw:
        props = feature['properties']
        if props.get('amenity') != 'school':
            continue
        geometry = shape(feature['geometry'])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ('Point', 'Polygon', 'MultiPolygon'):
            continue
        point = geometry if geometry.geom_type == 'Point' else geometry.representative_point()
        names = {normalize_name(props.get(k)) for k in ('name', 'name_ar', 'name_en', 'name_latin')} - {''}
        hot[props['id']] = (feature, point)
        for name in names:
            for governorate_id in containing(point):
                index[governorate_id, name].add(props['id'])
    school_candidates, reverse = {}, defaultdict(set)
    # Reverse uniqueness is checked against ALL targets, not only unmatched targets.
    for school in schools:
        candidates = set()
        for name in {normalize_name(school['name_ar']), normalize_name(school['name_en'])} - {''}:
            candidates.update(index[school['governorate_id'], name])
        school_candidates[school['id']] = candidates
        for fid in candidates:
            reverse[fid].add(school['id'])
    for school in schools:
        if school['id'] in accepted:
            continue
        candidates = school_candidates[school['id']]
        if len(candidates) != 1 or (candidates and len(reverse[next(iter(candidates))]) != 1):
            reasons[school['id']] = 'ambiguous_name_or_multiple_features' if candidates else 'no_unambiguous_source_match'
            continue
        fid = next(iter(candidates))
        feature, point = hot[fid]
        props = feature['properties']
        method = 'source_point' if feature['geometry']['type'] == 'Point' else 'point_inside_mapped_school_footprint'
        accepted[school['id']] = {**{k: school[k] for k in identity},
            'latitude': point.y, 'longitude': point.x,
            'source_id': 'hotosm-2026-09-06', 'source_record_id': fid,
            'source_name_ar': props.get('name_ar') or props.get('name'), 'source_name_en': props.get('name_en'),
            'match_method': 'unique_exact_name_and_governorate', 'geometry_method': method,
            'source_date': '2026-09-06', 'spatial_check': 'inside_listed_governorate',
            'coordinate_source': f"© OpenStreetMap contributors / HOT; snapshot 2026-09-06; {fid}; exact name + governorate; {method}; ODbL 1.0; https://www.openstreetmap.org/{fid}",
        }
    sources = [
        {'id': 'hdx-wb-2015', 'title': 'State of Palestine - West Bank schools',
         'publisher': 'Ministry of Education and UNICEF, via OCHA oPt / HDX', 'url': WB_URL,
         'resource_url': 'https://data.humdata.org/dataset/0306a338-951c-45ec-a9b1-184a0f099d05/resource/61d4145d-0330-4135-bd53-8a3eec4c6e23/download/schools_wb.zip',
         'dataset_date': '2015-06-01', 'retrieved_on': PREPARED, 'sha256': WB_SHA256,
         'license': 'Creative Commons Attribution', 'license_url': 'https://www.opendefinition.org/licenses/cc-by', 'features': len(wb)},
        {'id': 'hotosm-2026-09-06', 'title': 'Education Facilities of Palestine, State of',
         'publisher': '© OpenStreetMap contributors; Humanitarian OpenStreetMap Team', 'url': HOT_URL,
         'resource_url': 'https://production-raw-data-api.s3.amazonaws.com/ISO3/PSE/education_facilities/hotosm_pse_education_facilities_osm_geojson.zip',
         'snapshot_date': '2026-09-06', 'retrieved_on': PREPARED, 'sha256': HOT_SHA256,
         'license': 'ODbL 1.0', 'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/', 'features': len(hot_raw)},
    ]
    records = [accepted[s['id']] for s in schools if s['id'] in accepted]
    bundle = {'schema_version': 1, 'bundle_id': 'parp-school-locations-2026-10-01', 'prepared_on': PREPARED,
              'crs': 'EPSG:4326', 'sources': sources, 'records': records}
    coverage = []
    for governor in governors + [{'id': None, 'name_ar': 'غير محدد', 'name_en': 'Unassigned'}]:
        subset = [s for s in schools if s['governorate_id'] == governor['id']]
        located = sum(s['id'] in accepted for s in subset)
        coverage.append({k: governor[k] for k in ('id', 'name_ar', 'name_en')} | {'total': len(subset), 'located': located, 'unresolved': len(subset)-located})
    report = {'prepared_on': PREPARED, 'total': len(schools), 'located': len(records), 'unresolved': len(schools)-len(records),
              'by_source': dict(Counter(r['source_id'] for r in records)), 'by_region': dict(Counter(r['region'] for r in records)),
              'coverage': coverage,
              'registry': {'url': 'https://data.humdata.org/dataset/state-of-palestine-schools', 'dataset_date': '2022-03-07',
                           'sha256': '25a58a2b007e1fcbfb8f6c27b7a6847192a2a6791aef954072caa8fed3912db3', 'match_to_uploaded_workbook': 'byte_identical'},
              'sources': sources,
              'limits': ['Source dates are not evidence of present-day operation, physical condition, or field verification.',
                         'No fuzzy geocoding, guessed governorate centres, or inferred directorate links.',
                         'The two original NULL governorate assignments are preserved.',
                         'Other surveyed ArcGIS/UNOSAT sources were not merged: dates/provenance or identities were insufficiently clear.']}
    output.mkdir(parents=True, exist_ok=True)
    for filename, data in [('school-locations.json', bundle), ('school-location-report.json', report)]:
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (output / 'school-locations-unresolved.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = list(identity) + ['reason', 'candidate_source_ids']
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n'); writer.writeheader()
        for s in schools:
            if s['id'] not in accepted:
                writer.writerow({**{k: s[k] for k in identity}, 'reason': reasons.get(s['id'], 'no_unambiguous_source_match'),
                                 'candidate_source_ids': ';'.join(sorted(school_candidates.get(s['id'], [])))})
    # Downloadable OSM-derived subset for attribution/share-alike; not a map fallback.
    osm_subset = {'type': 'FeatureCollection', 'license': 'ODbL 1.0', 'license_url': sources[1]['license_url'],
                  'attribution': sources[1]['publisher'], 'snapshot_date': '2026-09-06',
                  'features': [{'type': 'Feature', 'id': r['id'], 'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
                                'properties': {k: r[k] for k in ('id', 'name_ar', 'name_en', 'source_record_id', 'match_method', 'geometry_method')}}
                               for r in records if r['source_id'] == 'hotosm-2026-09-06']}
    (output / 'school-locations-osm.geojson').write_text(json.dumps(osm_subset, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['total', 'located', 'unresolved', 'by_source', 'by_region']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wb-zip', required=True, type=Path)
    parser.add_argument('--osm-zip', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=DATA)
    args = parser.parse_args()
    prepare(args.wb_zip, args.osm_zip, args.output)

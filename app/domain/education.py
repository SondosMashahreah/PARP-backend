import re
import unicodedata

def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").lower()
    value = "".join(c for c in value if not unicodedata.combining(c) and c != "ـ")
    value = value.translate(str.maketrans("أإآٱىة٠١٢٣٤٥٦٧٨٩", "اااايه0123456789"))
    return " ".join(re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE).split())



def school_payload(school):
    keys = ("id", "national_code", "name_ar", "name_en", "school_type", "governorate_id", "directorate_id", "region", "latitude", "longitude", "coordinate_source")
    return {key: getattr(school, key) for key in keys}

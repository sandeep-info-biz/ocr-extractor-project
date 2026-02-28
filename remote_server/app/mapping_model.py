import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from app.language_utils import normalize_languages


DEFAULT_MODEL_PATH = Path("models/resume_mapping_model.json")


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _collect_unique(items: List[object]) -> List[str]:
    counts: Dict[str, int] = {}
    first_seen: Dict[str, int] = {}
    canonical: Dict[str, str] = {}
    for idx, item in enumerate(items):
        value = _norm(item)
        if not value:
            continue
        key = value.lower()
        canonical[key] = canonical.get(key, value)
        counts[key] = counts.get(key, 0) + 1
        if key not in first_seen:
            first_seen[key] = idx
    ranked_keys = sorted(counts.keys(), key=lambda k: (-counts[k], first_seen[k]))
    return [canonical[k] for k in ranked_keys]


def _update_counted_values(
    values: List[object],
    counts: Dict[str, int],
    first_seen: Dict[str, int],
    canonical: Dict[str, str],
    base_index: int = 0,
    weight: int = 1,
) -> int:
    idx = base_index
    for item in values:
        value = _norm(item)
        if not value:
            continue
        key = value.lower()
        canonical[key] = canonical.get(key, value)
        counts[key] = counts.get(key, 0) + max(1, int(weight or 1))
        if key not in first_seen:
            first_seen[key] = idx
        idx += 1
    return idx


def _contains_phrase(text_lower: str, phrase: str) -> bool:
    candidate = phrase.lower().strip()
    if not candidate:
        return False
    if len(candidate) <= 2:
        return False
    return re.search(rf"\b{re.escape(candidate)}\b", text_lower) is not None


def _first_match(text_lower: str, candidates: List[str]) -> str:
    for value in candidates:
        if _contains_phrase(text_lower, value):
            return value
    return ""


def train_mapping_model_from_dataset(dataset: List[Dict[str, object]]) -> Dict[str, List[str]]:
    first_names: List[object] = []
    last_names: List[object] = []
    cities: List[object] = []
    country_regions: List[object] = []
    countries: List[object] = []
    postal_codes: List[object] = []
    date_of_births: List[object] = []
    genders: List[object] = []
    religions: List[object] = []
    marital_statuses: List[object] = []
    languages: List[object] = []
    industries: List[object] = []
    designations: List[object] = []
    passport_numbers: List[object] = []
    passport_expiry_dates: List[object] = []
    education_degrees: List[object] = []
    summaries: List[object] = []
    linkedin_urls: List[object] = []
    skills: List[object] = []
    projects: List[object] = []

    for row in dataset:
        try:
            weight = int(row.get("_feedback_weight", 1) or 1)
        except Exception:
            weight = 1
        weight = max(1, min(5, weight))
        for _ in range(weight):
            first_names.append(row.get("first_name", ""))
            last_names.append(row.get("last_name", ""))
            cities.append(row.get("city", ""))
            country_regions.append(row.get("country_region", ""))
            countries.append(row.get("nationality_country_name", ""))
            postal_codes.append(row.get("postal_code", ""))
            date_of_births.append(row.get("date_of_birth", ""))
            genders.append(row.get("gender", ""))
            religions.append(row.get("religion", ""))
            marital_statuses.append(row.get("marital_status", ""))
            industries.append(row.get("industry_type", ""))
            designations.append(row.get("designation_or_position", ""))
            passport_numbers.append(row.get("passport_number", ""))
            passport_expiry_dates.append(row.get("passport_expiry_date", ""))
            education_degrees.append(row.get("education_degree", ""))
            summaries.append(row.get("about_description_summary", ""))
            linkedin_urls.append(row.get("linkedin_url", ""))
            skills.extend([str(x) for x in row.get("skills", []) if isinstance(x, str)])
            languages.extend(normalize_languages(row.get("languages", []) if isinstance(row.get("languages"), list) else []))
            projects.extend([str(x) for x in row.get("projects", []) if isinstance(x, str)])

            for edu in row.get("education", []) if isinstance(row.get("education"), list) else []:
                if isinstance(edu, dict):
                    education_degrees.append(edu.get("degree", ""))

    return {
        "first_names": _collect_unique(first_names),
        "last_names": _collect_unique(last_names),
        "cities": _collect_unique(cities),
        "country_regions": _collect_unique(country_regions),
        "countries": _collect_unique(countries),
        "postal_codes": _collect_unique(postal_codes),
        "date_of_births": _collect_unique(date_of_births),
        "genders": _collect_unique(genders),
        "religions": _collect_unique(religions),
        "marital_statuses": _collect_unique(marital_statuses),
        "languages": _collect_unique(languages),
        "industry_types": _collect_unique(industries),
        "designations": _collect_unique(designations),
        "passport_numbers": _collect_unique(passport_numbers),
        "passport_expiry_dates": _collect_unique(passport_expiry_dates),
        "education_degrees": _collect_unique(education_degrees),
        "summaries": _collect_unique(summaries),
        "linkedin_urls": _collect_unique(linkedin_urls),
        "skills": _collect_unique(skills),
        "projects": _collect_unique(projects),
    }


def update_mapping_model_with_rows(
    model: Dict[str, List[str]],
    rows: List[Dict[str, object]],
) -> Dict[str, List[str]]:
    if not rows:
        return dict(model or {})

    # Keep ordering stable by reusing current model order as the initial "first seen" signal.
    fields = {
        "first_names": [],
        "last_names": [],
        "cities": [],
        "country_regions": [],
        "countries": [],
        "postal_codes": [],
        "date_of_births": [],
        "genders": [],
        "religions": [],
        "marital_statuses": [],
        "languages": [],
        "industry_types": [],
        "designations": [],
        "passport_numbers": [],
        "passport_expiry_dates": [],
        "education_degrees": [],
        "summaries": [],
        "linkedin_urls": [],
        "skills": [],
        "projects": [],
    }

    counts: Dict[str, Dict[str, int]] = {k: {} for k in fields.keys()}
    first_seen: Dict[str, Dict[str, int]] = {k: {} for k in fields.keys()}
    canonical: Dict[str, Dict[str, str]] = {k: {} for k in fields.keys()}

    for field_key in fields.keys():
        idx = 0
        for value in (model or {}).get(field_key, []):
            idx = _update_counted_values(
                [value],
                counts[field_key],
                first_seen[field_key],
                canonical[field_key],
                base_index=idx,
                weight=1,
            )

    for row in rows:
        try:
            weight = int(row.get("_feedback_weight", 1) or 1)
        except Exception:
            weight = 1
        weight = max(1, min(5, weight))

        mapped = {
            "first_names": [row.get("first_name", "")],
            "last_names": [row.get("last_name", "")],
            "cities": [row.get("city", "")],
            "country_regions": [row.get("country_region", "")],
            "countries": [row.get("nationality_country_name", "")],
            "postal_codes": [row.get("postal_code", "")],
            "date_of_births": [row.get("date_of_birth", "")],
            "genders": [row.get("gender", "")],
            "religions": [row.get("religion", "")],
            "marital_statuses": [row.get("marital_status", "")],
            "languages": normalize_languages(row.get("languages", []) if isinstance(row.get("languages"), list) else []),
            "industry_types": [row.get("industry_type", "")],
            "designations": [row.get("designation_or_position", "")],
            "passport_numbers": [row.get("passport_number", "")],
            "passport_expiry_dates": [row.get("passport_expiry_date", "")],
            "education_degrees": [row.get("education_degree", "")],
            "summaries": [row.get("about_description_summary", "")],
            "linkedin_urls": [row.get("linkedin_url", "")],
            "skills": [str(x) for x in row.get("skills", []) if isinstance(x, str)],
            "projects": [str(x) for x in row.get("projects", []) if isinstance(x, str)],
        }
        for edu in row.get("education", []) if isinstance(row.get("education"), list) else []:
            if isinstance(edu, dict):
                mapped["education_degrees"].append(edu.get("degree", ""))

        for field_key, values in mapped.items():
            base_idx = len(first_seen[field_key])
            _update_counted_values(
                values,
                counts[field_key],
                first_seen[field_key],
                canonical[field_key],
                base_index=base_idx,
                weight=weight,
            )

    out: Dict[str, List[str]] = {}
    for field_key in fields.keys():
        ranked_keys = sorted(
            counts[field_key].keys(),
            key=lambda k: (-counts[field_key][k], first_seen[field_key].get(k, 10**9)),
        )
        out[field_key] = [canonical[field_key].get(k, k) for k in ranked_keys]
    return out


def save_mapping_model(model: Dict[str, List[str]], path: Path = DEFAULT_MODEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    load_mapping_model.cache_clear()
    return path


@lru_cache(maxsize=1)
def load_mapping_model(path: Path = DEFAULT_MODEL_PATH) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def apply_mapping_model(parsed: Dict[str, object], text: str, model: Dict[str, List[str]]) -> Dict[str, object]:
    if not model:
        return parsed

    text_lower = text.lower()

    if not parsed.get("first_name"):
        parsed["first_name"] = _first_match(text_lower, model.get("first_names", []))
    if not parsed.get("last_name"):
        parsed["last_name"] = _first_match(text_lower, model.get("last_names", []))
    if not parsed.get("city"):
        parsed["city"] = _first_match(text_lower, model.get("cities", []))
    if not parsed.get("country_region"):
        parsed["country_region"] = _first_match(text_lower, model.get("country_regions", []))
    if not parsed.get("nationality_country_name"):
        parsed["nationality_country_name"] = _first_match(text_lower, model.get("countries", []))
    if not parsed.get("postal_code"):
        parsed["postal_code"] = _first_match(text_lower, model.get("postal_codes", []))
    if not parsed.get("date_of_birth"):
        parsed["date_of_birth"] = _first_match(text_lower, model.get("date_of_births", []))
    if not parsed.get("gender"):
        parsed["gender"] = _first_match(text_lower, model.get("genders", []))
    if not parsed.get("religion"):
        parsed["religion"] = _first_match(text_lower, model.get("religions", []))
    if not parsed.get("marital_status"):
        parsed["marital_status"] = _first_match(text_lower, model.get("marital_statuses", []))
    if not parsed.get("industry_type"):
        parsed["industry_type"] = _first_match(text_lower, model.get("industry_types", []))
    if not parsed.get("designation_or_position"):
        parsed["designation_or_position"] = _first_match(text_lower, model.get("designations", []))
    if not parsed.get("passport_number"):
        parsed["passport_number"] = _first_match(text_lower, model.get("passport_numbers", []))
    if not parsed.get("passport_expiry_date"):
        parsed["passport_expiry_date"] = _first_match(text_lower, model.get("passport_expiry_dates", []))
    if not parsed.get("education_degree"):
        parsed["education_degree"] = _first_match(text_lower, model.get("education_degrees", []))
    if not parsed.get("about_description_summary"):
        parsed["about_description_summary"] = _first_match(text_lower, model.get("summaries", []))
    if not parsed.get("linkedin_url"):
        parsed["linkedin_url"] = _first_match(text_lower, model.get("linkedin_urls", []))

    existing_skills = {str(x).lower() for x in parsed.get("skills", []) if str(x).strip()}
    for skill in model.get("skills", []):
        if _contains_phrase(text_lower, skill):
            existing_skills.add(skill.lower())
    parsed["skills"] = sorted(existing_skills)

    existing_languages = [str(x) for x in parsed.get("languages", []) if str(x).strip()]
    merged_languages = list(existing_languages)
    seen_languages = {x.lower() for x in existing_languages}
    for language in model.get("languages", []):
        if _contains_phrase(text_lower, language) and language.lower() not in seen_languages:
            merged_languages.append(language)
            seen_languages.add(language.lower())
    parsed["languages"] = normalize_languages(merged_languages)

    existing_projects = [str(x).strip() for x in parsed.get("projects", []) if str(x).strip()]
    seen_projects = {x.lower() for x in existing_projects}
    merged_projects = list(existing_projects)
    for project in model.get("projects", []):
        if _contains_phrase(text_lower, project) and project.lower() not in seen_projects:
            merged_projects.append(project)
            seen_projects.add(project.lower())
    parsed["projects"] = merged_projects[:8]

    if not parsed.get("education_degree"):
        education = parsed.get("education", []) if isinstance(parsed.get("education"), list) else []
        if education and isinstance(education[0], dict):
            parsed["education_degree"] = _norm(education[0].get("degree", ""))

    total_experience = parsed.get("total_experience")
    if total_experience is None:
        years = re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text_lower)
        if years:
            parsed["total_experience"] = max(int(x) for x in years)

    gulf = parsed.get("gulf_expierence")
    if not isinstance(gulf, bool):
        parsed["gulf_expierence"] = bool(
            re.search(r"\b(gulf|uae|dubai|qatar|oman|kuwait|bahrain|saudi)\b", text_lower)
        )

    return parsed

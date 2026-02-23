import re
from datetime import date
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from app.constants import DEFAULT_SKILLS, DEGREE_HINTS, EMAIL_RE, PHONE_RE, SECTION_HEADERS, URL_RE
from app.mapping_model import apply_mapping_model, load_mapping_model
from app.pretrained_resume_model import MODEL_REGISTRY, extract_entities


MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@lru_cache(maxsize=4)
def load_spacy_pipeline(prefer_fast: bool = True):
    try:
        import spacy
    except Exception:
        return None, "spacy_unavailable"

    candidate_models = ["en_core_web_sm", "en_core_web_lg", "en_core_web_trf"] if prefer_fast else [
        "en_core_web_trf",
        "en_core_web_lg",
        "en_core_web_sm",
    ]
    nlp = None
    loaded_name = "blank_en"
    for candidate in candidate_models:
        try:
            nlp = spacy.load(candidate, exclude=["tagger", "parser", "lemmatizer", "textcat"])
            loaded_name = candidate
            break
        except Exception:
            continue
    if nlp is None:
        nlp = spacy.blank("en")

    if "entity_ruler" not in nlp.pipe_names:
        ruler = nlp.add_pipe("entity_ruler", before="ner" if "ner" in nlp.pipe_names else None)
    else:
        ruler = nlp.get_pipe("entity_ruler")

    existing = set()
    if hasattr(ruler, "patterns"):
        for p in ruler.patterns:
            label = p.get("label", "")
            pattern = str(p.get("pattern", "")).lower()
            existing.add((label, pattern))

    patterns = []
    for skill in DEFAULT_SKILLS:
        key = ("SKILL", skill.lower())
        if key not in existing:
            patterns.append({"label": "SKILL", "pattern": skill})
    for degree in DEGREE_HINTS:
        key = ("DEGREE", degree.lower())
        if key not in existing:
            patterns.append({"label": "DEGREE", "pattern": degree})
    if patterns:
        ruler.add_patterns(patterns)
    return nlp, loaded_name


def normalize_spaces(text: str) -> str:
    text = str(text or "").replace("\x00", " ")
    # Keep page separator token intact while cleaning OCR noise.
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _collapse_spaced_month_names(text: str) -> str:
    out = str(text or "")
    for month in sorted(set(MONTH_MAP.keys()), key=len, reverse=True):
        letters = r"\s*".join(list(month))
        out = re.sub(rf"\b{letters}\b", month, out, flags=re.IGNORECASE)
    return out


def _normalize_date_text(text: str) -> str:
    out = str(text or "")
    out = _collapse_spaced_month_names(out)
    out = re.sub(r"(\d{1,2})\s*(st|nd|rd|th)\b", r"\1", out, flags=re.IGNORECASE)
    out = re.sub(r"(\d)\s+(?=[/-])", r"\1", out)
    out = re.sub(r"(?<=[/-])\s+(\d)", r"\1", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _coerce_two_digit_year(year: int) -> int:
    if year >= 100:
        return year
    # Assume adult resume candidates; 00-29 -> 2000+, else 1900+.
    return 2000 + year if year <= 29 else 1900 + year


def _is_reasonable_dob(y: int, m: int, d: int) -> bool:
    try:
        dob = date(y, m, d)
    except Exception:
        return False
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return 14 <= age <= 80


def _to_iso_dob(y: int, m: int, d: int) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}"


def _extract_date_candidates(text: str) -> List[Tuple[int, int, int]]:
    src = _normalize_date_text(text)
    out: List[Tuple[int, int, int]] = []

    # YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
    for y, m, d in re.findall(r"\b((?:19|20)\d{2})[./-](\d{1,2})[./-](\d{1,2})\b", src):
        out.append((int(y), int(m), int(d)))

    # DD-MM-YYYY / MM-DD-YYYY / DD/MM/YY (resolved later)
    for a, b, y in re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", src):
        aa, bb, yy = int(a), int(b), _coerce_two_digit_year(int(y))
        # Try DD-MM first (common in resumes), then MM-DD.
        out.append((yy, bb, aa))
        out.append((yy, aa, bb))

    # DD Month YYYY
    for d, mon, y in re.findall(
        r"\b(\d{1,2})\s*[-,]?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*[-,]?\s*(\d{2,4})\b",
        src,
        flags=re.IGNORECASE,
    ):
        mm = MONTH_MAP.get(mon.lower(), 0)
        yy = _coerce_two_digit_year(int(y))
        out.append((yy, mm, int(d)))

    # Month DD YYYY
    for mon, d, y in re.findall(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*[-,]?\s*(\d{1,2})\s*[-,]?\s*(\d{2,4})\b",
        src,
        flags=re.IGNORECASE,
    ):
        mm = MONTH_MAP.get(mon.lower(), 0)
        yy = _coerce_two_digit_year(int(y))
        out.append((yy, mm, int(d)))

    # De-duplicate preserving order
    uniq: List[Tuple[int, int, int]] = []
    seen = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def extract_date_of_birth(text: str) -> str:
    src = _normalize_date_text(text)

    # Prefer dates found near DOB keywords.
    context_patterns = [
        r"(?:date\s*of\s*birth|dob|d\.?\s*o\.?\s*b\.?)\s*[:\-]?\s*([^\n]{0,80})",
        r"(?:birth\s*date|born\s*on)\s*[:\-]?\s*([^\n]{0,80})",
    ]
    for pat in context_patterns:
        for snippet in re.findall(pat, src, flags=re.IGNORECASE):
            for y, m, d in _extract_date_candidates(snippet):
                if _is_reasonable_dob(y, m, d):
                    return _to_iso_dob(y, m, d)

    # Fallback global scan with light filtering (skip expiry-like contexts).
    for match in re.finditer(r".{0,20}", src):
        _ = match  # keeps lint happy in minimal environments
        break
    for y, m, d in _extract_date_candidates(src):
        if not _is_reasonable_dob(y, m, d):
            continue
        candidate = _to_iso_dob(y, m, d)
        near = re.search(rf".{{0,20}}{re.escape(candidate)}.{{0,20}}", src, flags=re.IGNORECASE)
        if near and re.search(r"(expiry|passport|valid|issue)", near.group(0), flags=re.IGNORECASE):
            continue
        return candidate
    return ""


def _split_pages(text: str) -> List[str]:
    parts = [p.strip() for p in re.split(r"\[\[PAGE_BREAK\]\]", str(text or ""), flags=re.IGNORECASE) if p.strip()]
    return parts if parts else [str(text or "")]


def _page_resume_score(text: str) -> int:
    keywords = [
        "resume",
        "experience",
        "education",
        "skills",
        "project",
        "linkedin",
        "objective",
        "summary",
        "work history",
        "certification",
    ]
    low = text.lower()
    return sum(1 for key in keywords if key in low)


def _page_vaccination_score(text: str) -> int:
    keywords = [
        "certificate for covid",
        "vaccination",
        "covid-19",
        "covin",
        "covishield",
        "dose",
        "beneficiary",
        "batch no",
    ]
    low = text.lower()
    return sum(1 for key in keywords if key in low)


def _select_resume_pages(text: str) -> str:
    pages = _split_pages(text)
    if len(pages) <= 1:
        return text

    selected: List[str] = []
    for page in pages:
        resume_score = _page_resume_score(page)
        vaccination_score = _page_vaccination_score(page)
        # Keep clear resume pages, and keep uncertain pages as context.
        if resume_score >= vaccination_score or (resume_score == 0 and vaccination_score == 0):
            selected.append(page)

    # If all pages looked non-resume, keep original text to avoid empty parsing.
    return "\n".join(selected) if selected else text


def extract_contacts(text: str) -> Dict[str, Optional[str]]:
    emails = sorted(set(EMAIL_RE.findall(text)))
    raw_phones = sorted(set(PHONE_RE.findall(text)))
    normalized_phones = []
    for phone in raw_phones:
        digits = re.sub(r"\D", "", phone)
        if 10 <= len(digits) <= 15:
            normalized_phones.append(phone.strip())
    links = sorted(set(URL_RE.findall(text)))
    return {
        "email": emails[0] if emails else None,
        "phone": normalized_phones[0] if normalized_phones else None,
        "linkedin_or_website": links[0] if links else None,
        "emails_all": emails,
        "phones_all": normalized_phones,
        "links_all": links,
    }


def extract_profile_links(text: str) -> Dict[str, Optional[str]]:
    links = sorted(set(URL_RE.findall(text)))
    linkedin = None
    for link in links:
        lower = link.lower()
        if linkedin is None and "linkedin.com" in lower:
            linkedin = link
    return {"linkedin": linkedin}


def guess_location(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocked_terms = {
        "language",
        "languages",
        "passport",
        "skill",
        "skills",
        "experience",
        "education",
        "linkedin",
        "github",
        "email",
        "phone",
    }
    for ln in lines[:14]:
        lower = ln.lower()
        if "@" in ln or "http" in lower or "www." in lower:
            continue
        if PHONE_RE.search(ln):
            continue
        if any(hint in lower for hint in DEGREE_HINTS):
            continue
        if re.search(r"\b(?:19|20)\d{2}\b", ln):
            continue
        if any(term in lower for term in blocked_terms):
            continue
        if re.search(r"\b\d{5,6}\b", ln) and "," in ln:
            return ln
        if "," in ln and len(ln.split()) <= 10:
            return ln
    return ""


def guess_name(nlp, text: str) -> Optional[str]:
    head = "\n".join(text.splitlines()[:8])
    if nlp is not None:
        doc = nlp(head[:400])
        people = [ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON" and len(ent.text.split()) <= 4]
        if people:
            return people[0]
    for ln in text.splitlines()[:8]:
        clean = ln.strip()
        if 2 <= len(clean.split()) <= 4 and clean.replace(" ", "").isalpha():
            return clean
    return None


def split_name(full_name: str) -> Tuple[str, str]:
    parts = [p for p in full_name.split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def split_sections(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    normalized = [ln.strip() for ln in lines]
    idx_map: List[Tuple[str, int]] = []

    for i, ln in enumerate(normalized):
        lower_ln = ln.lower().strip(":")
        for sec, keys in SECTION_HEADERS.items():
            if lower_ln in keys:
                idx_map.append((sec, i))
                break

    if not idx_map:
        return {}

    sections: Dict[str, str] = {}
    idx_map.sort(key=lambda x: x[1])
    for pos, (sec, start_idx) in enumerate(idx_map):
        end_idx = idx_map[pos + 1][1] if pos + 1 < len(idx_map) else len(lines)
        body = "\n".join(lines[start_idx + 1:end_idx]).strip()
        sections[sec] = body
    return sections


def extract_skills(nlp, text: str, section_text: Optional[str] = None) -> List[str]:
    source = section_text if section_text else text
    source_lower = source.lower()
    found = set()
    if nlp is not None:
        doc = nlp(source_lower[:6000])
        for ent in doc.ents:
            if ent.label_ == "SKILL":
                found.add(ent.text.lower())
    for skill in DEFAULT_SKILLS:
        if re.search(rf"\b{re.escape(skill.lower())}\b", source_lower):
            found.add(skill.lower())
    return sorted(found)


def extract_languages(section_text: Optional[str], text: str) -> List[str]:
    if section_text:
        source = section_text
    else:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        matched = [ln for ln in lines if re.search(r"\blanguages?\b", ln, flags=re.IGNORECASE)]
        source = "\n".join(matched)
    parts = re.split(r"[\n,;/|:]+", source)
    out: List[str] = []
    seen = set()
    for part in parts:
        token = re.sub(r"[^A-Za-z ]", " ", part).strip()
        if not token:
            continue
        words = token.split()
        if not words:
            continue
        if len(words) > 3:
            continue
        key = token.lower()
        if key in {"language", "languages", "proficiency", "fluent", "native"}:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(token.title())
    return out[:8]


def extract_education(text: str, edu_section: Optional[str] = None) -> List[str]:
    source = edu_section if edu_section else text
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    results = []
    for ln in lines:
        l = ln.lower()
        if any(h in l for h in DEGREE_HINTS):
            results.append(ln)
    return results[:10]


def structure_education(education_lines: List[str], section_text: Optional[str]) -> List[Dict[str, object]]:
    source_lines = [ln.strip() for ln in (section_text.splitlines() if section_text else education_lines) if ln.strip()]
    if not source_lines:
        return []
    items: List[Dict[str, object]] = []
    for ln in source_lines[:10]:
        lower = ln.lower()
        if not any(h in lower for h in DEGREE_HINTS) and "," not in ln:
            continue
        year_match = re.search(r"(?:19|20)\d{2}", ln)
        year = int(year_match.group(0)) if year_match else None
        degree = ""
        institution = ""
        parts = [p.strip() for p in re.split(r"\s*[-|,]\s*", ln) if p.strip()]
        for p in parts:
            if any(h in p.lower() for h in DEGREE_HINTS) and not degree:
                degree = p
            elif not institution:
                institution = p
        if not degree:
            degree = parts[0] if parts else ln
        if not institution and len(parts) > 1:
            institution = parts[1]
        items.append(
            {
                "degree": degree,
                "field_of_study": "",
                "institution": institution,
                "graduation_year": year,
            }
        )
    return items


def extract_summary(text: str, sections: Dict[str, str]) -> str:
    if sections.get("summary"):
        summary_lines = [ln.strip() for ln in sections["summary"].splitlines() if ln.strip()]
        return " ".join(summary_lines[:4]).strip()

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    stop_words = set()
    for keys in SECTION_HEADERS.values():
        stop_words.update(k.lower() for k in keys)
    summary_lines: List[str] = []
    for ln in lines[1:12]:
        l = ln.lower().strip(":")
        if l in stop_words:
            break
        if EMAIL_RE.search(ln) or PHONE_RE.search(ln) or URL_RE.search(ln):
            continue
        summary_lines.append(ln)
        if len(" ".join(summary_lines)) > 320:
            break
    return " ".join(summary_lines).strip()


def extract_postal_code(text: str) -> str:
    match = re.search(r"\b\d{5,6}\b", text)
    return match.group(0) if match else ""


def extract_passport_number(text: str) -> str:
    match = re.search(r"\b[A-Z][0-9]{7}\b", text.upper())
    return match.group(0) if match else ""


def extract_passport_expiry_date(text: str) -> str:
    expiry_line = re.search(
        r"(passport\s+expiry|expiry\s+date)\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}[/-][0-9]{2}[/-][0-9]{2,4})",
        text,
        flags=re.IGNORECASE,
    )
    if expiry_line:
        return expiry_line.group(2)
    date_match = re.search(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b", text)
    return date_match.group(0) if date_match else ""


def extract_total_experience(text: str) -> Optional[int]:
    candidates = re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text, flags=re.IGNORECASE)
    if not candidates:
        return None
    try:
        return max(int(x) for x in candidates)
    except Exception:
        return None


def infer_gulf_experience(text: str) -> bool:
    return bool(re.search(r"\b(gulf|uae|dubai|qatar|oman|kuwait|bahrain|saudi)\b", text, flags=re.IGNORECASE))


def split_location_parts(location: str) -> Tuple[str, str, str]:
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if not parts:
        return "", "", ""
    city = parts[0]
    country = parts[-1] if len(parts) > 1 else ""
    region = parts[1] if len(parts) > 2 else ""
    return city, region, country


def _merge_pretrained_entities(parsed: Dict[str, object], entities: List[Dict[str, object]]) -> None:
    if (not parsed.get("first_name")) and entities:
        for ent in entities:
            label = str(ent.get("label", "")).upper()
            value = str(ent.get("text", "")).strip()
            if label in {"NAME", "PERSON"} and value:
                first, last = split_name(value)
                parsed["first_name"] = first
                parsed["last_name"] = last
                break

    for ent in entities:
        label = str(ent.get("label", "")).upper()
        value = str(ent.get("text", "")).strip()
        if not value:
            continue
        if label in {"EMAIL", "MAIL"} and not parsed.get("email"):
            parsed["email"] = value
        elif label in {"PHONE", "CONTACT"} and not parsed.get("phone_number"):
            parsed["phone_number"] = value
        elif label in {"LINKEDIN"} and not parsed.get("linkedin_url"):
            parsed["linkedin_url"] = value
        elif label in {"LOCATION", "CITY", "ADDRESS"} and not parsed.get("city"):
            parsed["city"] = value
        elif label in {"DESIGNATION", "ROLE", "POSITION", "JOB_TITLE"} and not parsed.get("designation_or_position"):
            parsed["designation_or_position"] = value
        elif label in {"SKILL", "SKILLS", "TECHNOLOGY"}:
            current = {str(x).lower() for x in parsed.get("skills", [])}
            current.update(x.strip().lower() for x in re.split(r"[,;/]", value) if x.strip())
            parsed["skills"] = sorted(current)


def parse_resume_text(raw_text: str, mode: str = "balanced") -> Dict[str, object]:
    text = normalize_spaces(_select_resume_pages(raw_text))
    if mode not in {"fast", "balanced", "resume_bert"}:
        mode = "balanced"

    nlp = None
    if mode in {"balanced", "resume_bert"}:
        nlp, _ = load_spacy_pipeline(prefer_fast=True)

    sections = split_sections(text)
    contacts = extract_contacts(text)
    links = extract_profile_links(text)
    full_name = guess_name(nlp, text) or ""
    first_name, last_name = split_name(full_name)
    skills = extract_skills(nlp, text, sections.get("skills"))
    education_lines = extract_education(text, sections.get("education"))
    education = structure_education(education_lines, sections.get("education"))
    summary = extract_summary(text, sections)
    location = guess_location(text)
    city, country_region, nationality_country_name = split_location_parts(location)

    parsed: Dict[str, object] = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": contacts.get("phone") or "",
        "email": contacts.get("email") or "",
        "date_of_birth": extract_date_of_birth(text),
        "gender": "",
        "religion": "",
        "marital_status": "",
        "nationality_country_name": nationality_country_name,
        "country_region": country_region,
        "city": city,
        "postal_code": extract_postal_code(text),
        "languages": extract_languages(sections.get("languages"), text),
        "industry_type": "",
        "designation_or_position": "",
        "total_experience": extract_total_experience(text),
        "gulf_expierence": infer_gulf_experience(text),
        "passport_number": extract_passport_number(text),
        "passport_expiry_date": extract_passport_expiry_date(text),
        "skills": skills,
        "education": education,
        "education_degree": education[0]["degree"] if education else "",
        "about_description_summary": summary,
        "linkedin_url": links.get("linkedin") or "",
        "raw_text": text,
    }

    if mode == "resume_bert":
        entities = extract_entities(text, model_key="resume_ner_bert_v2")
        _merge_pretrained_entities(parsed, entities)

    mapping_model = load_mapping_model()
    parsed = apply_mapping_model(parsed, text, mapping_model)
    return parsed


def get_model_metadata(mode: str) -> Dict[str, object]:
    if mode == "resume_bert":
        meta = MODEL_REGISTRY["resume_ner_bert_v2"]
        return {
            "mode": mode,
            "model_key": "resume_ner_bert_v2",
            "provider": meta["provider"],
            "model_id": meta["model_id"],
            "reported_f1": meta["reported_f1"],
            "notes": meta["notes"],
        }
    if mode == "fast":
        return {"mode": mode, "model_key": "rule_based", "notes": "Regex + rules only (optimized for speed)."}
    return {"mode": mode, "model_key": "spacy_local", "notes": "Local spaCy + rules (balanced speed/quality)."}

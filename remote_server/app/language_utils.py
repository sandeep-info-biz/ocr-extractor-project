import re
from typing import Iterable, List


_CANONICAL_BY_KEY = {
    "english": "English",
    "hindi": "Hindi",
    "tamil": "Tamil",
    "telugu": "Telugu",
    "kannada": "Kannada",
    "malayalam": "Malayalam",
    "marathi": "Marathi",
    "gujarati": "Gujarati",
    "bengali": "Bengali",
    "urdu": "Urdu",
    "punjabi": "Punjabi",
    "odia": "Odia",
    "oriya": "Odia",
    "assamese": "Assamese",
    "sanskrit": "Sanskrit",
    "arabic": "Arabic",
    "french": "French",
    "german": "German",
}

_ALIASES = {
    "eng": "english",
    "en": "english",
    "hin": "hindi",
    "tam": "tamil",
    "tel": "telugu",
    "kan": "kannada",
    "mal": "malayalam",
    "mar": "marathi",
    "guj": "gujarati",
    "ben": "bengali",
    "urd": "urdu",
    "panjabi": "punjabi",
    "odia": "odia",
    "oriya": "oriya",
}

_NOISE_WORDS = {
    "language",
    "languages",
    "known",
    "speak",
    "speaks",
    "speaking",
    "proficiency",
    "fluent",
    "native",
    "basic",
    "intermediate",
    "advanced",
    "and",
}


def _clean_token(token: str) -> str:
    text = re.sub(r"[^a-zA-Z ]", " ", str(token or "")).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    words = [w for w in text.split() if w and w not in _NOISE_WORDS]
    return " ".join(words).strip()


def normalize_languages(values: Iterable[object]) -> List[str]:
    out: List[str] = []
    seen = set()

    for value in values:
        text = str(value or "")
        if not text.strip():
            continue
        parts = re.split(r"[\n,;/|:&]+|\band\b", text, flags=re.IGNORECASE)
        for part in parts:
            clean = _clean_token(part)
            if not clean:
                continue

            candidates = [clean]
            if " " in clean:
                candidates.extend(clean.split())

            for cand in candidates:
                key = _ALIASES.get(cand, cand)
                canonical = _CANONICAL_BY_KEY.get(key, "")
                if not canonical:
                    continue
                low = canonical.lower()
                if low in seen:
                    continue
                seen.add(low)
                out.append(canonical)

    return out

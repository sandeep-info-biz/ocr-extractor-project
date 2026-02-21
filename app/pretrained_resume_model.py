from functools import lru_cache
from typing import Dict, List


MODEL_REGISTRY: Dict[str, Dict[str, object]] = {
    "resume_ner_bert_v2": {
        "provider": "huggingface",
        "model_id": "yashpwr/resume-ner-bert-v2",
        "task": "token-classification",
        "reported_f1": 0.9087,
        "notes": "Resume-specific NER model (model-card reported).",
    }
}


def _normalize_label(label: str) -> str:
    clean = label.upper()
    if clean.startswith("B-") or clean.startswith("I-"):
        clean = clean[2:]
    return clean


@lru_cache(maxsize=1)
def _load_hf_pipeline(model_key: str):
    if model_key not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model key: {model_key}")

    model_id = str(MODEL_REGISTRY[model_key]["model_id"])
    try:
        from transformers import pipeline
    except Exception as exc:
        raise RuntimeError(
            "transformers is required for pretrained resume model inference. "
            "Install dependencies in requirements.txt."
        ) from exc

    return pipeline(
        "token-classification",
        model=model_id,
        tokenizer=model_id,
        aggregation_strategy="simple",
        device=-1,
    )


def extract_entities(text: str, model_key: str = "resume_ner_bert_v2", max_chars: int = 12000) -> List[Dict[str, object]]:
    ner = _load_hf_pipeline(model_key)
    clipped = text[:max_chars]
    entities = ner(clipped)
    normalized = []
    for ent in entities:
        label = _normalize_label(str(ent.get("entity_group", ent.get("entity", ""))))
        normalized.append(
            {
                "label": label,
                "text": str(ent.get("word", "")).strip(),
                "score": float(ent.get("score", 0.0)),
                "start": int(ent.get("start", 0)),
                "end": int(ent.get("end", 0)),
            }
        )
    return normalized


from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

SCHEMA_FIELDS = [
    "first_name",
    "last_name",
    "phone_number",
    "email",
    "date_of_birth",
    "gender",
    "religion",
    "marital_status",
    "nationality_country_name",
    "country_region",
    "city",
    "postal_code",
    "languages",
    "industry_type",
    "designation_or_position",
    "total_experience",
    "gulf_expierence",
    "passport_number",
    "passport_expiry_date",
    "skills",
    "education",
    "education_degree",
    "about_description_summary",
    "linkedin_url",
    "projects",
    "raw_text",
]

PROMPT_TEMPLATE = """You are a resume parser.
Extract data from the resume text into strict JSON.
Return only one JSON object and no extra text.
Use exactly these keys:
{keys}

Rules:
- If a field is not found, return empty string, [] or null where appropriate.
- Keep `skills` and `languages` as arrays of strings.
- Keep `projects` as array of strings.
- Keep `education` as array of objects with keys: degree, field_of_study, institution, graduation_year.
- Keep `gulf_expierence` boolean.
- Keep `total_experience` integer or null.

Resume text:
{text}
"""


def _runtime_load_config() -> tuple[object, dict]:
    import torch

    if torch.cuda.is_available():
        return torch.float16, {"device_map": "auto"}
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        # Apple MPS does not support bfloat16 for this path; keep to fp16.
        return torch.float16, {"device_map": {"": "mps"}}
    return torch.float32, {"device_map": {"": "cpu"}}


def empty_llm_schema(raw_text: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {field: "" for field in SCHEMA_FIELDS}
    payload["languages"] = []
    payload["skills"] = []
    payload["education"] = []
    payload["projects"] = []
    payload["total_experience"] = None
    payload["gulf_expierence"] = False
    payload["raw_text"] = raw_text
    return payload


def _debug_log(debug_events: list[str] | None, message: str) -> None:
    line = f"[llm_extractor] {message}"
    print(line)
    if debug_events is not None:
        debug_events.append(line)


def _extract_first_json_block(text: str) -> Dict[str, Any]:
    decoder = json.JSONDecoder()
    start_positions = [m.start() for m in re.finditer(r"\{", text)]
    for start in start_positions:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    raise ValueError("Model response does not include a valid JSON object.")


def _normalize_to_schema(payload: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    out = empty_llm_schema(raw_text=raw_text)
    for field in SCHEMA_FIELDS:
        if field in payload:
            out[field] = payload[field]

    if not isinstance(out.get("languages"), list):
        out["languages"] = []
    if not isinstance(out.get("skills"), list):
        out["skills"] = []
    if not isinstance(out.get("education"), list):
        out["education"] = []
    if not isinstance(out.get("projects"), list):
        out["projects"] = []

    normalized_edu = []
    for item in out["education"]:
        if isinstance(item, dict):
            normalized_edu.append(
                {
                    "degree": str(item.get("degree", "")),
                    "field_of_study": str(item.get("field_of_study", "")),
                    "institution": str(item.get("institution", "")),
                    "graduation_year": item.get("graduation_year", None),
                }
            )
    out["education"] = normalized_edu

    total_exp = out.get("total_experience")
    if isinstance(total_exp, str):
        digits = re.findall(r"\d+", total_exp)
        out["total_experience"] = int(digits[0]) if digits else None
    elif not isinstance(total_exp, int):
        out["total_experience"] = None

    gulf = out.get("gulf_expierence")
    if isinstance(gulf, str):
        out["gulf_expierence"] = gulf.strip().lower() in {"1", "true", "yes", "y"}
    elif not isinstance(gulf, bool):
        out["gulf_expierence"] = False

    return out


@lru_cache(maxsize=2)
def _load_lora_model(base_model_id: str, adapter_path: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    torch_dtype, load_kwargs = _runtime_load_config()
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch_dtype,
        **load_kwargs,
    )
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.eval()
    return tokenizer, model


@lru_cache(maxsize=2)
def _load_base_model(base_model_id: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch_dtype, load_kwargs = _runtime_load_config()
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch_dtype,
        **load_kwargs,
    )
    model.eval()
    return tokenizer, model


def run_lora_qlora_extraction(
    raw_text: str,
    adapter_path: str,
    base_model_id: str,
    max_new_tokens: int = 768,
    debug_events: list[str] | None = None,
) -> Dict[str, Any]:
    adapter_cfg = Path(adapter_path) / "adapter_config.json"
    adapter_exists = Path(adapter_path).exists()
    adapter_has_config = adapter_cfg.exists()
    _debug_log(debug_events, f"start base_model_id={base_model_id}, adapter_path={adapter_path}, max_new_tokens={max_new_tokens}")
    _debug_log(debug_events, f"adapter_exists={adapter_exists}")
    _debug_log(debug_events, f"adapter_config_exists={adapter_has_config}")

    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401
    except Exception as exc:
        _debug_log(debug_events, f"core dependency import failed: {exc!r}")
        raise RuntimeError(
            "LLM inference dependencies missing. Install transformers and torch."
        ) from exc

    _debug_log(debug_events, f"torch_version={getattr(torch, '__version__', 'unknown')}")
    _debug_log(debug_events, f"transformers_version={getattr(transformers, '__version__', 'unknown')}")
    dtype, kwargs = _runtime_load_config()
    _debug_log(debug_events, f"load_torch_dtype={dtype}, load_device_map={kwargs.get('device_map')}")
    _debug_log(debug_events, "core dependencies imported successfully")
    if adapter_exists and adapter_has_config:
        try:
            from peft import PeftModel  # noqa: F401
        except Exception as exc:
            _debug_log(debug_events, f"peft import failed: {exc!r}")
            raise RuntimeError(
                "Adapter is present but `peft` is missing. Install peft>=0.11 or remove adapter path to use base model."
            ) from exc
        tokenizer, model = _load_lora_model(base_model_id, adapter_path)
        _debug_log(debug_events, "loaded_lora_adapter=True")
    else:
        tokenizer, model = _load_base_model(base_model_id)
        _debug_log(debug_events, "loaded_lora_adapter=False (fallback_to_base_model=True)")

    _debug_log(debug_events, f"model_loaded_device={model.device}")
    prompt = PROMPT_TEMPLATE.format(keys=", ".join(SCHEMA_FIELDS), text=raw_text[:14000])
    inputs = tokenizer(prompt, return_tensors="pt")
    prompt_tokens = int(inputs["input_ids"].shape[-1]) if "input_ids" in inputs else -1
    _debug_log(debug_events, f"prompt_chars={len(prompt)}, prompt_tokens={prompt_tokens}")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    _debug_log(debug_events, f"generated_chars={len(generated)}")
    parsed = _extract_first_json_block(generated)
    _debug_log(debug_events, f"json_parse_success keys_count={len(parsed.keys())}")
    return _normalize_to_schema(parsed, raw_text)

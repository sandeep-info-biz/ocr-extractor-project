import tempfile
import json
import io
import hashlib
import re
import math
import time
import os
import base64
import hmac
import mimetypes
import atexit
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from app.evaluation import evaluate
from app.llm_extractor import empty_llm_schema, run_lora_qlora_extraction
from app.mapping_model import save_mapping_model, train_mapping_model_from_dataset
from app.ocr import extract_raw_text
from app.parser import parse_resume_text
from app.pretrained_resume_model import MODEL_REGISTRY
from app.schemas import (
    AutoTrainLLMResponse,
    ExtractionWithTokenResponse,
    FeedbackRequest,
    FeedbackResponse,
    RetrainMappingRequest,
    RetrainMappingResponse,
    ResumeExtractedResponse,
)

app = FastAPI(
    title="Resume OCR Extractor API",
    version="1.0.0",
    description="FastAPI service for OCR resume extraction.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATASET_PATH = Path("data/resume_training_seed.json")
MODEL_PATH = Path("models/resume_mapping_model.json")
SESSION_STORE_PATH = Path("data/feedback_sessions.json")
FEEDBACK_LOG_PATH = Path("data/feedback_log.json")
FEEDBACK_FIELD_CHANGES_PATH = Path("data/feedback_field_changes.json")
TRAINING_EVENTS_PATH = Path("data/training_events.json")
FEEDBACK_MEMORY_PATH = Path("data/feedback_memory.json")
ASYNC_DOCUMENTS_PATH = Path("data/async_documents.json")
UPLOADS_DIR = Path("data/uploads")
ASYNC_DOC_LOCK = Lock()


def _async_worker_count() -> int:
    try:
        configured = int(os.getenv("ASYNC_OCR_WORKERS", "0"))
    except Exception:
        configured = 0
    if configured > 0:
        return configured
    cpu = os.cpu_count() or 2
    return max(1, min(1, cpu))


ASYNC_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=_async_worker_count(), thread_name_prefix="ocr-worker")
atexit.register(lambda: ASYNC_OCR_EXECUTOR.shutdown(wait=False, cancel_futures=True))


def _format_dd_mm_yyyy(day: int, month: int, year: int) -> str:
    return f"{day:02d}/{month:02d}/{year:04d}"


def _parse_dob_to_dd_mm_yyyy(raw: object) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None

    clean = re.sub(r"\s+", " ", value.replace(",", " ")).strip()

    # yyyy-mm-dd / yyyy/mm/dd / yyyy.mm.dd
    m = re.match(r"^(\d{4})[\/\.-](\d{1,2})[\/\.-](\d{1,2})$", clean)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(year, month, day)
            return _format_dd_mm_yyyy(day, month, year)
        except Exception:
            return None

    # dd-mm-yyyy / dd/mm/yy / dd.mm.yyyy
    m = re.match(r"^(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})$", clean)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 1900 if year > 30 else 2000
        try:
            datetime(year, month, day)
            return _format_dd_mm_yyyy(day, month, year)
        except Exception:
            return None

    # ISO with time (e.g. 1993-02-15T00:00:00)
    try:
        dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
        return _format_dd_mm_yyyy(dt.day, dt.month, dt.year)
    except Exception:
        pass

    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
        try:
            dt = datetime.strptime(clean, fmt)
            return _format_dd_mm_yyyy(dt.day, dt.month, dt.year)
        except Exception:
            continue

    return None


def _normalize_dob_fields(payload: object, key_hint: str = "") -> object:
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            out[k] = _normalize_dob_fields(v, str(k))
        return out
    if isinstance(payload, list):
        return [_normalize_dob_fields(item, key_hint) for item in payload]
    if isinstance(payload, str):
        if re.search(r"(dob|date[_\s]*of[_\s]*birth|birth[_\s]*date)", key_hint, flags=re.IGNORECASE):
            normalized = _parse_dob_to_dd_mm_yyyy(payload)
            return normalized if normalized else payload
    return payload


def _load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


def _save_json_list(path: Path, payload: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_training_events() -> dict:
    if not TRAINING_EVENTS_PATH.exists():
        return {"feedback_events": [], "retrain_events": []}
    raw = TRAINING_EVENTS_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return {"feedback_events": [], "retrain_events": []}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"feedback_events": [], "retrain_events": []}
    if not isinstance(payload, dict):
        return {"feedback_events": [], "retrain_events": []}
    feedback_events = payload.get("feedback_events", [])
    retrain_events = payload.get("retrain_events", [])
    return {
        "feedback_events": feedback_events if isinstance(feedback_events, list) else [],
        "retrain_events": retrain_events if isinstance(retrain_events, list) else [],
    }


def _save_training_events(payload: dict) -> None:
    TRAINING_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRAINING_EVENTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_async_documents() -> list:
    return _load_json_list(ASYNC_DOCUMENTS_PATH)


def _save_async_documents(rows: list) -> None:
    _save_json_list(ASYNC_DOCUMENTS_PATH, rows)


def _get_page_count(path: Path, suffix: str) -> int:
    if suffix != ".pdf":
        return 1
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        try:
            import fitz

            with fitz.open(str(path)) as doc:
                return len(doc)
        except Exception:
            return 1


def _estimate_cost_inr(page_count: int) -> float:
    # Keeps behavior close to sample payloads: 2 pages -> 10.44, 24 pages -> 20.88.
    buckets = max(1, math.ceil(max(1, page_count) / 12))
    return round(10.44 * buckets, 2)


def _convert_skills_for_api(skills: object) -> list:
    if not isinstance(skills, list):
        return []
    out = []
    for skill in skills:
        text = str(skill).strip()
        if text:
            out.append({"skill_name": text})
    return out


def _normalize_parsed_for_api(parsed: dict) -> dict:
    row = dict(parsed)
    row = _normalize_dob_fields(row)
    row["skills"] = _convert_skills_for_api(row.get("skills", []))
    row["education"] = row.get("education_degree") or ""
    row["gulf_experience"] = row.get("gulf_expierence")
    row.pop("gulf_expierence", None)
    row.pop("raw_text", None)
    return row


def _validation_errors(parsed_for_api: dict) -> list:
    value = str(parsed_for_api.get("first_name", "") or "").strip()
    if value:
        return []
    return [
        {
            "path": {"key": "first_name", "depth": 1, "index": 0},
            "rule": "required",
            "field": "first_name",
            "value": value,
            "message": "This field is required",
            "is_valid": False,
            "parser_field_id": str(uuid4()),
        }
    ]


def _find_document(document_id: str) -> dict | None:
    docs = _load_async_documents()
    for row in docs:
        if str(row.get("document_id", "")) == document_id:
            return row
    return None


def _upsert_document(updated: dict) -> None:
    with ASYNC_DOC_LOCK:
        docs = _load_async_documents()
        found = False
        for idx, row in enumerate(docs):
            if str(row.get("document_id", "")) == str(updated.get("document_id", "")):
                docs[idx] = updated
                found = True
                break
        if not found:
            docs.append(updated)
        _save_async_documents(docs)


def _mutate_document(document_id: str, mutator) -> bool:
    with ASYNC_DOC_LOCK:
        docs = _load_async_documents()
        changed = False
        found = False
        for row in docs:
            if str(row.get("document_id", "")) != str(document_id):
                continue
            found = True
            changed = bool(mutator(row))
            if changed:
                row["updated_at"] = _now_iso()
            break
        if found and changed:
            _save_async_documents(docs)
        return found


def _queue_async_document(**kwargs) -> None:
    ASYNC_OCR_EXECUTOR.submit(_process_async_document, **kwargs)


def _process_async_document(
    document_id: str,
    parser_id: str,
    environment: str,
    source_path: str,
    public_url_path: str,
    suffix: str,
    content_type: str,
    file_size: int,
    page_count: int,
    file_hash: str,
) -> None:
    started = time.perf_counter()
    created_at = _now_iso()
    try:
        path = Path(source_path)

        target_dpi = 180
        use_preprocess = True
        if page_count >= 20:
            target_dpi = 105
            use_preprocess = False
        elif page_count >= 12:
            target_dpi = 140

        raw_text = extract_raw_text(
            path,
            preprocess=use_preprocess,
            fast=True,
            pdf_dpi=target_dpi,
            progress_callback=None,
        )
        parsed = parse_resume_text(raw_text, mode="balanced")
        # Keep async flow consistent with /test flow by applying learned
        # corrections for matching raw-text fingerprints.
        parsed = _apply_feedback_memory(parsed, raw_text)
        parsed = _normalize_dob_fields(parsed)
        token_id = _register_session(parsed, mode=f"async:{parser_id}")
        parsed_api = _normalize_parsed_for_api(parsed)
        errors = _validation_errors(parsed_api)
        is_valid = len(errors) == 0

        # Dedup check by file hash.
        dedup_entry = None
        docs = _load_async_documents()
        for row in docs:
            if str(row.get("file_hash", "")) != file_hash:
                continue
            for entry in row.get("entries", []) if isinstance(row.get("entries"), list) else []:
                if str(entry.get("status", "")) == "completed" and isinstance(entry.get("parsed_data"), dict):
                    dedup_entry = entry
                    break
            if dedup_entry:
                break

        # Keep dedup flag/cost tracking, but always return fresh parsed output
        # from current parser rules (important after extractor improvements).

        processing_time = round(max(0.01, time.perf_counter() - started), 2)
        entry = {
            "id": str(uuid4()),
            "token_id": token_id,
            "status": "completed",
            "cost": _estimate_cost_inr(page_count),
            "cost_currency": "INR",
            "processing_time_seconds": processing_time,
            "created_at": created_at,
            "updated_at": _now_iso(),
            "is_deduplicated": dedup_entry is not None,
            "is_valid": is_valid,
            "parsed_data": parsed_api,
            "feedback_data": _strip_raw_text(parsed),
            "validation_errors": errors,
        }
        doc = {
            "document_id": document_id,
            "job_id": str(uuid4()),
            "parser_id": parser_id,
            "environment": environment,
            "status": "completed",
            "url": public_url_path,
            "file_hash": file_hash,
            "metadata": {
                "etag": None,
                "filename": path.name,
                "page_count": page_count,
                "size_bytes": file_size,
                "content_type": content_type,
            },
            "entries": [entry],
            "created_at": created_at,
            "updated_at": _now_iso(),
        }
        _upsert_document(doc)
    except Exception as exc:
        doc = _find_document(document_id)
        if doc is None:
            return
        failed_entry = {
            "id": str(uuid4()),
            "status": "failed",
            "cost": 0.0,
            "cost_currency": "INR",
            "processing_time_seconds": round(max(0.01, time.perf_counter() - started), 2),
            "created_at": created_at,
            "updated_at": _now_iso(),
            "is_deduplicated": False,
            "is_valid": False,
            "parsed_data": {},
            "validation_errors": [],
            "error_message": str(exc),
        }
        doc["status"] = "failed"
        doc["entries"] = [failed_entry]
        doc["updated_at"] = _now_iso()
        _upsert_document(doc)


def _validate_auth_token(authorization: str | None) -> None:
    configured = (Path("data/.api_token").read_text(encoding="utf-8").strip() if Path("data/.api_token").exists() else "")
    env_token = configured or str(os.environ.get("SIMPLYPARSE_API_TOKEN", "")).strip()
    if not env_token:
        return
    incoming = str(authorization or "").strip()
    if incoming.startswith("Token "):
        incoming = incoming[6:].strip()
    if incoming != env_token:
        raise HTTPException(status_code=401, detail="Invalid Authorization token")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("utf-8"))


def _auth_secret() -> str:
    return str(os.environ.get("API_AUTH_SECRET", "change-me-secret")).strip()


def _token_ttl_seconds() -> int:
    try:
        return max(300, int(os.environ.get("API_AUTH_TTL_SECONDS", "86400")))
    except Exception:
        return 86400


def _login_user() -> str:
    return str(os.environ.get("API_LOGIN_USER", "admin")).strip()


def _login_password() -> str:
    return str(os.environ.get("API_LOGIN_PASSWORD", "admin123")).strip()


def _create_access_token(username: str) -> str:
    now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + _token_ttl_seconds()}
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_part = _b64url_encode(payload_bytes)
    sig = hmac.new(_auth_secret().encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_part}.{_b64url_encode(sig)}"


def _verify_access_token(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("invalid token")
        payload_part, sig_part = parts
        expected = hmac.new(_auth_secret().encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
        got = _b64url_decode(sig_part)
        if not hmac.compare_digest(expected, got):
            raise ValueError("invalid signature")
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if int(time.time()) >= exp:
            raise ValueError("token expired")
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid bearer token: {exc}") from exc


def _validate_authorization(authorization: str | None) -> dict | None:
    incoming = str(authorization or "").strip()
    if incoming.startswith("Bearer "):
        token = incoming[7:].strip()
        return _verify_access_token(token)
    _validate_auth_token(authorization)
    return None


def _normalize_text_for_fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _text_fingerprint(text: str) -> str:
    normalized = _normalize_text_for_fingerprint(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _save_feedback_memory(raw_text: str, corrected_data: dict) -> bool:
    fingerprint = _text_fingerprint(raw_text)
    if not fingerprint:
        return False
    rows = _load_json_list(FEEDBACK_MEMORY_PATH)
    rows = [row for row in rows if str(row.get("fingerprint", "")) != fingerprint]
    rows.append(
        {
            "fingerprint": fingerprint,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "corrected_data": corrected_data,
        }
    )
    _save_json_list(FEEDBACK_MEMORY_PATH, rows)
    return True


def _apply_feedback_memory(parsed: dict, raw_text: str) -> dict:
    fingerprint = _text_fingerprint(raw_text)
    if not fingerprint:
        return parsed
    rows = _load_json_list(FEEDBACK_MEMORY_PATH)
    matched = None
    for row in reversed(rows):
        if str(row.get("fingerprint", "")) == fingerprint:
            matched = row
            break
    if not matched:
        return parsed
    corrected = matched.get("corrected_data", {})
    if not isinstance(corrected, dict):
        return parsed

    merged = dict(parsed)
    for key, value in corrected.items():
        if key == "raw_text":
            continue
        merged[key] = value
    return merged


def _rating_to_feedback_weight(rating: int) -> int:
    return {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}.get(rating, 1)


def _strip_raw_text(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    cleaned = dict(payload)
    cleaned.pop("raw_text", None)
    return cleaned


def _merge_with_baseline(override_data: dict | None, baseline_data: dict | None, fields_to_override: set[str]) -> dict | None:
    if override_data is None:
        return None
    base = dict(baseline_data or {})
    for field in fields_to_override:
        if field == "raw_text":
            continue
        if field in override_data:
            base[field] = override_data[field]
    return base


def _register_session(parsed: dict, mode: str) -> str:
    token_id = str(uuid4())
    sessions = _load_json_list(SESSION_STORE_PATH)
    sessions.append(
        {
            "token_id": token_id,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "extracted_data": parsed,
        }
    )
    _save_json_list(SESSION_STORE_PATH, sessions)
    return token_id


def _find_session(token_id: str) -> dict | None:
    sessions = _load_json_list(SESSION_STORE_PATH)
    for row in reversed(sessions):
        if str(row.get("token_id", "")) == token_id:
            return row
    return None


def _find_document_id_by_token(token_id: str) -> str:
    docs = _load_async_documents()
    for row in docs:
        entries = row.get("entries", []) if isinstance(row.get("entries"), list) else []
        for entry in entries:
            if str(entry.get("token_id", "")) == token_id:
                return str(row.get("document_id", "") or "")
    return ""


def _json_value_changed(old_value: object, new_value: object) -> bool:
    try:
        return json.dumps(old_value, sort_keys=True, ensure_ascii=False) != json.dumps(
            new_value, sort_keys=True, ensure_ascii=False
        )
    except Exception:
        return str(old_value) != str(new_value)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/models")
def list_models() -> dict:
    return {
        "supported_modes": ["fast", "balanced", "resume_bert"],
        "pretrained_models": MODEL_REGISTRY,
        "default_mode": "balanced",
    }


@app.post("/auth/login")
def auth_login(username: str = Form(...), password: str = Form(...)) -> dict:
    if username != _login_user() or password != _login_password():
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _create_access_token(username)
    return {
        "status": "success",
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "expires_in": _token_ttl_seconds(),
    }


@app.get("/dapi/v1/document-file/{document_id}")
def get_document_file(
    document_id: str,
    authorization: str | None = Header(default=None),
    auth: str | None = Query(default=None),
):
    if auth:
        _verify_access_token(auth)
    else:
        _validate_authorization(authorization)
    doc = _find_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document_id not found")
    meta_name = str(doc.get("metadata", {}).get("filename", "") or "")
    path = UPLOADS_DIR / f"{document_id}{Path(meta_name).suffix or '.pdf'}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="document file not found")
    media_type = str(doc.get("metadata", {}).get("content_type", "") or "").strip().lower()
    guessed = (mimetypes.guess_type(path.name)[0] or "").lower()
    # Browsers may disable inline PDF rendering when content-type is octet-stream.
    if media_type in {"", "application/octet-stream", "binary/octet-stream"}:
        media_type = guessed or "application/octet-stream"
    if media_type == "application/octet-stream":
        ext = path.suffix.lower()
        if ext == ".pdf":
            media_type = "application/pdf"
        elif ext in {".png"}:
            media_type = "image/png"
        elif ext in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif ext in {".bmp"}:
            media_type = "image/bmp"
        elif ext in {".tif", ".tiff"}:
            media_type = "image/tiff"
    # Force inline rendering so UI preview does not trigger downloads.
    return FileResponse(
        path=str(path),
        media_type=media_type,
        headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
    )


@app.post("/dapi/v1/parser/{parser_id}/parse/async")
async def parse_async_endpoint(
    parser_id: str,
    file: UploadFile = File(...),
    environment: str = Form("dev"),
    authorization: str | None = Header(default=None),
) -> dict:
    _validate_authorization(authorization)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    document_id = str(uuid4())
    job_id = str(uuid4())
    file_hash = hashlib.sha256(raw).hexdigest()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOADS_DIR / f"{document_id}{suffix}"
    stored_path.write_bytes(raw)
    page_count = _get_page_count(stored_path, suffix)
    public_url_path = f"/dapi/v1/document-file/{document_id}"

    doc = {
        "document_id": document_id,
        "job_id": job_id,
        "parser_id": parser_id,
        "environment": environment,
        "status": "processing",
        "url": public_url_path,
        "file_hash": file_hash,
        "metadata": {
            "etag": None,
            "filename": file.filename or stored_path.name,
            "page_count": page_count,
            "processed_pages": 0,
            "total_pages": page_count,
            "progress_percent": 0,
            "processing_stage": "queued",
            "size_bytes": len(raw),
            "content_type": file.content_type or "application/octet-stream",
        },
        "entries": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _upsert_document(doc)

    _queue_async_document(
        document_id=document_id,
        parser_id=parser_id,
        environment=environment,
        source_path=str(stored_path),
        public_url_path=public_url_path,
        suffix=suffix,
        content_type=file.content_type or "application/octet-stream",
        file_size=len(raw),
        page_count=page_count,
        file_hash=file_hash,
    )
    return {
        "status": "success",
        "code": "document_queued",
        "message": "Document queued for processing",
        "data": {"document_id": document_id, "job_id": job_id},
    }


@app.post("/dapi/v1/parser/{parser_id}/parse/async/batch")
async def parse_async_batch_endpoint(
    parser_id: str,
    files: list[UploadFile] = File(...),
    environment: str = Form("dev"),
    authorization: str | None = Header(default=None),
) -> dict:
    _validate_authorization(authorization)
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    queued = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".docx", ".txt"}:
            continue
        raw = await file.read()
        if not raw:
            continue
        document_id = str(uuid4())
        job_id = str(uuid4())
        file_hash = hashlib.sha256(raw).hexdigest()
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        stored_path = UPLOADS_DIR / f"{document_id}{suffix}"
        stored_path.write_bytes(raw)
        page_count = _get_page_count(stored_path, suffix)
        public_url_path = f"/dapi/v1/document-file/{document_id}"
        doc = {
            "document_id": document_id,
            "job_id": job_id,
            "parser_id": parser_id,
            "environment": environment,
            "status": "processing",
            "url": public_url_path,
            "file_hash": file_hash,
            "metadata": {
                "etag": None,
                "filename": file.filename or stored_path.name,
                "page_count": page_count,
                "processed_pages": 0,
                "total_pages": page_count,
                "progress_percent": 0,
                "processing_stage": "queued",
                "size_bytes": len(raw),
                "content_type": file.content_type or "application/octet-stream",
            },
            "entries": [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _upsert_document(doc)
        _queue_async_document(
            document_id=document_id,
            parser_id=parser_id,
            environment=environment,
            source_path=str(stored_path),
            public_url_path=public_url_path,
            suffix=suffix,
            content_type=file.content_type or "application/octet-stream",
            file_size=len(raw),
            page_count=page_count,
            file_hash=file_hash,
        )
        queued.append({"document_id": document_id, "job_id": job_id, "filename": file.filename})

    return {
        "status": "success",
        "code": "documents_queued",
        "message": "Documents queued for processing",
        "data": {"parser_id": parser_id, "count": len(queued), "items": queued},
    }


@app.get("/dapi/v1/parser/{parser_id}/document/{document_id}")
def get_document_endpoint(
    parser_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    _validate_authorization(authorization)
    doc = _find_document(document_id)
    if doc is None or str(doc.get("parser_id", "")) != parser_id:
        raise HTTPException(status_code=404, detail="document_id not found")

    entries = doc.get("entries", []) if isinstance(doc.get("entries"), list) else []
    status = str(doc.get("status", "processing") or "processing")
    if status == "failed":
        return {
            "status": "success",
            "code": "document_failed",
            "message": "Document processing failed",
            "data": {
                "document_id": doc.get("document_id", document_id),
                "status": status,
                "url": doc.get("url", ""),
                "metadata": doc.get("metadata", {}),
                "entries": entries,
            },
        }
    if status != "completed" or not entries:
        return {
            "status": "success",
            "code": "no_parsed_data",
            "message": "No parsed data found for the document",
            "data": {
                "document_id": doc.get("document_id", document_id),
                "status": status,
                "url": doc.get("url", ""),
                "metadata": doc.get("metadata", {}),
                "entries": [],
            },
        }

    return {
        "status": "success",
        "code": "document_retrieved",
        "message": "Document retrieved successfully",
        "data": {
            "document_id": doc.get("document_id", document_id),
            "status": doc.get("status", "completed"),
            "url": doc.get("url", ""),
            "metadata": doc.get("metadata", {}),
            "entries": entries,
        },
    }


@app.post("/retrain-mapping", response_model=RetrainMappingResponse)
def retrain_mapping_endpoint(payload: RetrainMappingRequest) -> RetrainMappingResponse:
    try:
        existing = []
        if DATASET_PATH.exists():
            existing = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                raise ValueError("Existing dataset is not a JSON list.")

        incoming = [entry.model_dump() for entry in payload.new_entries]
        merged = (existing + incoming) if payload.append_to_existing else incoming

        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATASET_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

        model = train_mapping_model_from_dataset(merged)
        save_mapping_model(model, MODEL_PATH)

        check_score = None
        if payload.run_check and incoming:
            scores = []
            for row in incoming:
                raw_text = str(row.get("raw_text", "")).strip()
                if not raw_text:
                    continue
                pred = parse_resume_text(raw_text, mode="fast")
                result = evaluate(pred, row)
                scores.append(float(result.get("overall", 0.0)))
            if scores:
                check_score = round(sum(scores) / len(scores), 4)

        events = _load_training_events()
        events["retrain_events"].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "retrain_mapping_endpoint",
                "added_entries": len(incoming),
                "total_dataset_entries": len(merged),
                "mapping_feature_count": sum(len(v) for v in model.values()),
                "check_average_overall_score": check_score,
            }
        )
        _save_training_events(events)

        return RetrainMappingResponse(
            dataset_path=str(DATASET_PATH),
            model_path=str(MODEL_PATH),
            total_dataset_entries=len(merged),
            added_entries=len(incoming),
            mapping_counts={k: len(v) for k, v in model.items()},
            check_average_overall_score=check_score,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/feedback", response_model=FeedbackResponse)
def feedback_endpoint(
    payload: FeedbackRequest,
    authorization: str | None = Header(default=None),
) -> FeedbackResponse:
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    auth_payload = _validate_authorization(authorization)

    session = _find_session(payload.token_id)
    if session is None:
        raise HTTPException(status_code=404, detail="token_id not found")

    submitted_at = datetime.now(timezone.utc).isoformat()
    resolved_token_id = payload.token_id
    extracted_data = _strip_raw_text(payload.extracted_data.model_dump()) if payload.extracted_data else None
    corrected_data_raw = _strip_raw_text(payload.corrected_data.model_dump()) if payload.corrected_data else None
    extracted_data = _normalize_dob_fields(extracted_data) if extracted_data is not None else None
    corrected_data_raw = _normalize_dob_fields(corrected_data_raw) if corrected_data_raw is not None else None
    feedback_weight = _rating_to_feedback_weight(payload.rating)
    feedback_accuracy = float(payload.rating) / 5.0

    baseline_pred = session.get("extracted_data", {}) if isinstance(session.get("extracted_data"), dict) else {}

    corrected_data = None
    if payload.corrected_data:
        corrected_fields = set(payload.corrected_data.model_fields_set)
        corrected_data = _merge_with_baseline(corrected_data_raw, baseline_pred, corrected_fields)
    elif payload.extracted_data:
        # UX shortcut: allow sending the same JSON shape as /test response,
        # editing extracted_data directly and submitting it as correction.
        corrected_fields = set(payload.extracted_data.model_fields_set)
        corrected_data = _merge_with_baseline(extracted_data, baseline_pred, corrected_fields)

    if corrected_data is not None:
        corrected_data = _normalize_dob_fields(corrected_data)
        feedback_accuracy = float(evaluate(baseline_pred or {}, corrected_data).get("overall", 0.0))

    user_id = str(payload.user_id or "").strip()
    if not user_id:
        if isinstance(auth_payload, dict) and str(auth_payload.get("sub", "")).strip():
            user_id = str(auth_payload.get("sub", "")).strip()
        elif authorization:
            user_id = "api_token_user"
        else:
            user_id = "anonymous"
    document_id = _find_document_id_by_token(resolved_token_id)

    if corrected_data is not None:
        field_changes = _load_json_list(FEEDBACK_FIELD_CHANGES_PATH)
        for field_name in sorted(set(list(baseline_pred.keys()) + list(corrected_data.keys()))):
            if field_name == "raw_text":
                continue
            old_value = baseline_pred.get(field_name)
            new_value = corrected_data.get(field_name)
            if not _json_value_changed(old_value, new_value):
                continue
            field_changes.append(
                {
                    "user_id": user_id,
                    "document_id": document_id,
                    "token_id": resolved_token_id,
                    "field_name": field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "timestamp": submitted_at,
                    "rating": payload.rating,
                }
            )
        _save_json_list(FEEDBACK_FIELD_CHANGES_PATH, field_changes)

    feedback_log = _load_json_list(FEEDBACK_LOG_PATH)
    feedback_log.append(
        {
            "user_id": user_id,
            "document_id": document_id,
            "token_id": resolved_token_id,
            "rating": payload.rating,
            "feedback_weight": feedback_weight,
            "feedback_accuracy": round(feedback_accuracy, 4),
            "submitted_at": submitted_at,
            "extracted_data": extracted_data,
            "corrected_data": corrected_data,
        }
    )
    _save_json_list(FEEDBACK_LOG_PATH, feedback_log)

    dataset = _load_json_list(DATASET_PATH)
    retrained = False
    train_source = corrected_data
    if train_source is not None:
        train_row = _normalize_dob_fields(dict(train_source))
        train_row["_feedback_rating"] = payload.rating
        train_row["_feedback_weight"] = feedback_weight
        train_row["_feedback_submitted_at"] = submitted_at
        dataset.append(train_row)
        _save_json_list(DATASET_PATH, dataset)
        if corrected_data is not None and isinstance(session.get("extracted_data"), dict):
            raw_text_for_memory = str(session.get("extracted_data", {}).get("raw_text", "") or "")
            _save_feedback_memory(raw_text_for_memory, corrected_data)

    model = train_mapping_model_from_dataset(dataset)
    if payload.retrain_on_submit:
        save_mapping_model(model, MODEL_PATH)
        retrained = True

    events = _load_training_events()
    events["feedback_events"].append(
        {
            "timestamp": submitted_at,
            "token_id": resolved_token_id,
            "rating": payload.rating,
            "feedback_weight": feedback_weight,
            "feedback_accuracy": round(feedback_accuracy, 4),
            "has_extracted_data": extracted_data is not None,
            "has_corrected_data": corrected_data is not None,
            "retrained": retrained,
            "total_dataset_entries": len(dataset),
        }
    )
    if retrained:
        events["retrain_events"].append(
            {
                "timestamp": submitted_at,
                "source": "feedback_endpoint",
                "added_entries": 1 if train_source is not None else 0,
                "total_dataset_entries": len(dataset),
                "mapping_feature_count": sum(len(v) for v in model.values()),
                "check_average_overall_score": round(feedback_accuracy, 4),
            }
        )
    _save_training_events(events)

    return FeedbackResponse(
        token_id=resolved_token_id,
        rating=payload.rating,
        retrained=retrained,
        total_dataset_entries=len(dataset),
        mapping_counts={k: len(v) for k, v in model.items()},
        feedback_weight=feedback_weight,
        feedback_accuracy=round(feedback_accuracy, 4),
    )


@app.get("/analytics/training-feedback")
def training_feedback_analytics() -> dict:
    events = _load_training_events()
    feedback_events = sorted(events.get("feedback_events", []), key=lambda x: str(x.get("timestamp", "")))
    retrain_events = sorted(events.get("retrain_events", []), key=lambda x: str(x.get("timestamp", "")))

    rating_distribution = {str(i): 0 for i in range(1, 6)}
    for ev in feedback_events:
        rating = int(ev.get("rating", 0) or 0)
        if 1 <= rating <= 5:
            rating_distribution[str(rating)] += 1

    accuracy_trend = [
        {"x": str(ev.get("timestamp", "")), "y": float(ev.get("feedback_accuracy", 0.0) or 0.0)}
        for ev in feedback_events
    ]
    rating_trend = [{"x": str(ev.get("timestamp", "")), "y": float(ev.get("rating", 0) or 0)} for ev in feedback_events]
    dataset_growth = [
        {"x": str(ev.get("timestamp", "")), "y": float(ev.get("total_dataset_entries", 0) or 0)} for ev in retrain_events
    ]
    model_growth = [
        {"x": str(ev.get("timestamp", "")), "y": float(ev.get("mapping_feature_count", 0) or 0)} for ev in retrain_events
    ]
    retrain_quality = [
        {"x": str(ev.get("timestamp", "")), "y": float(ev.get("check_average_overall_score", 0.0) or 0.0)}
        for ev in retrain_events
        if ev.get("check_average_overall_score") is not None
    ]

    initial_accuracy = accuracy_trend[0]["y"] if accuracy_trend else None
    latest_accuracy = accuracy_trend[-1]["y"] if accuracy_trend else None
    improvement_delta = None
    if initial_accuracy is not None and latest_accuracy is not None:
        improvement_delta = round(latest_accuracy - initial_accuracy, 4)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "feedback_events": len(feedback_events),
            "retrain_events": len(retrain_events),
            "current_dataset_entries": len(_load_json_list(DATASET_PATH)),
        },
        "rating_distribution": rating_distribution,
        "improvement": {
            "initial_feedback_accuracy": initial_accuracy,
            "latest_feedback_accuracy": latest_accuracy,
            "delta_feedback_accuracy": improvement_delta,
        },
        "graphs": {
            "accuracy_trend": accuracy_trend,
            "rating_trend": rating_trend,
            "dataset_growth": dataset_growth,
            "model_growth": model_growth,
            "retrain_quality": retrain_quality,
        },
    }


@app.get("/analytics/training-feedback/plot")
def training_feedback_plot() -> Response:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="matplotlib is required for graph rendering. Install requirements and restart API.",
        ) from exc

    analytics = training_feedback_analytics()
    graphs = analytics.get("graphs", {})

    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    axes = axes.flatten()

    chart_defs = [
        ("Accuracy Trend", "accuracy_trend", "Accuracy"),
        ("Rating Trend", "rating_trend", "Rating"),
        ("Dataset Growth", "dataset_growth", "Entries"),
        ("Model Feature Growth", "model_growth", "Feature Count"),
        ("Retrain Quality", "retrain_quality", "Score"),
    ]

    for idx, (title, key, y_label) in enumerate(chart_defs):
        ax = axes[idx]
        points = graphs.get(key, [])
        xs = list(range(1, len(points) + 1))
        ys = [float(p.get("y", 0.0) or 0.0) for p in points]
        if ys:
            ax.plot(xs, ys, marker="o", linewidth=2)
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(title)
        ax.set_xlabel("Event #")
        ax.set_ylabel(y_label)
        ax.grid(alpha=0.25)

    ax_dist = axes[5]
    dist = analytics.get("rating_distribution", {})
    labels = ["1", "2", "3", "4", "5"]
    values = [int(dist.get(k, 0) or 0) for k in labels]
    ax_dist.bar(labels, values)
    ax_dist.set_title("Rating Distribution")
    ax_dist.set_xlabel("Rating")
    ax_dist.set_ylabel("Count")
    ax_dist.grid(axis="y", alpha=0.25)

    fig.suptitle("Training & Feedback Analytics", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0.01, 1, 0.97])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/test", response_model=ExtractionWithTokenResponse)
async def test_endpoint(
    resume_file: UploadFile = File(...),
    preprocess: bool = Form(True),
    mode: str = Form("balanced"),
    pdf_dpi: int = Form(220),
) -> ExtractionWithTokenResponse:
    suffix = Path(resume_file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    if mode not in {"fast", "balanced", "resume_bert"}:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await resume_file.read())
        tmp_path = Path(tmp.name)

    try:
        raw_text = extract_raw_text(
            tmp_path,
            preprocess=preprocess,
            fast=(mode != "resume_bert"),
            pdf_dpi=pdf_dpi,
        )
        parsed = parse_resume_text(raw_text, mode=mode)
        parsed = _apply_feedback_memory(parsed, raw_text)
        parsed = _normalize_dob_fields(parsed)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    response_obj = ResumeExtractedResponse(**parsed)
    token_id = _register_session(response_obj.model_dump(), mode=mode)
    return ExtractionWithTokenResponse(token_id=token_id, extracted_data=response_obj)


@app.post("/auto-test-llm-colab", response_model=AutoTrainLLMResponse)
async def auto_test_llm_colab_endpoint(
    resume_file: UploadFile = File(...),
    preprocess: bool = Form(True),
    pdf_dpi: int = Form(220),
    mode: str = Form("balanced"),
    llm_base_model_id: str = Form("Qwen/Qwen2.5-3B-Instruct"),
    llm_adapter_path: str = Form("models/lora_adapter"),
    llm_max_new_tokens: int = Form(768),
    auto_train: bool = Form(True),
) -> AutoTrainLLMResponse:
    suffix = Path(resume_file.filename or "").suffix.lower()
    supported_types = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".docx", ".txt"}
    if suffix not in supported_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    if mode not in {"fast", "balanced", "resume_bert"}:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await resume_file.read())
        tmp_path = Path(tmp.name)

    raw_text = ""
    llm_error: str | None = None
    llm_debug: list[str] = [
        f"input_suffix={suffix}",
        f"mode={mode}",
        f"llm_base_model_id={llm_base_model_id}",
        f"llm_adapter_path={llm_adapter_path}",
        f"llm_max_new_tokens={llm_max_new_tokens}",
    ]
    llm_parsed = empty_llm_schema(raw_text="")

    try:
        raw_text = extract_raw_text(
            tmp_path,
            preprocess=preprocess,
            fast=(mode != "resume_bert"),
            pdf_dpi=pdf_dpi,
        )
        llm_debug.append(f"raw_text_len={len(raw_text)}")
        if raw_text:
            llm_parsed = run_lora_qlora_extraction(
                raw_text=raw_text,
                adapter_path=llm_adapter_path,
                base_model_id=llm_base_model_id,
                max_new_tokens=llm_max_new_tokens,
                debug_events=llm_debug,
            )
            llm_parsed = _normalize_dob_fields(llm_parsed)
        else:
            llm_error = "OCR returned empty text; skipped LLM extraction."
            llm_debug.append("skipped_llm_call_because_raw_text_is_empty")
    except Exception as exc:
        llm_error = str(exc)
        llm_debug.append(f"llm_exception={exc!r}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    llm_output = ResumeExtractedResponse(**llm_parsed)
    dataset = _load_json_list(DATASET_PATH)
    added_entries = 0
    trained = False
    model = train_mapping_model_from_dataset(dataset) if dataset else {}

    if llm_error is None and raw_text and auto_train:
        train_row = llm_output.model_dump()
        train_row["_feedback_weight"] = 1
        train_row["_auto_label_source"] = "auto_test_llm_colab_endpoint"
        train_row["_auto_label_created_at"] = datetime.now(timezone.utc).isoformat()
        dataset.append(train_row)
        _save_json_list(DATASET_PATH, dataset)
        added_entries = 1

        model = train_mapping_model_from_dataset(dataset)
        save_mapping_model(model, MODEL_PATH)
        trained = True

        events = _load_training_events()
        events["retrain_events"].append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "auto_test_llm_colab_endpoint",
                "added_entries": 1,
                "total_dataset_entries": len(dataset),
                "mapping_feature_count": sum(len(v) for v in model.values()),
                "check_average_overall_score": None,
            }
        )
        _save_training_events(events)

    token_id = _register_session(llm_output.model_dump(), mode=f"auto-test-llm-colab:{mode}")
    return AutoTrainLLMResponse(
        token_id=token_id,
        trained=trained,
        added_entries=added_entries,
        total_dataset_entries=len(dataset),
        dataset_path=str(DATASET_PATH),
        model_path=str(MODEL_PATH),
        mapping_counts={k: len(v) for k, v in model.items()},
        llm_output=llm_output,
        extracted_data=llm_output,
        rating=5,
        corrected_data=llm_output,
        retrain_on_submit=auto_train,
        llm_error=llm_error,
        llm_debug=llm_debug,
    )

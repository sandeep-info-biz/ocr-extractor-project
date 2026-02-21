import tempfile
import json
import io
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.evaluation import evaluate
from app.mapping_model import save_mapping_model, train_mapping_model_from_dataset
from app.ocr import extract_raw_text
from app.parser import parse_resume_text
from app.pretrained_resume_model import MODEL_REGISTRY
from app.schemas import (
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

DATASET_PATH = Path("data/resume_training_seed.json")
MODEL_PATH = Path("models/resume_mapping_model.json")
SESSION_STORE_PATH = Path("data/feedback_sessions.json")
FEEDBACK_LOG_PATH = Path("data/feedback_log.json")
TRAINING_EVENTS_PATH = Path("data/training_events.json")


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


def _rating_to_feedback_weight(rating: int) -> int:
    return {1: 1, 2: 1, 3: 2, 4: 3, 5: 4}.get(rating, 1)


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
def feedback_endpoint(payload: FeedbackRequest) -> FeedbackResponse:
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")

    session = _find_session(payload.token_id)
    if session is None:
        raise HTTPException(status_code=404, detail="token_id not found")

    submitted_at = datetime.now(timezone.utc).isoformat()
    corrected_data = payload.corrected_data.model_dump() if payload.corrected_data else None
    feedback_weight = _rating_to_feedback_weight(payload.rating)
    feedback_accuracy = float(payload.rating) / 5.0
    if corrected_data is not None:
        baseline_pred = session.get("extracted_data", {}) if isinstance(session.get("extracted_data"), dict) else {}
        feedback_accuracy = float(evaluate(baseline_pred, corrected_data).get("overall", 0.0))

    feedback_log = _load_json_list(FEEDBACK_LOG_PATH)
    feedback_log.append(
        {
            "token_id": payload.token_id,
            "rating": payload.rating,
            "feedback_weight": feedback_weight,
            "feedback_accuracy": round(feedback_accuracy, 4),
            "submitted_at": submitted_at,
            "corrected_data": corrected_data,
        }
    )
    _save_json_list(FEEDBACK_LOG_PATH, feedback_log)

    dataset = _load_json_list(DATASET_PATH)
    retrained = False
    if corrected_data is not None:
        train_row = dict(corrected_data)
        train_row["_feedback_rating"] = payload.rating
        train_row["_feedback_weight"] = feedback_weight
        train_row["_feedback_submitted_at"] = submitted_at
        dataset.append(train_row)
        _save_json_list(DATASET_PATH, dataset)

    model = train_mapping_model_from_dataset(dataset)
    if payload.retrain_on_submit:
        save_mapping_model(model, MODEL_PATH)
        retrained = True

    events = _load_training_events()
    events["feedback_events"].append(
        {
            "timestamp": submitted_at,
            "token_id": payload.token_id,
            "rating": payload.rating,
            "feedback_weight": feedback_weight,
            "feedback_accuracy": round(feedback_accuracy, 4),
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
                "added_entries": 1 if corrected_data is not None else 0,
                "total_dataset_entries": len(dataset),
                "mapping_feature_count": sum(len(v) for v in model.values()),
                "check_average_overall_score": round(feedback_accuracy, 4),
            }
        )
    _save_training_events(events)

    return FeedbackResponse(
        token_id=payload.token_id,
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
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".docx", ".txt"}:
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

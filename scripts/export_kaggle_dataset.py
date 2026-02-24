#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _ts_sort_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except Exception:
        return text


def _text_fingerprint(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip().lower()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def _stable_bucket(fingerprint: str) -> int:
    return int(hashlib.md5(fingerprint.encode("utf-8")).hexdigest()[:8], 16) % 100


def _split_name(bucket: int, train_pct: int, val_pct: int) -> str:
    if bucket < train_pct:
        return "train"
    if bucket < train_pct + val_pct:
        return "val"
    return "test"


def _session_raw_text_map(sessions: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in sessions:
        token_id = str(row.get("token_id", "")).strip()
        if not token_id:
            continue
        extracted = row.get("extracted_data", {})
        if isinstance(extracted, dict):
            raw_text = str(extracted.get("raw_text", "") or "")
            if raw_text:
                out[token_id] = raw_text
    return out


def _token_doc_map(async_docs: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc in async_docs:
        doc_id = str(doc.get("document_id", "") or "")
        entries = doc.get("entries", []) if isinstance(doc.get("entries"), list) else []
        for entry in entries:
            token_id = str(entry.get("token_id", "") or "")
            if token_id and doc_id:
                out[token_id] = doc_id
    return out


def _build_rows(
    feedback_log: list[dict],
    raw_text_by_token: dict[str, str],
    document_by_token: dict[str, str],
    min_rating: int,
) -> list[dict]:
    rows: list[dict] = []
    for item in feedback_log:
        token_id = str(item.get("token_id", "") or "").strip()
        if not token_id:
            continue

        try:
            rating = int(item.get("rating", 0) or 0)
        except Exception:
            rating = 0
        if rating < min_rating:
            continue

        corrected_data = item.get("corrected_data")
        if not isinstance(corrected_data, dict) or not corrected_data:
            continue

        raw_text = str(corrected_data.get("raw_text", "") or "").strip()
        if not raw_text:
            raw_text = str(raw_text_by_token.get(token_id, "") or "").strip()
        if not raw_text:
            continue

        label = dict(corrected_data)
        label.pop("raw_text", None)

        row = {
            "token_id": token_id,
            "document_id": str(item.get("document_id", "") or document_by_token.get(token_id, "") or ""),
            "user_id": str(item.get("user_id", "") or "").strip() or "unknown",
            "rating": rating,
            "timestamp": str(item.get("submitted_at", "") or ""),
            "raw_text": raw_text,
            "label": label,
            "feedback_accuracy": item.get("feedback_accuracy"),
            "feedback_weight": item.get("feedback_weight"),
        }
        row["text_fingerprint"] = _text_fingerprint(raw_text)
        rows.append(row)
    return rows


def _dedup_keep_latest(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        fp = row.get("text_fingerprint", "")
        if not fp:
            continue
        prev = latest.get(fp)
        if prev is None:
            latest[fp] = row
            continue
        if _ts_sort_key(row.get("timestamp")) >= _ts_sort_key(prev.get("timestamp")):
            latest[fp] = row
    return list(latest.values())


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Kaggle-ready dataset from feedback logs."
    )
    parser.add_argument("--feedback-log", default="data/feedback_log.json")
    parser.add_argument("--feedback-sessions", default="data/feedback_sessions.json")
    parser.add_argument("--async-documents", default="data/async_documents.json")
    parser.add_argument("--out-dir", default="data/kaggle_export")
    parser.add_argument("--min-rating", type=int, default=4)
    parser.add_argument("--train-pct", type=int, default=80)
    parser.add_argument("--val-pct", type=int, default=10)
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Do not deduplicate by raw_text fingerprint.",
    )
    args = parser.parse_args()

    if args.train_pct <= 0 or args.val_pct < 0 or (args.train_pct + args.val_pct) >= 100:
        raise SystemExit("Invalid split: require train_pct > 0, val_pct >= 0, and train_pct + val_pct < 100")
    if args.min_rating < 1 or args.min_rating > 5:
        raise SystemExit("min-rating must be between 1 and 5")

    feedback_log = _load_json(Path(args.feedback_log), [])
    feedback_sessions = _load_json(Path(args.feedback_sessions), [])
    async_documents = _load_json(Path(args.async_documents), [])

    if not isinstance(feedback_log, list):
        raise SystemExit("feedback-log must be a JSON list")
    if not isinstance(feedback_sessions, list):
        feedback_sessions = []
    if not isinstance(async_documents, list):
        async_documents = []

    raw_text_by_token = _session_raw_text_map(feedback_sessions)
    document_by_token = _token_doc_map(async_documents)
    rows = _build_rows(
        feedback_log=feedback_log,
        raw_text_by_token=raw_text_by_token,
        document_by_token=document_by_token,
        min_rating=args.min_rating,
    )

    total_before_dedup = len(rows)
    if not args.no_dedup:
        rows = _dedup_keep_latest(rows)

    rows.sort(key=lambda r: (_ts_sort_key(r.get("timestamp")), str(r.get("token_id", ""))))

    split_rows = {"train": [], "val": [], "test": []}
    for row in rows:
        fp = row.get("text_fingerprint", "")
        bucket = _stable_bucket(fp)
        split = _split_name(bucket, train_pct=args.train_pct, val_pct=args.val_pct)
        sample = {
            "sample_id": f"{split}-{fp[:12]}",
            "token_id": row.get("token_id", ""),
            "document_id": row.get("document_id", ""),
            "user_id": row.get("user_id", ""),
            "rating": row.get("rating", 0),
            "timestamp": row.get("timestamp", ""),
            "raw_text": row.get("raw_text", ""),
            "label": row.get("label", {}),
            "feedback_accuracy": row.get("feedback_accuracy"),
            "feedback_weight": row.get("feedback_weight"),
            "text_fingerprint": fp,
            "split": split,
        }
        split_rows[split].append(sample)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = split_rows["train"] + split_rows["val"] + split_rows["test"]
    _write_jsonl(out_dir / "kaggle_all.jsonl", all_rows)
    _write_jsonl(out_dir / "kaggle_train.jsonl", split_rows["train"])
    _write_jsonl(out_dir / "kaggle_val.jsonl", split_rows["val"])
    _write_jsonl(out_dir / "kaggle_test.jsonl", split_rows["test"])

    manifest = {
        "source": {
            "feedback_log": str(Path(args.feedback_log)),
            "feedback_sessions": str(Path(args.feedback_sessions)),
            "async_documents": str(Path(args.async_documents)),
        },
        "filters": {
            "min_rating": args.min_rating,
            "deduplicated": not args.no_dedup,
        },
        "split": {
            "train_pct": args.train_pct,
            "val_pct": args.val_pct,
            "test_pct": 100 - args.train_pct - args.val_pct,
        },
        "counts": {
            "total_candidates_before_dedup": total_before_dedup,
            "total_final": len(all_rows),
            "train": len(split_rows["train"]),
            "val": len(split_rows["val"]),
            "test": len(split_rows["test"]),
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Export complete: {out_dir}")


if __name__ == "__main__":
    main()

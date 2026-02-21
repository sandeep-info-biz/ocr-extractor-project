import argparse
import json
from pathlib import Path

from app.evaluation import evaluate
from app.ocr import extract_raw_text
from app.parser import parse_resume_text


def run_extract(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw = extract_raw_text(
        input_path,
        preprocess=not args.no_preprocess,
        fast=(args.mode != "resume_bert"),
        pdf_dpi=args.pdf_dpi,
    )
    parsed = parse_resume_text(raw, mode=args.mode)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved parsed output: {out_path}")

    if args.ground_truth:
        gt_path = Path(args.ground_truth)
        truth = json.loads(gt_path.read_text(encoding="utf-8"))
        scores = evaluate(parsed, truth)
        print("Evaluation scores:")
        for k, v in scores.items():
            print(f"  {k}: {v:.4f}")
        if scores["overall"] >= 0.95:
            print("Target reached: overall >= 95%")
        else:
            print("Target not reached yet: tune patterns/model/data for >=95%")


def run_api(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resume OCR + spaCy extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Extract resume fields from a file")
    extract.add_argument("--input", required=True, help="Path to resume file (.pdf/.png/.jpg/.docx/.txt)")
    extract.add_argument("--output", default="outputs/resume_extracted.json", help="Output JSON file path")
    extract.add_argument("--no-preprocess", action="store_true", help="Disable OCR image preprocessing")
    extract.add_argument("--mode", default="balanced", choices=["fast", "balanced", "resume_bert"])
    extract.add_argument("--pdf-dpi", type=int, default=220, help="PDF OCR DPI (lower is faster)")
    extract.add_argument("--ground-truth", help="Path to JSON file for evaluation")
    extract.set_defaults(func=run_extract)

    api = subparsers.add_parser("api", help="Run FastAPI server")
    api.add_argument("--host", default="127.0.0.1", help="Host to bind")
    api.add_argument("--port", type=int, default=8000, help="Port to bind")
    api.add_argument("--reload", action="store_true", help="Enable auto-reload")
    api.set_defaults(func=run_api)

    return parser


def run_cli() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    run_cli()


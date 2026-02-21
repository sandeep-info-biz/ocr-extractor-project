import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mapping_model import save_mapping_model, train_mapping_model_from_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Train mapping model from structured resume dataset JSON.")
    parser.add_argument("--dataset", default="data/resume_training_seed.json", help="Path to dataset JSON file")
    parser.add_argument("--output", default="models/resume_mapping_model.json", help="Path to output model JSON")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(dataset, list):
        raise ValueError("Dataset JSON must be a list of resume objects.")

    model = train_mapping_model_from_dataset(dataset)
    out_path = save_mapping_model(model, Path(args.output))
    counts = {k: len(v) for k, v in model.items()}
    print(f"Saved mapping model: {out_path}")
    print(f"Counts: {counts}")


if __name__ == "__main__":
    main()

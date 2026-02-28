from pathlib import Path
from typing import Dict, List


def train_spacy_ner(
    train_data: List[Dict[str, object]],
    output_dir: str = "models/resume_ner",
    base_model: str = "en_core_web_sm",
    n_iter: int = 20,
    dropout: float = 0.2,
) -> Dict[str, object]:
    import random

    try:
        import spacy
    except Exception as exc:
        raise RuntimeError(
            "spaCy is unavailable in this Python environment. "
            "Use Python 3.10-3.13 (recommended 3.11) to enable training."
        ) from exc
    from spacy.training import Example
    from spacy.util import minibatch

    if train_data is None or len(train_data) == 0:
        raise ValueError("train_data must contain at least one sample.")

    try:
        nlp = spacy.load(base_model)
        loaded = base_model
    except Exception:
        nlp = spacy.blank("en")
        loaded = "blank_en"

    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner")
    else:
        ner = nlp.get_pipe("ner")

    examples = []
    for row in train_data:
        text = str(row.get("text", ""))
        entities = row.get("entities", [])
        offsets = []
        for ent in entities:
            offsets.append((int(ent["start"]), int(ent["end"]), str(ent["label"])))
            ner.add_label(str(ent["label"]))
        doc = nlp.make_doc(text)
        examples.append(Example.from_dict(doc, {"entities": offsets}))

    other_pipes = [p for p in nlp.pipe_names if p != "ner"]
    losses = {}
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.initialize(get_examples=lambda: examples)
        for _ in range(n_iter):
            random.shuffle(examples)
            batches = minibatch(examples, size=8)
            for batch in batches:
                nlp.update(batch, sgd=optimizer, drop=dropout, losses=losses)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(out_dir)
    return {
        "saved_model_path": str(out_dir),
        "base_model_used": loaded,
        "iterations": n_iter,
        "dropout": dropout,
        "final_losses": losses,
        "samples_trained": len(train_data),
    }

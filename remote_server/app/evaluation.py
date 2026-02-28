import re
from typing import Dict


def token_f1(pred: str, truth: str) -> float:
    pred_toks = set(re.findall(r"\w+", pred.lower()))
    truth_toks = set(re.findall(r"\w+", truth.lower()))
    if not pred_toks and not truth_toks:
        return 1.0
    if not pred_toks or not truth_toks:
        return 0.0
    tp = len(pred_toks & truth_toks)
    precision = tp / len(pred_toks) if pred_toks else 0.0
    recall = tp / len(truth_toks) if truth_toks else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate(pred_json: Dict[str, object], truth_json: Dict[str, object]) -> Dict[str, float]:
    scores = {}

    pred_name = f"{pred_json.get('first_name', '')} {pred_json.get('last_name', '')}".strip()
    truth_name = f"{truth_json.get('first_name', '')} {truth_json.get('last_name', '')}".strip()
    scores["name"] = token_f1(pred_name, truth_name)
    scores["skills"] = token_f1(str(pred_json.get("skills", "")), str(truth_json.get("skills", "")))
    scores["education"] = token_f1(str(pred_json.get("education", "")), str(truth_json.get("education", "")))
    scores["designation_or_position"] = token_f1(
        str(pred_json.get("designation_or_position", "")),
        str(truth_json.get("designation_or_position", "")),
    )
    scores["about_description_summary"] = token_f1(
        str(pred_json.get("about_description_summary", "")),
        str(truth_json.get("about_description_summary", "")),
    )
    scores["overall"] = sum(scores.values()) / len(scores)
    return scores

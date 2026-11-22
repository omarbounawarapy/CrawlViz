"""Scores the judge against human labels for the audit area of the benchmark routes."""

import json
from pathlib import Path
from typing import Any

from benchmark import audit as audit_mod

from .benchmark_json import nan_to_none


def labels_of(path: Path) -> dict[str, int]:
    return audit_mod.read_labels(path) if path.is_file() else {}


def audit_result(
    key_path: Path, tsv: Path, total: int | None = None, other: Path | None = None
) -> dict[str, Any] | None:
    key = json.loads(key_path.read_text())
    human = labels_of(tsv)
    ids = sorted((i for i in human if i in key["items"]), key=int)
    if not ids:
        return None
    pairs = [(key["items"][i]["judge_label"], human[i]) for i in ids]
    bp = audit_mod.binary(pairs)
    counts = {int(g): n for g, n in key["graph_label_counts"].items()}
    prec, rec = audit_mod.per_class(bp, (1,))[1]
    return {
        "n": len(pairs),
        "sampled": total or len(key["items"]),
        "confusion": audit_mod.confusion(pairs, (0, 1, 2)),
        "confusion_binary": audit_mod.confusion(bp, (0, 1)),
        "agreement": nan_to_none(audit_mod.agreement(pairs)),
        "kappa": nan_to_none(audit_mod.kappa(pairs)),
        "agreement_binary": nan_to_none(audit_mod.agreement(bp)),
        "kappa_binary": nan_to_none(audit_mod.kappa(bp)),
        "kappa_ci": [nan_to_none(v) for v in audit_mod.bootstrap_ci(pairs, audit_mod.kappa)],
        "relevant_precision": nan_to_none(prec),
        "relevant_recall": nan_to_none(rec),
        "reweighted": nan_to_none(audit_mod.reweighted_agreement(pairs, counts)[0]),
        "human_vs_annotator1": human_pair(human, other),
    }


def human_pair(human: dict[str, int], other: Path | None) -> dict[str, Any] | None:
    """Annotator 2 against annotator 1 on the ids both labelled ."""
    first = labels_of(other) if other else {}
    both = sorted(set(human) & set(first), key=int)
    if not both:
        return None
    pairs = [(first[i], human[i]) for i in both]
    return {
        "n": len(pairs),
        "agreement": nan_to_none(audit_mod.agreement(pairs)),
        "kappa": nan_to_none(audit_mod.kappa(pairs)),
        "agreement_binary": nan_to_none(audit_mod.agreement(audit_mod.binary(pairs))),
        "kappa_binary": nan_to_none(audit_mod.kappa(audit_mod.binary(pairs))),
    }

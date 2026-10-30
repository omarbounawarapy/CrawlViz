"""Reads the experiment protocol (``benchmark/PROTOCOL.md``) into the shape the UI shows."""

import re
from pathlib import Path
from typing import Any

# The result is JSON for the UI, so values are plain dicts and lists.
Protocol = dict[str, Any]


def _section(text: str, number: str) -> str:
    """The body of '## <number>. ...' up to the next '## ' heading."""
    m = re.search(rf"^## {re.escape(number)}\.? .*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def _cells(line: str) -> list[str]:
    return [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]


def read_protocol(protocol_file: Path) -> Protocol:
    """Hypotheses, arms, budgets, models and amendments, read from PROTOCOL.md itself."""
    if not protocol_file.is_file():
        return {
            "hypotheses": [],
            "arms": [],
            "budgets": [],
            "models": [],
            "primary_metric": "",
            "amendments": [],
        }
    text = protocol_file.read_text()
    hypotheses = []
    for line in _section(text, "1").splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) >= 3 and re.fullmatch(r"H\d", c[0]):
            hypotheses.append({"id": c[0], "text": c[1], "comparison": c[2]})
    arms = []
    sec5 = _section(text, "5")
    for line in sec5.splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) >= 4 and re.match(r"\d+", c[1]):
            arms.append({"arm": c[0], "repeats": c[1], "scopes": c[2], "llm": c[3]})
    budget_line = re.search(r"Budgets[^:]*:\s*([^.]*)\.", sec5)
    budgets = [int(b) for b in re.findall(r"\d+", budget_line.group(1) if budget_line else "")]
    models = []
    for line in _section(text, "6").splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) == 3 and c[0] not in ("Role", "") and not set(c[0]) <= set("-"):
            models.append({"role": c[0], "provider": c[1], "model": c[2]})
    metric = re.search(r"^harvest@30[^\n]*(?:\n[^\n]+)*", _section(text, "2").strip(), re.M)
    tail = text.split("\n## Amendments", 1)[1] if "\n## Amendments" in text else ""
    parts = re.split(r"^\*\*(\d{4}-\d{2}-\d{2}[^*]*)\*\*", tail, flags=re.M)
    amendments = [
        {"title": parts[k].strip().rstrip("."), "body": parts[k + 1].strip().replace("`", "")}
        for k in range(1, len(parts) - 1, 2)
    ]
    return {
        "hypotheses": hypotheses,
        "arms": arms,
        "budgets": budgets,
        "models": models,
        "primary_metric": " ".join(metric.group(0).split()).replace("`", "") if metric else "",
        "amendments": amendments,
    }

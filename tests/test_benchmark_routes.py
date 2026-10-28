"""The benchmark routes read experiment files, annotate the audit and whitelist CLI flags."""
import csv
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routes import benchmark as bm
from routes import benchmark_jobs as jobs


@pytest.fixture
def client(tmp_path, monkeypatch):
    data, results = tmp_path / "data", tmp_path / "results"
    data.mkdir()
    results.mkdir()
    monkeypatch.setattr(bm, "DATA_DIR", data)
    monkeypatch.setattr(bm, "RESULTS_DIR", results)
    bm._graph_cache.clear()
    (data / "g.json").write_text(json.dumps({
        "seed": "A", "topic": "t",
        "pages": {
            "A": {"title": "A", "label": 0, "links": [{"to": "B", "anchor": "b"}]},
            "B": {"title": "B", "label": 1, "links": []},
        },
    }))
    for i, labels in enumerate([[1, 0, 1], [0, 1, 1]]):
        (results / f"g.json__bfs__rep{i}.json").write_text(json.dumps({
            "format": 1, "graph": "g.json", "policy": "bfs", "rep": i, "budget": 3,
            "sequence": ["A", "B", "C"], "labels": labels, "valid": True, "status": "completed",
        }))
    with (data / "audit.tsv").open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "title", "excerpt", "human_label"])
        w.writerow(["1", "A", "text a", ""])
        w.writerow(["2", "B", "text b", ""])
    (data / "audit_key.json").write_text(json.dumps({
        "graph_label_counts": {"0": 1, "1": 1, "2": 0},
        "items": {"1": {"page": "A", "judge_label": 0}, "2": {"page": "B", "judge_label": 1}},
    }))
    app = FastAPI()
    app.include_router(bm.router)
    return TestClient(app)


def test_runs_and_curves(client):
    runs = client.get("/benchmark/runs").json()
    assert [r["found"] for r in runs] == [2, 2]
    series = client.get("/benchmark/curves").json()["series"]["bfs"]
    assert series["runs"] == 2 and series["points"][0]["k"] == 1


def test_graph_subgraph_has_labels_and_edges(client):
    g = client.get("/benchmark/graph?name=g.json&max_depth=1").json()
    assert {n["id"]: n["label"] for n in g["nodes"]} == {"A": 0, "B": 1}
    assert {n["id"]: n["parent"] for n in g["nodes"]} == {"A": None, "B": "A"}
    assert g["cross_links"] == 0


def test_audit_is_blind_and_annotation_persists(client, tmp_path):
    items = client.get("/benchmark/audit").json()["items"]
    assert all("judge_label" not in i for i in items)
    assert client.put("/benchmark/audit/1?annotator=1", json={"human_label": 0}).status_code == 200
    assert client.put("/benchmark/audit/2?annotator=1", json={"human_label": 1}).json()["done"] == 2
    score = client.post("/benchmark/audit/score").json()
    assert score["n"] == 2 and score["agreement"] == 1.0
    assert client.put("/benchmark/audit/2?annotator=1", json={"human_label": 3}).status_code == 422
    assert client.put("/benchmark/audit/9?annotator=1", json={"human_label": 1}).status_code == 404
    assert not (tmp_path / "data" / "audit_filled.tsv").exists()


def test_job_flags_are_whitelisted():
    cmd = jobs.build_command("run", {"graph": "benchmark/data/isi.json", "budget": 50, "cascade": True})
    assert "--cascade" in cmd and cmd[cmd.index("--budget") + 1] == "50"
    for kind, args in [("run", {"rm": 1}), ("run", {"graph": "../x.json"}),
                       ("run", {"model": "a; ls"}), ("shell", {})]:
        with pytest.raises(HTTPException):
            jobs.build_command(kind, args)


def test_second_annotator_labels_only_the_first_items(client, monkeypatch):
    monkeypatch.setattr(bm, "SECOND_ANNOTATOR_ITEMS", 1)
    assert [i["id"] for i in client.get("/benchmark/audit?annotator=2").json()["items"]] == ["1"]
    assert client.put("/benchmark/audit/2?annotator=2", json={"human_label": 1}).status_code == 404
    client.put("/benchmark/audit/1?annotator=1", json={"human_label": 0})
    client.put("/benchmark/audit/1?annotator=2", json={"human_label": 0})
    score = client.post("/benchmark/audit/score?annotator=2").json()
    assert score["sampled"] == 1 and score["human_vs_annotator1"]["agreement"] == 1.0


def test_protocol_is_read_from_the_file(client, tmp_path, monkeypatch):
    md = tmp_path / "PROTOCOL.md"
    md.write_text(
        "## 1. Question\n\n| | Hypothesis | Comparison |\n|---|---|---|\n"
        "| H1 | A beats B. | `a` vs `b` |\n\n## 5. Arms\n\nBudgets (fetched pages, seed included): 50, 100.\n\n"
        "| Arm | Repeats | Seeds | LLM |\n|---|---|---|---|\n| `cascade` | 10 | rep | yes |\n\n"
        "## Amendments\n\n**2026-01-01, a change.** Body text.\n")
    monkeypatch.setattr(bm, "PROTOCOL_FILE", md)
    p = client.get("/benchmark/overview").json()["protocol"]
    assert p["hypotheses"][0]["text"] == "A beats B."
    assert p["budgets"] == [50, 100] and p["arms"][0]["arm"] == "cascade"
    assert p["amendments"][0]["title"].startswith("2026-01-01") and p["amendments"][0]["body"] == "Body text."


def test_estimate_comes_from_recorded_runs(client):
    assert client.get("/benchmark/estimate").json()["arms"] == {}
    (bm.RESULTS_DIR / "c.json").write_text(json.dumps({
        "format": 1, "graph": "g.json", "policy": "cascade", "rep": 0, "budget": 4,
        "sequence": ["A", "B"], "labels": [0, 1], "valid": True, "status": "completed",
        "input_tokens": 600, "output_tokens": 400,
    }))
    arm = client.get("/benchmark/estimate?budget=50").json()["arms"]["cascade"]
    assert arm["tokens_per_page"] == 500 and arm["tokens_for_budget"] == 25000


def test_expected_results_counts_baselines_and_the_arm():
    from benchmark import POLICIES

    assert jobs.expected_results("run", {"reps": 2}) == len(POLICIES) * 2
    assert jobs.expected_results("run", {"reps": 2, "cascade": True}) == len(POLICIES) * 2 + 2
    assert jobs.expected_results("analyze", {}) is None

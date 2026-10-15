"""Blind audit of the judge's labels: a human relabels a stratified sample.

    .venv/bin/python -m benchmark.audit sample --graph benchmark/data/ball.json \\
        --out benchmark/data/audit.tsv --key benchmark/data/audit_key.json
    # fill the human_label column (0, 1 or 2) without opening the key file
    .venv/bin/python -m benchmark.audit score --tsv benchmark/data/audit.tsv \\
        --key benchmark/data/audit_key.json [--tsv2 second_annotator.tsv]

``form`` turns the sample TSV into a self-contained HTML checklist to fill in
a browser (answers are kept in the browser and exported as the filled TSV).
It carries only what the TSV carries, so the form is as blind as the TSV.

``sample`` draws every label-2 page plus label-1, label-0 (weighted toward
pages that mention Tunisia) and uniformly random pages, minus the pages of the
pilot files, and writes a shuffled TSV that carries only id, title, excerpt and
an empty human_label. The stratum and the judge's label go to a separate key
file that the annotator must not read.

``score`` compares the filled TSV with the judge: confusion matrices (3-class
and binary, label >= 1), per-class precision and recall (the judge is the
prediction, the human the truth), raw agreement and Cohen's kappa with
bootstrap 95% CIs, and raw agreement reweighted to the label distribution of
the whole graph. A second annotator file adds human-human kappa.
"""
import argparse
import csv
import json
import random
import hashlib
import html
from collections import Counter
from pathlib import Path

from .graph import FrozenGraph, page_key

EXCERPT_CHARS = 450
PILOT_FILES = ("benchmark/data/pilot30.tsv", "benchmark/data/pilot_label2.tsv")
# Shares of the sample that is not label 2: label 1, label 0, uniform (60 : 60 : 30).
SHARES = {"label1": 0.4, "label0": 0.4, "uniform": 0.2}
DEFAULT_REST = 150
TUNISIA_WEIGHT = 5.0
BOOTSTRAPS = 1000


def excluded_pages(files) -> set[str]:
    out: set[str] = set()
    for f in files:
        path = Path(f)
        if path.exists():
            with path.open(newline="") as fh:
                out |= {page_key(r["page"]) for r in csv.DictReader(fh, delimiter="\t") if r.get("page")}
    return out


def mentions_tunisia(page: dict) -> bool:
    return "tunisi" in f'{page.get("title", "")} {page.get("text", "")}'.lower()


def weighted_sample(names: list[str], weights: dict[str, float], k: int, rng: random.Random) -> list[str]:
    """k names without replacement, chosen with probability proportional to weight."""
    keyed = sorted(names, key=lambda n: rng.random() ** (1 / weights[n]), reverse=True)
    return keyed[:k]


def draw(graph: FrozenGraph, total: int | None, seed: int, exclude: set[str]) -> list[tuple[str, str]]:
    """(page, stratum) pairs: all label 2, then label 1, label 0, uniform."""
    rng = random.Random(f"audit:{seed}")
    pool = sorted(n for n in graph.pages if n not in exclude and "text" in graph.pages[n])
    by_label = {g: [n for n in pool if graph.label(n) == g] for g in (0, 1, 2)}
    chosen = [(n, "label2") for n in by_label[2]]
    rest = (total - len(chosen)) if total is not None else DEFAULT_REST
    if rest < 0:
        raise SystemExit(f"--total {total} is below the {len(chosen)} label-2 pages, which are all included")
    n1, n0 = round(rest * SHARES["label1"]), round(rest * SHARES["label0"])
    n_uniform = rest - n1 - n0
    picked = set(by_label[2])
    one = rng.sample(by_label[1], min(n1, len(by_label[1])))
    picked |= set(one)
    weights = {n: TUNISIA_WEIGHT if mentions_tunisia(graph.pages[n]) else 1.0 for n in by_label[0]}
    zero = weighted_sample(by_label[0], weights, min(n0, len(by_label[0])), rng)
    picked |= set(zero)
    others = [n for n in pool if n not in picked]
    uniform = rng.sample(others, min(n_uniform, len(others)))
    return chosen + [(n, "label1") for n in one] + [(n, "label0") for n in zero] + [(n, "uniform") for n in uniform]


def sample(graph_path: Path, out: Path, key: Path, total: int | None, seed: int, exclude_files) -> None:
    graph = FrozenGraph.load(graph_path)
    unlabelled = sum(1 for p in graph.pages.values() if p.get("label") is None)
    if unlabelled:
        raise SystemExit(f"{graph_path}: {unlabelled} of {len(graph.pages)} pages have no judge label; "
                         "finish benchmark.label_graph and --merge before sampling")
    exclude = excluded_pages(exclude_files)
    picks = draw(graph, total, seed, exclude)
    random.Random(f"audit-order:{seed}").shuffle(picks)
    out.parent.mkdir(parents=True, exist_ok=True)
    items = {}
    with out.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "title", "excerpt", "human_label"])
        for i, (name, stratum) in enumerate(picks, 1):
            page = graph.pages[name]
            w.writerow([i, page["title"], page["text"][:EXCERPT_CHARS].replace("\n", " ").replace("\t", " "), ""])
            items[str(i)] = {"page": name, "stratum": stratum, "judge_label": graph.label(name)}
    counts = Counter(graph.label(n) for n in graph.pages)
    key.write_text(json.dumps({
        "graph": graph_path.name,
        "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
        "seed": seed,
        "graph_label_counts": {str(g): counts.get(g, 0) for g in (0, 1, 2)},
        "items": items,
    }, ensure_ascii=False, indent=1))
    by = Counter(s for _, s in picks)
    print(f"{len(picks)} pages ({', '.join(f'{s} {c}' for s, c in by.items())}); "
          f"{len(exclude)} pilot pages excluded; wrote {out} and {key}")


# ---- scoring ---------------------------------------------------------------

def read_labels(path: Path) -> dict[str, int]:
    out = {}
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            v = (row.get("human_label") or "").strip()
            if v:
                if v not in ("0", "1", "2"):
                    raise SystemExit(f"{path}: id {row['id']}: human_label must be 0, 1 or 2, got {v!r}")
                out[row["id"]] = int(v)
    return out


def confusion(pairs: list[tuple[int, int]], classes) -> list[list[int]]:
    """Rows: first element of each pair; columns: second."""
    return [[sum(1 for a, b in pairs if a == r and b == c) for c in classes] for r in classes]


def agreement(pairs) -> float:
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else float("nan")


def kappa(pairs) -> float:
    """Cohen's kappa; 1.0 when both raters use one class throughout."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = agreement(pairs)
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in ca.keys() | cb.keys()) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def bootstrap_ci(pairs, stat, seed: int = 0, n: int = BOOTSTRAPS) -> tuple[float, float]:
    rng = random.Random(f"audit-boot:{seed}")
    vals = sorted(stat([rng.choice(pairs) for _ in pairs]) for _ in range(n))
    vals = [v for v in vals if v == v]
    if not vals:
        return float("nan"), float("nan")
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def per_class(pairs, classes) -> dict[int, tuple[float, float]]:
    """class -> (precision, recall) of the judge (first) against the human (second)."""
    out = {}
    for c in classes:
        tp = sum(1 for j, h in pairs if j == c and h == c)
        pj, ph = sum(1 for j, _ in pairs if j == c), sum(1 for _, h in pairs if h == c)
        out[c] = (tp / pj if pj else float("nan"), tp / ph if ph else float("nan"))
    return out


def reweighted_agreement(pairs, label_counts: dict[int, int]) -> tuple[float, list[int]]:
    """Agreement within each judge class, weighted by that class's share of the
    graph. Classes with no sampled page are left out and the rest renormalized;
    they are returned."""
    total = weight = 0.0
    missing = []
    for c, n in label_counts.items():
        sub = [(j, h) for j, h in pairs if j == c]
        if not sub:
            if n:
                missing.append(c)
            continue
        total += n * agreement(sub)
        weight += n
    return (total / weight if weight else float("nan")), missing


def binary(pairs):
    return [(int(a >= 1), int(b >= 1)) for a, b in pairs]


def _fmt(matrix, classes, row_name, col_name) -> str:
    head = f"{row_name}\\{col_name}".ljust(14) + "".join(f"{c:>6}" for c in classes) + f"{'total':>7}"
    rows = [f"{c:>14}" + "".join(f"{v:>6}" for v in r) + f"{sum(r):>7}" for c, r in zip(classes, matrix)]
    return "\n".join([head] + rows)


def _ci(lo_hi) -> str:
    return f"[{lo_hi[0]:.3f}, {lo_hi[1]:.3f}]"


def report(pairs, label_counts, row_name="judge", col_name="human", reweight=True) -> None:
    classes = (0, 1, 2)
    print(f"n = {len(pairs)}")
    print("\n3-class confusion matrix")
    print(_fmt(confusion(pairs, classes), classes, row_name, col_name))
    bp = binary(pairs)
    print("\nbinary confusion matrix (label >= 1 is relevant)")
    print(_fmt(confusion(bp, (0, 1)), (0, 1), row_name, col_name))
    print(f"\nper-class ({row_name} as prediction, {col_name} as truth)")
    print(f"{'class':>7}{'precision':>11}{'recall':>9}")
    for c, (p, r) in per_class(pairs, classes).items():
        print(f"{c:>7}{p:>11.3f}{r:>9.3f}")
    bpc = per_class(bp, (1,))[1]
    print(f"{'rel':>7}{bpc[0]:>11.3f}{bpc[1]:>9.3f}   (binary: label >= 1)")
    print()
    for name, ps in (("3-class", pairs), ("binary", bp)):
        print(f"{name:>8}  agreement {agreement(ps):.3f} {_ci(bootstrap_ci(ps, agreement))}"
              f"   kappa {kappa(ps):.3f} {_ci(bootstrap_ci(ps, kappa))}   (95% bootstrap, {BOOTSTRAPS} resamples)")
    if reweight:
        rw, missing = reweighted_agreement(pairs, label_counts)
        rw_b, _ = reweighted_agreement(
            bp, {0: label_counts.get(0, 0), 1: label_counts.get(1, 0) + label_counts.get(2, 0)}
        )
        print(f"\nagreement reweighted to the graph's label distribution {label_counts}: "
              f"3-class {rw:.3f}, binary {rw_b:.3f}")
        if missing:
            print(f"  no sampled page with judge label {missing}; those classes are left out")


def score(tsv: Path, key: Path, tsv2: Path | None = None) -> None:
    k = json.loads(Path(key).read_text())
    human = read_labels(tsv)
    unknown = set(human) - set(k["items"])
    if unknown:
        raise SystemExit(f"{len(unknown)} ids in {tsv} are not in the key file")
    unlabelled = len(k["items"]) - len(human)
    if unlabelled:
        print(f"{unlabelled} of {len(k['items'])} sampled pages have no human_label and are left out\n")
    counts = {int(g): n for g, n in k["graph_label_counts"].items()}
    ids = sorted(human, key=int)
    pairs = [(k["items"][i]["judge_label"], human[i]) for i in ids]
    print(f"== judge vs annotator 1 ({tsv.name}) ==")
    report(pairs, counts)
    if tsv2:
        h2 = read_labels(tsv2)
        both = [i for i in ids if i in h2]
        print(f"\n== judge vs annotator 2 ({tsv2.name}) ==")
        report([(k["items"][i]["judge_label"], h2[i]) for i in both], counts)
        hh = [(human[i], h2[i]) for i in both]
        print(f"\n== annotator 1 vs annotator 2 (n = {len(hh)}) ==")
        report(hh, counts, "annot1", "annot2", reweight=False)


FORM = r"""<!doctype html>
<html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1c1c1c;--mut:#666;--line:#d9d9d9;--panel:#f4f4f1;--ok:#e7f4e7;--cur:#fff6d6;--acc:#1a56b0}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e8e8e8;--mut:#9a9a9a;--line:#333;--panel:#212121;--ok:#1d2f1d;--cur:#3a3416;--acc:#7fb0ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:2px solid var(--line);padding:10px 16px;z-index:2}
header p{margin:2px 0;max-width:62rem}
.bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:6px}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;cursor:pointer}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
main{max-width:62rem;margin:0 auto;padding:8px 16px 80px}
.item{border-bottom:1px solid var(--line);padding:12px 8px;display:grid;grid-template-columns:3rem 1fr;gap:4px 8px}
.item.done{background:var(--ok)}.item.cur{outline:2px solid var(--acc);background:var(--cur)}
.n{color:var(--mut);font-variant-numeric:tabular-nums}
.t{font-weight:600}.x{color:var(--mut);font-size:.92em;margin-top:2px}
fieldset{border:0;margin:8px 0 0;padding:0;display:flex;gap:10px;grid-column:2}
fieldset label{border:1px solid var(--line);border-radius:6px;padding:6px 18px;cursor:pointer;font-size:1.1em}
fieldset input{margin-right:6px}
fieldset label:has(input:checked){background:var(--acc);color:#fff;border-color:var(--acc)}
small{color:var(--mut)}
</style>
<header>
<p><b>2</b> = the ISI Ariana itself (or a page devoted to its own programmes, departments or buildings).</p>
<p><b>1</b> = a degree-granting higher-education institution in Tunisia (including foreign campuses and sibling institutes), or the Tunisian system, its ministry, or a list of institutions. Not the target itself.</p>
<p><b>0</b> = everything else. If the excerpt does not make Tunisia clear, 0. People, events and concepts are 0.</p>
<div class="bar"><span id="cnt"></span>
<button id="next">Next unanswered</button><button id="exp" class="primary">Export TSV</button>
<label><input type="checkbox" id="only"> unanswered only</label>
<small>Keys: 0 / 1 / 2 answer and move on, ↑ ↓ move, Backspace clears.</small></div>
</header>
<main id="list"></main>
<script>
const ITEMS = __ITEMS__;
const KEY = "audit-form:" + __KEY__;
let ans = {}; try { ans = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const list = document.getElementById("list");
let cur = 0;
function save() { try { localStorage.setItem(KEY, JSON.stringify(ans)); } catch (e) {} }
function render() {
  list.innerHTML = "";
  ITEMS.forEach((it, i) => {
    const d = document.createElement("div");
    d.className = "item" + (ans[it.id] !== undefined ? " done" : "") + (i === cur ? " cur" : "");
    d.id = "i" + i; d.dataset.i = i;
    d.innerHTML = '<div class="n">' + it.id + '</div><div><div class="t"></div><div class="x"></div></div>';
    d.querySelector(".t").textContent = it.title;
    d.querySelector(".x").textContent = it.excerpt;
    const f = document.createElement("fieldset");
    [0, 1, 2].forEach(v => {
      const l = document.createElement("label");
      const r = document.createElement("input");
      r.type = "radio"; r.name = "q" + it.id; r.value = v; r.checked = ans[it.id] === v;
      r.onchange = () => { ans[it.id] = v; save(); cur = i; refresh(); };
      l.append(r, String(v)); f.append(l);
    });
    d.append(f);
    d.onclick = () => { cur = i; mark(); };
    list.append(d);
  });
  refresh();
}
function refresh() {
  const n = Object.keys(ans).length;
  document.getElementById("cnt").textContent = n + " / " + ITEMS.length + " answered";
  const only = document.getElementById("only").checked;
  ITEMS.forEach((it, i) => {
    const d = document.getElementById("i" + i);
    d.classList.toggle("done", ans[it.id] !== undefined);
    d.hidden = only && ans[it.id] !== undefined && i !== cur;
  });
  mark();
}
function mark() {
  document.querySelectorAll(".item").forEach((d, i) => d.classList.toggle("cur", i === cur));
  const d = document.getElementById("i" + cur);
  if (d) d.scrollIntoView({block: "center"});
}
function nextOpen(from) {
  for (let k = 1; k <= ITEMS.length; k++) {
    const j = (from + k) % ITEMS.length;
    if (ans[ITEMS[j].id] === undefined) return j;
  }
  return from;
}
document.getElementById("next").onclick = () => { cur = nextOpen(cur); mark(); };
document.getElementById("only").onchange = refresh;
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" && e.target.type === "checkbox") return;
  const id = ITEMS[cur].id;
  if (["0", "1", "2"].includes(e.key)) { ans[id] = +e.key; save(); cur = nextOpen(cur); render(); }
  else if (e.key === "Backspace") { delete ans[id]; save(); render(); e.preventDefault(); }
  else if (e.key === "ArrowDown") { cur = Math.min(cur + 1, ITEMS.length - 1); mark(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { cur = Math.max(cur - 1, 0); mark(); e.preventDefault(); }
});
document.getElementById("exp").onclick = () => {
  const missing = ITEMS.filter(it => ans[it.id] === undefined).length;
  if (missing && !confirm(missing + " items are unanswered and will be exported empty. Export anyway?")) return;
  const clean = s => s.replace(/[\t\r\n]+/g, " ");
  const rows = ["id\ttitle\texcerpt\thuman_label"].concat(ITEMS.map(it =>
    [it.id, clean(it.title), clean(it.excerpt), ans[it.id] === undefined ? "" : ans[it.id]].join("\t")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.join("\n") + "\n"], {type: "text/tab-separated-values"}));
  a.download = __OUT__; a.click();
};
render();
</script></html>
"""


def form(tsv: Path, out: Path, limit: int | None = None, name: str = "audit_filled.tsv") -> None:
    """Write the HTML checklist for ``tsv`` (its first ``limit`` rows)."""
    import json as _json

    with Path(tsv).open(newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if limit:
        rows = rows[:limit]
    items = [{"id": r["id"], "title": r["title"], "excerpt": r["excerpt"]} for r in rows]
    # No "<" survives, so neither "</script>" nor "<!--" can occur in page text.
    data = _json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    page = (FORM.replace("__TITLE__", html.escape(f"Audit: {len(items)} pages"))
            .replace("__ITEMS__", data).replace("__KEY__", _json.dumps(Path(tsv).name + f":{limit or 'all'}"))
            .replace("__OUT__", _json.dumps(name)))
    Path(out).write_text(page)
    print(f"wrote {out} ({len(items)} pages); answers export as {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="draw the stratified sample")
    s.add_argument("--graph", type=Path, required=True)
    s.add_argument("--out", type=Path, default=Path("benchmark/data/audit.tsv"))
    s.add_argument("--key", type=Path, default=Path("benchmark/data/audit_key.json"))
    s.add_argument("--total", type=int, help=f"sample size, label-2 pages included (default: label 2 plus {DEFAULT_REST})")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--exclude", type=Path, nargs="*", default=[Path(p) for p in PILOT_FILES],
                   help="TSV files with a `page` column whose pages are left out")
    c = sub.add_parser("score", help="compare the filled TSV with the judge")
    c.add_argument("--tsv", type=Path, required=True)
    c.add_argument("--key", type=Path, required=True)
    c.add_argument("--tsv2", type=Path, help="second annotator's filled TSV (same ids)")
    f = sub.add_parser("form", help="write an HTML checklist for a sample TSV")
    f.add_argument("--tsv", type=Path, default=Path("benchmark/data/audit.tsv"))
    f.add_argument("--out", type=Path, default=Path("benchmark/data/audit.html"))
    f.add_argument("--limit", type=int, help="only the first N rows (second annotator: 50)")
    f.add_argument("--name", default="audit_filled.tsv", help="file name the export downloads as")
    args = ap.parse_args()
    if args.cmd == "form":
        form(args.tsv, args.out, args.limit, args.name)
    elif args.cmd == "sample":
        sample(args.graph, args.out, args.key, args.total, args.seed, args.exclude)
    else:
        score(args.tsv, args.key, args.tsv2)


if __name__ == "__main__":
    main()
